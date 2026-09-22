"""Stage 6 — report: assemble `runs.totals`, get Nemotron's narrative summary
(P6), and mark the run `done`.

Implements docs/03-PIPELINE.md "Stage 6 — REPORT". Per-flake report sections
(evidence matrix, diagnosis, patch, before/after) are *not* rendered here:
`web/lib/report.ts` already assembles `GET /api/runs/:id/report.md` on
request straight from `flaky_tests` rows -- there's no `report_md` column in
`runs` for this stage to write into (see that file's own docstring). P6's
prose is still generated here for real (matching docs/05-LLM-PROMPTS.md and
giving genuine `llm_calls` audit trail / NemotronPanel data), but since
there's nowhere durable to render it inline in the schema as it stands, it's
logged in full as a `run_events` payload rather than silently discarded.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from supabase import Client

from flakeproof import db, llm

STAGE = "s6_report"


def _short_name(test_id: str) -> str:
    return test_id.rsplit("::", 1)[-1]


def _flaky_list_with_rates(flaky_tests: list[dict[str, Any]]) -> str:
    if not flaky_tests:
        return "(none)"
    return ", ".join(f"{_short_name(f['test_id'])} ({round(f['failure_rate'] * 100)}%)" for f in flaky_tests)


def _broken_list(test_stats: list[dict[str, Any]]) -> str:
    broken = [row["test_id"] for row in test_stats if row.get("is_always_failing")]
    return ", ".join(_short_name(t) for t in broken) if broken else "(none)"


def _cause_summary_list(flaky_tests: list[dict[str, Any]]) -> str:
    diagnosed = [f for f in flaky_tests if f.get("root_cause")]
    if not diagnosed:
        return "(none diagnosed)"
    return ", ".join(f"{_short_name(f['test_id'])}: {f['root_cause']}" for f in diagnosed)


def _verified_list_with_before_after(flaky_tests: list[dict[str, Any]]) -> str:
    verified = [f for f in flaky_tests if f.get("status") == "fix_verified"]
    if not verified:
        return "(none)"
    return ", ".join(
        f"{_short_name(f['test_id'])} ({f.get('verify_before_failures', '?')}/{f.get('verify_total', '?')} -> "
        f"{f.get('verify_after_failures', '?')}/{f.get('verify_total', '?')})"
        for f in verified
    )


def _unfixed_list_with_reasons(flaky_tests: list[dict[str, Any]]) -> str:
    unfixed = [f for f in flaky_tests if f.get("status") in ("fix_failed", "skipped")]
    if not unfixed:
        return "(none)"
    return ", ".join(f"{_short_name(f['test_id'])} ({f['status']})" for f in unfixed)


def _headline(flaky_tests: list[dict[str, Any]], detect_runs: int) -> str:
    verified_count = sum(1 for f in flaky_tests if f["status"] == "fix_verified")
    if not flaky_tests:
        return f"No flakiness detected in {detect_runs} identical runs"
    flaky_part = f"{len(flaky_tests)} flaky test{'s' if len(flaky_tests) != 1 else ''} caught"
    return f"{flaky_part} and {verified_count} fixed with proof" if verified_count else flaky_part


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


async def run(run_id: str, db_client: Client) -> None:
    """Compute totals, call Nemotron for the narrative summary, and transition to `done`."""
    run_row = await db.get_run(db_client, run_id)
    config: dict[str, Any] = run_row.get("config") or {}
    owner = run_row["repo_owner"]
    repo = run_row["repo_name"]
    commit_sha = run_row.get("commit_sha") or "0" * 40

    await db.emit_event(db_client, run_id, STAGE, "info", "Compiling report...")

    test_stats = await db.list_test_stats(db_client, run_id)
    flaky_tests = await db.list_flaky_tests(db_client, run_id)
    tests_collected = len(test_stats)
    always_failing_count = sum(1 for row in test_stats if row.get("is_always_failing"))
    fixed_verified_count = sum(1 for f in flaky_tests if f["status"] == "fix_verified")
    fix_failed_count = sum(1 for f in flaky_tests if f["status"] == "fix_failed")
    sandbox_forks = await db.count_rows(db_client, "sandbox_ops", run_id, kind="fork_run")
    detect_runs = int(config.get("detect_runs", 20))

    p6_result = await llm.run(
        db_client,
        "report",
        {
            "owner": owner,
            "repo": repo,
            "sha7": commit_sha[:7],
            "tests_collected": tests_collected,
            "detect_runs": detect_runs,
            "flaky_list_with_rates": _flaky_list_with_rates(flaky_tests),
            "broken_list": _broken_list(test_stats),
            "cause_summary_list": _cause_summary_list(flaky_tests),
            "verified_list_with_before_after": _verified_list_with_before_after(flaky_tests),
            "unfixed_list_with_reasons": _unfixed_list_with_reasons(flaky_tests),
        },
        run_id=run_id,
        stage=STAGE,
    )
    summary_md = p6_result.content if p6_result.ok and p6_result.content else None

    # Counted after the P6 call above (not before): P6 is itself an llm_calls
    # row via llm.run()'s logging, so counting first would always undercount
    # by at least one -- caught live by a real run showing llm_calls=0 despite
    # a real, successfully-logged Nemotron call.
    llm_call_count = await db.count_rows(db_client, "llm_calls", run_id)

    now = datetime.now(UTC)
    started_at = run_row.get("started_at")
    wall_clock_s = int((now - _parse_iso(started_at)).total_seconds()) if started_at else 0

    totals = {
        "tests_collected": tests_collected,
        "detect_runs": detect_runs,
        "flaky_found": len(flaky_tests),
        "always_failing": always_failing_count,
        "fixed_verified": fixed_verified_count,
        "fix_failed": fix_failed_count,
        "sandbox_forks": sandbox_forks,
        "llm_calls": llm_call_count,
        "wall_clock_s": wall_clock_s,
    }

    await db.update_run_status(db_client, run_id, "done", totals=totals, finished_at=now.isoformat())

    headline = _headline(flaky_tests, detect_runs)
    await db.emit_event(
        db_client,
        run_id,
        STAGE,
        "success",
        f"Report ready: {headline}",
        {"summary_md": summary_md} if summary_md else None,
    )
