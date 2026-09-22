"""Stage 4 — fix: generate a patch for each diagnosed flaky test, gate it, and
store it. Patches touch test code and fixtures/conftest only.

Implements docs/03-PIPELINE.md "Stage 4 — FIX": Nemotron P4 patch generation,
a deterministic pre-check pass (path allowlist, no added sleeps/skips/xfails,
non-decreasing assertion count per hunk, a changed-lines cap) plus the P5
semantic review gate, one retry with the reviewer's objection appended on
failure, then `status='skipped'` if it's still bad.

Correction against the original stub's docstring: patch *application* to a
real sandbox checkpoint happens in S5, not here (docs/03-PIPELINE.md lists
"Apply patch: write_file the patched files ... on a fork -> new checkpoint"
under Stage 5's steps, not Stage 4's) -- this stage's own sandbox use is
limited to a throwaway `git apply --check` against `env` to confirm the
patch is really applicable before persisting it as `fix_proposed`. The
return type changed accordingly: the nodeids that got a usable patch (S5's
verification queue), not an `EnvHandle`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from supabase import Client

from flakeproof import db, llm
from flakeproof.executors.base import EnvHandle, SandboxExecutor

STAGE = "s4_fix"

_CONTEXT_MAX_LINES = 400
_MAX_CHANGED_LINES = 200  # docs/05-LLM-PROMPTS.md P4: "Keep the diff minimal (< 200 changed lines)"
_MAX_ATTEMPTS = 2  # initial + one retry, per docs/03-PIPELINE.md Stage 4 step 2

_SLEEP_RE = re.compile(r"\b(?:time\.sleep|asyncio\.sleep)\s*\(")
_SKIP_XFAIL_RE = re.compile(r"@pytest\.mark\.(?:skip|xfail)\b|pytest\.(?:skip|xfail)\s*\(")
_RERUN_RE = re.compile(r"@pytest\.mark\.flaky\b|@retry\b|reruns\s*=")
_ASSERT_RE = re.compile(r"^\s*assert\b")


# ============ unified diff parsing + deterministic gate (pure, unit-testable) ============


@dataclass(frozen=True)
class DiffHunk:
    """One `@@ ... @@` hunk's changed lines for one file in a unified diff."""

    path: str
    added_lines: list[str]
    removed_lines: list[str]


def parse_unified_diff(patch_text: str) -> list[DiffHunk]:
    """Parse a `git apply`-compatible unified diff into per-hunk added/removed lines.

    Tolerant of the usual surrounding noise (`diff --git`, `index ...` lines)
    since only `--- `/`+++ ` (file boundary) and `@@ ` (hunk boundary) are
    recognized; anything else is ignored rather than erroring.
    """
    hunks: list[DiffHunk] = []
    current_path: str | None = None
    added: list[str] = []
    removed: list[str] = []
    in_hunk = False

    def _flush() -> None:
        if in_hunk and current_path is not None:
            hunks.append(DiffHunk(path=current_path, added_lines=list(added), removed_lines=list(removed)))

    for line in patch_text.splitlines():
        if line.startswith("+++ "):
            _flush()
            path = line[4:].strip()
            current_path = path.removeprefix("b/")
            in_hunk = False
            continue
        if line.startswith("--- "):
            continue
        if line.startswith("@@"):
            _flush()
            added, removed = [], []
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            removed.append(line[1:])
    _flush()
    return hunks


def _is_allowed_path(path: str) -> bool:
    """docs/05-LLM-PROMPTS.md P4/P5 rule: "only test files, conftest.py, or test fixtures"."""
    name = path.rsplit("/", 1)[-1]
    parts = path.split("/")
    return name == "conftest.py" or name.startswith("test_") or name.endswith("_test.py") or "test" in parts or "tests" in parts


