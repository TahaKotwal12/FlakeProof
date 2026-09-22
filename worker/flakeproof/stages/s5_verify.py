"""Stage 5 — verify: re-run each fixed test across fresh forks under its
triggering condition to prove the fix ("Before: 7/20 failed. After: 0/20.").

Implements docs/03-PIPELINE.md "Stage 5 — VERIFY": picks the triggering
condition (the perturbation with the highest failure rate in S3's evidence
matrix, falling back to a plain repeat), a before wave against the
unpatched checkpoint, the actual `git apply` (S4 only ever ran
`git apply --check`), a full-suite regression guard, an after wave against
the patched checkpoint, and the verdict.

Self-sufficient like S1 (docs: "the worker can die and restart at any stage
boundary"): unlike S3/S4, this stage isn't handed a nodeid list -- it
queries `flaky_tests` for this run's `fix_proposed` rows itself.
"""

from __future__ import annotations

import os
from typing import Any

from supabase import Client

from flakeproof import db, perturbations, pytest_parse
from flakeproof.executors.base import EnvHandle, SandboxExecutor

STAGE = "s5_verify"

_DEFAULT_MAX_CONCURRENT_SANDBOXES = 10
_PATCH_PATH = "/tmp/fix.patch"


def _max_concurrent_sandboxes() -> int:
    return int(os.environ.get("MAX_CONCURRENT_SANDBOXES", _DEFAULT_MAX_CONCURRENT_SANDBOXES))


def _pick_triggering_condition(evidence: dict[str, Any]) -> str:
    """docs/03-PIPELINE.md Stage 5 step 1: "the perturbation with the highest
    failure rate in the evidence matrix (fallback: none = plain repeat)".
    """
    matrix = evidence.get("matrix") or {}
    best_name = "none"
    best_rate = 0.0
    for name, data in matrix.items():
        runs = data.get("runs", 0)
        if runs <= 0:
            continue
        rate = data.get("failures", 0) / runs
        if rate > best_rate:
            best_rate = rate
            best_name = name
    return best_name


def _condition_commands(condition: str, test_id: str, *, k: int, per_test_timeout_s: int):
    name = condition if condition in perturbations.ALL_PERTURBATIONS else "alone"
    return perturbations.build_commands(name, test_id, k=k, per_test_timeout_s=per_test_timeout_s)


async def _run_wave(
    executor: SandboxExecutor,
    env: EnvHandle,
    *,
    run_id: str,
    test_id: str,
    condition: str,
    k: int,
    per_test_timeout_s: int,
    phase: db.ResultPhase,
) -> tuple[int, int, list[db.TestResultInsert]]:
    """Fork `k` branches of `env` running `test_id` under `condition`. Returns
    `(observed, failures, test_results_rows)` -- all `k` forks' outcomes are
    kept (docs/02-DATABASE.md: "ALL results for flaky tests").
    """
    commands = _condition_commands(condition, test_id, k=k, per_test_timeout_s=per_test_timeout_s)
    try:
        branches = await executor.fork_and_run(env, commands, concurrency=_max_concurrent_sandboxes())
    except Exception:  # noqa: BLE001 — docs/04-API.md: degrade rather than fail the run
        return 0, 0, []

    target_identity = pytest_parse.classname_and_name_for_nodeid(test_id)
    observed = 0
    failures = 0
    rows: list[db.TestResultInsert] = []
    for branch_index, branch in enumerate(branches):
        try:
            report_xml = await executor.read_file(branch.env, perturbations.REPORT_PATH)
            testcases = pytest_parse.parse_junit_xml(report_xml)
        except Exception:  # noqa: BLE001, S112 — a fork with no report contributes no data
            continue
        matches = [tc for tc in testcases if (tc.classname, tc.name) == target_identity]
        if not matches:
            continue
        result = matches[0]
        observed += 1
        if result.outcome != "passed":
            failures += 1
        rows.append(
            {
                "run_id": run_id,
                "test_id": test_id,
                "phase": phase,
                "branch_index": branch_index,
                "perturbation": condition,
                "outcome": result.outcome,
                "duration_ms": int(result.duration_s * 1000),
                "failure_message": result.message,
                "failure_log": result.log_tail,
            }
        )
    return observed, failures, rows


