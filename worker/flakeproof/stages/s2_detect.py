"""Stage 2 — detect: fork the baseline checkpoint N times and run the suite in
parallel to prove flakiness (same code + same starting state, different outcomes).

Implements docs/03-PIPELINE.md "Stage 2 — DETECT" end to end: one identical
pytest command forked N ways, JUnit XML parsed back per branch, aggregated
into `test_stats`/`test_results`, and `flaky_tests` findings inserted ordered
by failure rate. Only the top `config.max_flaky_to_fix` nodeids are returned
for S3 to diagnose (docs: "top max_flaky_to_fix rows of flaky_tests"); a
`max_flaky_to_fix=0` config (a legitimate "detect-only" run, per
web/lib/run-config.ts) skips diagnosis entirely and the run goes straight to
`reporting`, same as the zero-flaky-tests case.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from supabase import Client

from flakeproof import db, pytest_parse
from flakeproof.executors.base import EnvHandle, SandboxCommand, SandboxExecutor

STAGE = "s2_detect"

REPORT_PATH = "/tmp/report.xml"
_DEFAULT_MAX_CONCURRENT_SANDBOXES = 10


@dataclass
class _TestAgg:
    file_path: str
    pass_count: int = 0
    fail_count: int = 0
    error_count: int = 0
    timeout_count: int = 0
    durations_ms: list[int] = field(default_factory=list)
    # (branch_index, outcome, duration_ms, message, log_tail) for every branch this test appeared in.
    per_branch: list[tuple[int, str, int | None, str | None, str | None]] = field(default_factory=list)


def _max_concurrent_sandboxes() -> int:
    return int(os.environ.get("MAX_CONCURRENT_SANDBOXES", _DEFAULT_MAX_CONCURRENT_SANDBOXES))


def classify(pass_count: int, fail_count: int, error_count: int, timeout_count: int) -> tuple[bool, bool]:
    """docs/03-PIPELINE.md Stage 2 step 4 verdict math, given one test's outcome
    counts across the forks that actually reported a result for it:
    `is_flaky = 0 < failures < observed`; `is_always_failing = failures == observed`
    (broken/excluded from fixing, not flaky). Deliberately keyed off *observed*
    runs, not the nominal fork count -- see the call site's comment.
    """
    n_observed = pass_count + fail_count + error_count + timeout_count
    bad_count = fail_count + error_count + timeout_count
    is_flaky = 0 < bad_count < n_observed
    is_always_failing = n_observed > 0 and bad_count == n_observed
    return is_flaky, is_always_failing


def _detect_command(per_test_timeout_s: int) -> str:
    return (
        f"cd /app && pytest -q --junitxml={REPORT_PATH} -p no:cacheprovider "
        f"--timeout={per_test_timeout_s}; echo EXIT:$?"
    )


async def run(
    run_id: str,
    executor: SandboxExecutor,
    env: EnvHandle,
    db_client: Client,
    *,
    num_forks: int = 20,
) -> list[str]:
    """Run the full suite across `num_forks` identical forks and return the nodeids
    of tests proven flaky (inconsistent pass/fail across forks), capped to the
    run's `max_flaky_to_fix` (highest failure rate first).
    """
    run_row = await db.get_run(db_client, run_id)
    config: dict[str, Any] = run_row.get("config") or {}
    per_test_timeout_s = int(config.get("per_run_timeout_s", 900))
    max_flaky_to_fix = int(config.get("max_flaky_to_fix", 3))

    known_node_ids = await db.list_test_ids(db_client, run_id)

    await db.emit_event(db_client, run_id, STAGE, "info", f"Running {num_forks} parallel forks...")
    command = _detect_command(per_test_timeout_s)
    branches = await executor.fork_and_run(
        env,
        [SandboxCommand(command=command) for _ in range(num_forks)],
        concurrency=_max_concurrent_sandboxes(),
    )

    aggregates: dict[str, _TestAgg] = {}
    read_failures = 0
    for branch_index, branch in enumerate(branches):
        try:
            report_xml = await executor.read_file(branch.env, REPORT_PATH)
            testcases = pytest_parse.parse_junit_xml(report_xml)
        except Exception:  # noqa: BLE001 — Docker/ConTree raise unrelated exception types; a missing report is data, not our bug
            read_failures += 1
            continue
        for result in pytest_parse.match_node_ids(testcases, known_node_ids):
            agg = aggregates.setdefault(result.nodeid, _TestAgg(file_path=result.nodeid.split("::", 1)[0]))
            duration_ms = int(result.duration_s * 1000)
            if result.outcome == "passed":
                agg.pass_count += 1
            elif result.outcome == "failed":
                agg.fail_count += 1
            elif result.outcome == "error":
                agg.error_count += 1
            elif result.outcome == "timeout":
                agg.timeout_count += 1
            agg.durations_ms.append(duration_ms)
            agg.per_branch.append((branch_index, result.outcome, duration_ms, result.message, result.log_tail))

    if read_failures:
        await db.emit_event(
            db_client,
            run_id,
            STAGE,
            "warn",
            f"{read_failures}/{num_forks} forks produced no readable JUnit report (crashed before pytest ran?)",
        )

    test_stats_rows: list[db.TestStatInsert] = []
    flaky_tests_rows: list[db.FlakyTestInsert] = []
    test_results_rows: list[db.TestResultInsert] = []

    for nodeid, agg in aggregates.items():
        # classify() is keyed off observed forks, not the nominal num_forks -- a
        # handful of forks crashing before pytest even ran (read_failures above)
        # shouldn't make an otherwise-consistent test look flaky. failure_rate
        # below still divides by num_forks (the "X/N identical runs" the docs/UI
        # report against).
        is_flaky, is_always_failing = classify(agg.pass_count, agg.fail_count, agg.error_count, agg.timeout_count)
        bad_count = agg.fail_count + agg.error_count + agg.timeout_count
        mean_duration_ms = int(sum(agg.durations_ms) / len(agg.durations_ms)) if agg.durations_ms else None

        test_stats_rows.append(
            {
                "run_id": run_id,
                "test_id": nodeid,
                "file_path": agg.file_path,
                "pass_count": agg.pass_count,
                "fail_count": agg.fail_count,
                "error_count": agg.error_count,
                "timeout_count": agg.timeout_count,
                "mean_duration_ms": mean_duration_ms,
                "is_flaky": is_flaky,
                "is_always_failing": is_always_failing,
            }
        )

        keep_all = is_flaky or is_always_failing
        for branch_index, outcome, duration_ms, message, log_tail in agg.per_branch:
            if not keep_all and outcome == "passed":
                continue
            test_results_rows.append(
                {
                    "run_id": run_id,
                    "test_id": nodeid,
                    "phase": "detect",
                    "branch_index": branch_index,
                    "perturbation": "none",
                    "outcome": outcome,
                    "duration_ms": duration_ms,
                    "failure_message": message,
                    "failure_log": log_tail,
                }
            )

        if is_flaky:
            failure_rate = bad_count / num_forks
            flaky_tests_rows.append(
                {
                    "run_id": run_id,
                    "test_id": nodeid,
                    "file_path": agg.file_path,
                    "failure_rate": failure_rate,
                    "status": "detected",
                }
            )
        elif is_always_failing:
            await db.emit_event(
                db_client,
                run_id,
                STAGE,
                "warn",
                f"{nodeid} failed {bad_count}/{num_forks} runs — always failing, excluded from fixing",
            )

    await db.upsert_test_stats(db_client, test_stats_rows)
    await db.insert_test_results(db_client, test_results_rows)

    flaky_tests_rows.sort(key=lambda row: row["failure_rate"], reverse=True)
    inserted = await db.insert_flaky_tests(db_client, flaky_tests_rows)
    for row in sorted(inserted, key=lambda r: r["failure_rate"], reverse=True):
        fails = round(row["failure_rate"] * num_forks)
        await db.emit_event(
            db_client,
            run_id,
            STAGE,
            "success",
            f"\U0001f3af Flaky caught: {row['test_id']} — failed {fails}/{num_forks} identical runs",
        )

    ordered_nodeids = [row["test_id"] for row in sorted(inserted, key=lambda r: r["failure_rate"], reverse=True)]

    if not ordered_nodeids:
        await db.emit_event(
            db_client, run_id, STAGE, "success", f"No flakiness found in {num_forks} identical runs"
        )
        await db.update_run_status(db_client, run_id, "reporting")
        return []

    if max_flaky_to_fix <= 0:
        await db.emit_event(
            db_client,
            run_id,
            STAGE,
            "info",
            f"{len(ordered_nodeids)} flaky test(s) found; max_flaky_to_fix=0, skipping diagnosis (detect-only run)",
        )
        await db.update_run_status(db_client, run_id, "reporting")
        return []

    to_diagnose = ordered_nodeids[:max_flaky_to_fix]
    await db.update_run_status(db_client, run_id, "diagnosing")
    return to_diagnose