def static_precheck(patch_text: str) -> list[str]:
    """Deterministic pre-checks from docs/05-LLM-PROMPTS.md P5's note: path
    allowlist, non-decreasing assertion count per hunk, a changed-lines cap,
    plus the FORBIDDEN list from P4's own system prompt (sleep-based fixes,
    skip/xfail, retry/rerun decorators). Returns objection strings; empty
    means the patch passed every static check.
    """
    hunks = parse_unified_diff(patch_text)
    if not hunks:
        return ["Patch has no parseable diff hunks"]

    objections: list[str] = []
    total_changed = 0
    assert_delta_by_path: dict[str, int] = {}

    for hunk in hunks:
        total_changed += len(hunk.added_lines) + len(hunk.removed_lines)

        if not _is_allowed_path(hunk.path):
            objections.append(f"Patch touches a non-test file: {hunk.path}")

        added_asserts = sum(1 for line in hunk.added_lines if _ASSERT_RE.match(line))
        removed_asserts = sum(1 for line in hunk.removed_lines if _ASSERT_RE.match(line))
        assert_delta_by_path[hunk.path] = assert_delta_by_path.get(hunk.path, 0) + (added_asserts - removed_asserts)

        for line in hunk.added_lines:
            if _SLEEP_RE.search(line):
                objections.append(f"Patch adds a sleep-based fix in {hunk.path}: {line.strip()}")
            if _SKIP_XFAIL_RE.search(line):
                objections.append(f"Patch adds a skip/xfail marker in {hunk.path}: {line.strip()}")
            if _RERUN_RE.search(line):
                objections.append(f"Patch adds a retry/rerun decorator in {hunk.path}: {line.strip()}")

    for path, delta in assert_delta_by_path.items():
        if delta < 0:
            objections.append(f"Patch removes assertions in {path} (net {delta})")

    if total_changed > _MAX_CHANGED_LINES:
        objections.append(f"Patch changes {total_changed} lines, exceeding the {_MAX_CHANGED_LINES}-line cap")

    return list(dict.fromkeys(objections))  # de-dupe while preserving order


# ============ sandbox context helpers ============


def _truncate_lines(text: str, max_lines: int = _CONTEXT_MAX_LINES) -> str:
    return "\n".join(text.splitlines()[:max_lines])


def _sandbox_path(file_path: str) -> str:
    """S1 clones the repo to /app and every pytest command `cd /app` first, so
    `file_path`/nodeids are repo-relative -- but `read_file` needs a real
    filesystem path (DockerExecutor's `docker cp container:PATH` in particular
    resolves a relative PATH from the container's `/`, not its WORKDIR).
    """
    return f"/app/{file_path}"


def _conftest_path(file_path: str) -> str:
    directory = file_path.rsplit("/", 1)[0] if "/" in file_path else "."
    return _sandbox_path(f"{directory}/conftest.py")


async def _read_best_effort(executor: SandboxExecutor, env: EnvHandle, path: str) -> str:
    try:
        return await executor.read_file(env, path)
    except Exception:  # noqa: BLE001 — a missing conftest.py just means "no fixtures to show"
        return ""


def _numbered(text: str, max_lines: int = _CONTEXT_MAX_LINES) -> str:
    return "\n".join(f"{i + 1}: {line}" for i, line in enumerate(text.splitlines()[:max_lines]))


# ============ patch generation + gate ============