async def _mark_fix_failed(db_client: Client, run_id: str, row: dict[str, Any], *, reason: str, before_failures: int, num_forks: int) -> None:
    await db.update_flaky_test(
        db_client, row["id"], status="fix_failed", verify_before_failures=before_failures, verify_total=num_forks
    )
    await db.emit_event(db_client, run_id, STAGE, "error", f"❌ FIX FAILED {row['test_id']} — {reason}")


async def run(
    run_id: str,
    executor: SandboxExecutor,
    env: EnvHandle,
    db_client: Client,
    *,
    num_forks: int = 20,
) -> dict[str, tuple[int, int]]:
    """Return {nodeid: (failures_before, failures_after)} verification scoreboard."""
    run_row = await db.get_run(db_client, run_id)
    config: dict[str, Any] = run_row.get("config") or {}
    per_test_timeout_s = int(config.get("per_run_timeout_s", 900))

    flaky_rows = await db.list_flaky_tests(db_client, run_id, statuses=["fix_proposed"])
    if not flaky_rows:
        await db.update_run_status(db_client, run_id, "reporting")
        return {}

    await db.emit_event(db_client, run_id, STAGE, "info", "Verifying fixes under triggering conditions...")

    scoreboard: dict[str, tuple[int, int]] = {}
    for row in flaky_rows:
        test_id = row["test_id"]
        await db.update_flaky_test(db_client, row["id"], status="verifying")

        condition = _pick_triggering_condition(row.get("evidence") or {})

        _before_observed, before_failures, before_rows = await _run_wave(
            executor,
            env,
            run_id=run_id,
            test_id=test_id,
            condition=condition,
            k=num_forks,
            per_test_timeout_s=per_test_timeout_s,
            phase="verify_before",
        )
        await db.insert_test_results(db_client, before_rows)

        fix_patch = row.get("fix_patch") or ""
        if not fix_patch:
            await _mark_fix_failed(db_client, run_id, row, reason="no patch to apply", before_failures=before_failures, num_forks=num_forks)
            scoreboard[test_id] = (before_failures, before_failures)
            continue

        patch_env = await executor.write_file(env, _PATCH_PATH, fix_patch)
        apply_result = await executor.run(patch_env, f"cd /app && git apply {_PATCH_PATH}", timeout_s=60)
        if apply_result.exit_code != 0:
            reason = f"patch failed to apply: {apply_result.stderr.strip()[-300:]}"
            await _mark_fix_failed(db_client, run_id, row, reason=reason, before_failures=before_failures, num_forks=num_forks)
            scoreboard[test_id] = (before_failures, before_failures)
            continue
        patched_env = apply_result.env

        regression_timeout_s = max(per_test_timeout_s * 2, 300)
        regression_result = await executor.run(
            patched_env, f"cd /app && pytest -q --timeout={per_test_timeout_s}", timeout_s=regression_timeout_s
        )
        if regression_result.exit_code != 0:
            await _mark_fix_failed(
                db_client, run_id, row, reason="regression guard failed (patch broke other tests)",
                before_failures=before_failures, num_forks=num_forks,
            )
            scoreboard[test_id] = (before_failures, before_failures)
            continue

        after_observed, after_failures, after_rows = await _run_wave(
            executor,
            patched_env,
            run_id=run_id,
            test_id=test_id,
            condition=condition,
            k=num_forks,
            per_test_timeout_s=per_test_timeout_s,
            phase="verify_after",
        )
        await db.insert_test_results(db_client, after_rows)

        verified = after_observed > 0 and after_failures == 0
        await db.update_flaky_test(
            db_client,
            row["id"],
            status="fix_verified" if verified else "fix_failed",
            verify_before_failures=before_failures,
            verify_after_failures=after_failures,
            verify_total=num_forks,
        )
        if verified:
            await db.emit_event(
                db_client, run_id, STAGE, "success",
                f"✅ VERIFIED {test_id} — before {before_failures}/{num_forks} failed, after {after_failures}/{num_forks}",
            )
        else:
            await db.emit_event(
                db_client, run_id, STAGE, "error",
                f"❌ FIX FAILED {test_id} — before {before_failures}/{num_forks} failed, after {after_failures}/{num_forks}",
            )
        scoreboard[test_id] = (before_failures, after_failures)

    await db.update_run_status(db_client, run_id, "reporting")
    return scoreboard