async def _attempt_patch(
    db_client: Client,
    run_id: str,
    executor: SandboxExecutor,
    env: EnvHandle,
    *,
    test_id: str,
    root_cause: str,
    row: dict[str, Any],
    objection_note: str,
) -> tuple[str, str, list[str]]:
    """One P4 -> static gate -> P5 -> `git apply --check` attempt.

    Returns `(patch_text, rationale_md, objections)`; empty `objections` means
    the patch is approved and confirmed applicable against `env`.
    """
    file_path = row["file_path"]
    test_source = await _read_best_effort(executor, env, _sandbox_path(file_path))
    conftest_source = _truncate_lines(await _read_best_effort(executor, env, _conftest_path(file_path)))
    evidence = row.get("evidence") or {}
    sample_failures = evidence.get("sample_failures") or []
    failure_log_tail = sample_failures[0].get("log_tail", "") if sample_failures else ""

    p4_result = await llm.run(
        db_client,
        "patch_gen",
        {
            "test_id": test_id,
            "root_cause": root_cause,
            "confidence": row.get("confidence") or 0.0,
            "diagnosis_md": row.get("diagnosis_md") or "",
            "evidence_matrix_compact": json.dumps(evidence.get("matrix", {})),
            "file_path": file_path,
            "numbered_test_file": _numbered(test_source),
            "conftest_source": conftest_source,
            "failure_log_tail": failure_log_tail,
            "previous_attempt_objection": (
                f"Your previous attempt was rejected: {objection_note} Fix this and try again."
                if objection_note
                else ""
            ),
        },
        run_id=run_id,
        stage=STAGE,
    )
    if not p4_result.ok or p4_result.data is None:
        return "", "", [f"Patch generation failed: {p4_result.error or 'model error'}"]

    patch_text = str(p4_result.data.get("patch", "")).strip()
    rationale_md = str(p4_result.data.get("rationale_md", ""))
    if not patch_text:
        return "", rationale_md, ["Model returned an empty patch"]
    # A unified diff's last hunk line needs a trailing newline (or an explicit
    # "\ No newline at end of file" marker) or `git apply` rejects the whole
    # file as corrupt -- .strip() above removes exactly that newline, so it
    # has to come back before anything ever tries to apply this text.
    patch_text += "\n"

    objections = static_precheck(patch_text)
    if objections:
        return patch_text, rationale_md, objections

    p5_result = await llm.run(
        db_client, "patch_review", {"root_cause": root_cause, "patch": patch_text}, run_id=run_id, stage=STAGE
    )
    if not p5_result.ok or p5_result.data is None:
        return patch_text, rationale_md, [f"Patch review call failed: {p5_result.error or 'model error'}"]
    if not p5_result.data.get("approved"):
        objections = [str(o) for o in (p5_result.data.get("objections") or ["Reviewer rejected the patch"])]
        return patch_text, rationale_md, objections

    check_env = await executor.write_file(env, "/tmp/fix_check.patch", patch_text)
    check_result = await executor.run(check_env, "cd /app && git apply --check /tmp/fix_check.patch", timeout_s=60)
    if check_result.exit_code != 0:
        return patch_text, rationale_md, [f"git apply --check failed: {check_result.stderr.strip()[-400:]}"]

    return patch_text, rationale_md, []


async def run(
    run_id: str,
    executor: SandboxExecutor,
    env: EnvHandle,
    diagnoses: dict[str, str],
    db_client: Client,
) -> list[str]:
    """Generate and gate a patch per diagnosed test. Returns the nodeids whose
    patch was approved and stored as `fix_proposed` (ready for S5 to verify).
    """
    if not diagnoses:
        await db.update_run_status(db_client, run_id, "verifying")
        return []

    flaky_rows = {row["test_id"]: row for row in await db.list_flaky_tests(db_client, run_id) if row["test_id"] in diagnoses}

    await db.emit_event(db_client, run_id, STAGE, "info", "Generating patches...")

    proposed: list[str] = []
    for test_id, root_cause in diagnoses.items():
        row = flaky_rows.get(test_id)
        if row is None:
            continue
        await db.update_flaky_test(db_client, row["id"], status="fixing")

        short_name = test_id.rsplit("::", 1)[-1]
        objection_note = ""
        patch_text = rationale_md = ""
        objections: list[str] = []
        for attempt in range(_MAX_ATTEMPTS):
            patch_text, rationale_md, objections = await _attempt_patch(
                db_client,
                run_id,
                executor,
                env,
                test_id=test_id,
                root_cause=root_cause,
                row=row,
                objection_note=objection_note,
            )
            if not objections:
                break
            objection_note = "; ".join(objections)
            if attempt < _MAX_ATTEMPTS - 1:
                await db.emit_event(
                    db_client, run_id, STAGE, "warn", f"Patch attempt {attempt + 1} for {short_name} rejected: {objection_note}"
                )

        if not objections:
            await db.update_flaky_test(
                db_client, row["id"], status="fix_proposed", fix_patch=patch_text, fix_rationale_md=rationale_md
            )
            summary = rationale_md.strip().split(".")[0][:100] if rationale_md.strip() else "patch generated"
            await db.emit_event(db_client, run_id, STAGE, "success", f"Patch proposed for {short_name} ({summary})")
            proposed.append(test_id)
        else:
            await db.update_flaky_test(
                db_client, row["id"], status="skipped", fix_patch=patch_text or None, fix_rationale_md=f"Skipped: {objection_note}"
            )
            await db.emit_event(db_client, run_id, STAGE, "warn", f"Skipped fix for {short_name}: {objection_note}")

    await db.update_run_status(db_client, run_id, "verifying")
    return proposed
