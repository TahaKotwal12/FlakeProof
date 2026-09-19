"""Seed one fake completed run with 3 flaky tests, shaped like the example
responses in docs/04-API.md, so the web UI has something real to render
without running the actual pipeline.

Run with `python -m flakeproof.seed_demo`. Safe to re-run: deletes any prior
demo run with the same slug first (children cascade-delete via the runs.id FK).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from flakeproof import db

DEMO_SLUG = "x7Kp2mQ9aB"

REPO_OWNER = "flakeproof"
REPO_NAME = "flakeproof-demo"

FILE_API = "tests/test_api.py"
FILE_CACHE = "tests/test_cache.py"
FILE_WORKER_POOL = "tests/test_worker_pool.py"
FILE_UTILS = "tests/test_utils.py"
FILE_BROKEN = "tests/test_broken.py"

TEST_RETRY = f"{FILE_API}::test_retry"
TEST_EXPIRY = f"{FILE_CACHE}::test_expiry"
TEST_CONCURRENT_WRITES = f"{FILE_WORKER_POOL}::test_concurrent_writes"
TEST_BROKEN = f"{FILE_BROKEN}::test_x"

RUN_CONFIG: dict[str, Any] = {
    "detect_runs": 20,
    "verify_runs": 20,
    "max_flaky_to_fix": 3,
    "per_run_timeout_s": 900,
    "install_timeout_s": 900,
    "install_max_attempts": 4,
    "perturbations": ["alone", "order", "cpu_stress", "time_shift", "net_off", "seed"],
    "diagnose_runs_per_perturbation": 6,
    "base_image": "python:3.12-slim",
    "tavily_enrichment": True,
    "pinned": True,
}

STABLE_TESTS = [
    (f"{FILE_API}::test_get", FILE_API),
    (f"{FILE_API}::test_post", FILE_API),
    (f"{FILE_API}::test_delete", FILE_API),
    (f"{FILE_CACHE}::test_set", FILE_CACHE),
    (f"{FILE_CACHE}::test_get", FILE_CACHE),
    (f"{FILE_CACHE}::test_clear", FILE_CACHE),
    (f"{FILE_WORKER_POOL}::test_single_write", FILE_WORKER_POOL),
    (f"{FILE_WORKER_POOL}::test_shutdown", FILE_WORKER_POOL),
    (f"{FILE_UTILS}::test_parse", FILE_UTILS),
    (f"{FILE_UTILS}::test_format", FILE_UTILS),
    (f"{FILE_UTILS}::test_validate", FILE_UTILS),
    (f"{FILE_UTILS}::test_normalize", FILE_UTILS),
]

# (stage, level, message, payload)
RUN_EVENTS: list[tuple[str, str, str, dict[str, Any] | None]] = [
    ("s0_intake", "info", "Repo OK: flakeproof/flakeproof-demo@a1b2c3d, pytest detected, ~16 test files", None),
    ("system", "info", "Run claimed by worker", None),
    ("s1_provision", "info", "Installing dependencies...", None),
    ("s1_provision", "success", "Environment ready: 16 tests collected", None),
    ("s2_detect", "info", "Running 20 parallel forks...", None),
    ("s2_detect", "success", "🎯 Flaky caught: tests/test_api.py::test_retry — failed 7/20 identical runs", None),
    ("s2_detect", "success", "🎯 Flaky caught: tests/test_cache.py::test_expiry — failed 4/20 identical runs", None),
    (
        "s2_detect",
        "success",
        "🎯 Flaky caught: tests/test_worker_pool.py::test_concurrent_writes — failed 9/20 identical runs",
        None,
    ),
    (
        "s2_detect",
        "warn",
        "tests/test_broken.py::test_x failed 20/20 runs — always failing, excluded from fixing",
        None,
    ),
    ("s3_diagnose", "info", "Running perturbation matrix for 3 flaky tests...", None),
    ("s3_diagnose", "success", "🔬 Diagnosed test_retry: order-dependent shared state (confidence 0.86)", None),
    ("s3_diagnose", "success", "🔬 Diagnosed test_expiry: time-dependent assertion (confidence 0.79)", None),
    (
        "s3_diagnose",
        "success",
        "🔬 Diagnosed test_concurrent_writes: concurrency shared-state race (confidence 0.71)",
        None,
    ),
    ("s4_fix", "info", "Generating patches...", None),
    ("s4_fix", "success", "Patch proposed for test_retry (reset rate-limit state fixture)", None),
    ("s4_fix", "success", "Patch proposed for test_expiry (freezegun instead of sleep)", None),
    ("s4_fix", "success", "Patch proposed for test_concurrent_writes (lock around shared results list)", None),
    ("s5_verify", "info", "Verifying fixes under triggering conditions...", None),
    ("s5_verify", "success", "✅ VERIFIED tests/test_api.py::test_retry — before 7/20 failed, after 0/20", None),
    ("s5_verify", "success", "✅ VERIFIED tests/test_cache.py::test_expiry — before 4/20 failed, after 0/20", None),
    (
        "s5_verify",
        "error",
        "❌ FIX FAILED tests/test_worker_pool.py::test_concurrent_writes — before 9/20 failed, after 2/20",
        None,
    ),
    ("s6_report", "success", "Report ready: 3 flaky tests caught, 2 fixed with proof", None),
]


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _detect_results(run_id: str, test_id: str, fail_count: int, n: int = 20) -> list[db.TestResultInsert]:
    """All N detect-phase results for one test (flaky/always-failing tests keep every run)."""
    rows: list[db.TestResultInsert] = []
    for i in range(n):
        failed = i < fail_count
        rows.append(
            {
                "run_id": run_id,
                "test_id": test_id,
                "phase": "detect",
                "branch_index": i,
                "perturbation": "none",
                "outcome": "failed" if failed else "passed",
                "duration_ms": 140 + (i * 7) % 50,
                "failure_message": "AssertionError" if failed else None,
                "failure_log": f"...\nE   AssertionError\n(fork #{i})\n" if failed else None,
            }
        )
    return rows


def _verify_results(
    run_id: str,
    test_id: str,
    phase: db.ResultPhase,
    perturbation: str,
    fail_count: int,
    n: int = 20,
) -> list[db.TestResultInsert]:
    rows: list[db.TestResultInsert] = []
    for i in range(n):
        failed = i < fail_count
        rows.append(
            {
                "run_id": run_id,
                "test_id": test_id,
                "phase": phase,
                "branch_index": i,
                "perturbation": perturbation,
                "outcome": "failed" if failed else "passed",
                "duration_ms": 130 + (i * 5) % 40,
                "failure_message": "AssertionError" if failed else None,
                "failure_log": f"...\nE   AssertionError\n(fork #{i})\n" if failed else None,
            }
        )
    return rows


def _build_test_stats() -> list[db.TestStatInsert]:
    flaky_and_broken: list[db.TestStatInsert] = [
        {
            "test_id": TEST_RETRY,
            "file_path": FILE_API,
            "pass_count": 13,
            "fail_count": 7,
            "error_count": 0,
            "timeout_count": 0,
            "mean_duration_ms": 165,
            "is_flaky": True,
            "is_always_failing": False,
        },
        {
            "test_id": TEST_EXPIRY,
            "file_path": FILE_CACHE,
            "pass_count": 16,
            "fail_count": 4,
            "error_count": 0,
            "timeout_count": 0,
            "mean_duration_ms": 1120,
            "is_flaky": True,
            "is_always_failing": False,
        },
        {
            "test_id": TEST_CONCURRENT_WRITES,
            "file_path": FILE_WORKER_POOL,
            "pass_count": 11,
            "fail_count": 9,
            "error_count": 0,
            "timeout_count": 0,
            "mean_duration_ms": 340,
            "is_flaky": True,
            "is_always_failing": False,
        },
        {
            "test_id": TEST_BROKEN,
            "file_path": FILE_BROKEN,
            "pass_count": 0,
            "fail_count": 20,
            "error_count": 0,
            "timeout_count": 0,
            "mean_duration_ms": 95,
            "is_flaky": False,
            "is_always_failing": True,
        },
    ]
    stable: list[db.TestStatInsert] = [
        {
            "test_id": test_id,
            "file_path": file_path,
            "pass_count": 20,
            "fail_count": 0,
            "error_count": 0,
            "timeout_count": 0,
            "mean_duration_ms": 80,
            "is_flaky": False,
            "is_always_failing": False,
        }
        for test_id, file_path in STABLE_TESTS
    ]
    return flaky_and_broken + stable


def _build_flaky_tests() -> list[db.FlakyTestInsert]:
    return [
        {
            "test_id": TEST_RETRY,
            "file_path": FILE_API,
            "failure_rate": 0.35,
            "status": "fix_verified",
            "root_cause": "order_dependent",
            "confidence": 0.86,
            "diagnosis_md": (
                "### Why this test flakes\n\n"
                "`test_retry` reads a shared module-level `_rate_limit_state` dict that "
                "isn't reset between tests. When `test_backoff` runs first, leftover state "
                "makes `test_retry` see a stale retry counter and skip its second attempt.\n\n"
                "**Fix:** reset `_rate_limit_state` in an autouse fixture."
            ),
            "evidence": {
                "baseline_failure_rate": 0.35,
                "matrix": {
                    "alone": {"runs": 6, "failures": 0},
                    "order": {"runs": 6, "failures": 5},
                    "cpu_stress": {"runs": 6, "failures": 1},
                    "time_shift": {"runs": 6, "failures": 0},
                    "net_off": {"runs": 6, "failures": 0},
                    "seed": {"runs": 6, "failures": 4},
                },
                "sample_failures": [
                    {
                        "perturbation": "order",
                        "message": "AssertionError: assert retry_count == 2",
                        "log_tail": "...  assert retry_count == 2\nE    AssertionError: assert 1 == 2\n",
                    }
                ],
            },
            "known_reports": [
                {
                    "title": "Issue #123: test_retry flaky on CI",
                    "url": "https://github.com/flakeproof/flakeproof-demo/issues/123",
                    "snippet": "We've seen test_retry fail intermittently on CI when run after test_backoff...",
                }
            ],
            "fix_patch": (
                "--- a/tests/test_api.py\n+++ b/tests/test_api.py\n"
                "@@ -1,6 +1,12 @@\n import pytest\n from myapp.client import _rate_limit_state\n \n"
                "+@pytest.fixture(autouse=True)\n+def reset_rate_limit_state():\n"
                "+    _rate_limit_state.clear()\n+    yield\n+    _rate_limit_state.clear()\n+\n \n"
                " def test_retry():\n     ...\n"
            ),
            "fix_rationale_md": (
                "Resets the module-level `_rate_limit_state` dict before and after every test "
                "via an autouse fixture, removing the cross-test dependency that made ordering matter."
            ),
            "verify_before_failures": 7,
            "verify_after_failures": 0,
            "verify_total": 20,
        },
        {
            "test_id": TEST_EXPIRY,
            "file_path": FILE_CACHE,
            "failure_rate": 0.20,
            "status": "fix_verified",
            "root_cause": "time_dependent",
            "confidence": 0.79,
            "diagnosis_md": (
                "### Why this test flakes\n\n"
                "`test_expiry` asserts a cache entry expires after exactly 1 second using "
                "`time.sleep(1)` then a strict equality check. Under load the sleep over- or "
                "undershoots, and the `time_shift` perturbation confirms the expiry math is "
                "sensitive to wall-clock drift near the second boundary.\n\n"
                "**Fix:** freeze time with `freezegun` and advance it deterministically."
            ),
            "evidence": {
                "baseline_failure_rate": 0.20,
                "matrix": {
                    "alone": {"runs": 6, "failures": 1},
                    "order": {"runs": 6, "failures": 0},
                    "cpu_stress": {"runs": 6, "failures": 2},
                    "time_shift": {"runs": 6, "failures": 3},
                    "net_off": {"runs": 6, "failures": 0},
                    "seed": {"runs": 6, "failures": 0},
                },
                "sample_failures": [
                    {
                        "perturbation": "time_shift",
                        "message": "AssertionError: assert cache.get('k') is None",
                        "log_tail": "...  assert cache.get('k') is None\nE    AssertionError: assert 'v' is None\n",
                    }
                ],
            },
            "known_reports": [],
            "fix_patch": (
                "--- a/tests/test_cache.py\n+++ b/tests/test_cache.py\n"
                "@@ -1,10 +1,11 @@\n-import time\n+import freezegun\n \n def test_expiry():\n"
                "     cache = Cache(ttl_seconds=1)\n     cache.set('k', 'v')\n"
                "-    time.sleep(1.05)\n-    assert cache.get('k') is None\n"
                "+    with freezegun.freeze_time() as frozen:\n+        frozen.tick(delta=1.05)\n"
                "+        assert cache.get('k') is None\n"
            ),
            "fix_rationale_md": (
                "Replaces the real `time.sleep` with `freezegun` so expiry is asserted against "
                "a deterministic clock instead of racing the wall clock."
            ),
            "verify_before_failures": 4,
            "verify_after_failures": 0,
            "verify_total": 20,
        },
        {
            "test_id": TEST_CONCURRENT_WRITES,
            "file_path": FILE_WORKER_POOL,
            "failure_rate": 0.45,
            "status": "fix_failed",
            "root_cause": "concurrency_shared_state",
            "confidence": 0.71,
            "diagnosis_md": (
                "### Why this test flakes\n\n"
                "Four worker threads append to a plain Python `list` without a lock. Under "
                "`cpu_stress` the interpreter interleaves appends and the assertion on the "
                "final list length fails nondeterministically.\n\n"
                "**Fix attempted:** wrap the shared list access in a `threading.Lock`, but the "
                "regression guard still saw intermittent failures from a second, unguarded "
                "counter in `WorkerPool.__init__` — out of scope for a test-only patch."
            ),
            "evidence": {
                "baseline_failure_rate": 0.45,
                "matrix": {
                    "alone": {"runs": 6, "failures": 0},
                    "order": {"runs": 6, "failures": 0},
                    "cpu_stress": {"runs": 6, "failures": 6},
                    "time_shift": {"runs": 6, "failures": 0},
                    "net_off": {"runs": 6, "failures": 0},
                    "seed": {"runs": 6, "failures": 1},
                },
                "sample_failures": [
                    {
                        "perturbation": "cpu_stress",
                        "message": "AssertionError: assert len(results) == 400",
                        "log_tail": "...  assert len(results) == 400\nE    AssertionError: assert 397 == 400\n",
                    }
                ],
            },
            "known_reports": [],
            "fix_patch": (
                "--- a/tests/test_worker_pool.py\n+++ b/tests/test_worker_pool.py\n"
                "@@ -12,7 +12,9 @@\n     pool = WorkerPool(n_workers=4)\n-    results = []\n"
                "+    results = []\n+    results_lock = threading.Lock()\n"
            ),
            "fix_rationale_md": (
                "Adds a lock around the shared results list in the test harness. The post-patch "
                "regression guard still showed residual failures traced to an unguarded counter "
                "inside production code (`WorkerPool`), which a test-only patch cannot fix — "
                "flagged `fix_failed` rather than claiming a false verification."
            ),
            "verify_before_failures": 9,
            "verify_after_failures": 2,
            "verify_total": 20,
        },
    ]


def _build_llm_calls() -> list[db.LlmCallInsert]:
    return [
        {
            "stage": "s2_detect",
            "purpose": "failure_parse",
            "model": "nemotron-nano",
            "prompt_tokens": 812,
            "completion_tokens": 96,
            "latency_ms": 420,
            "ok": True,
        },
        {
            "stage": "s3_diagnose",
            "purpose": "root_cause",
            "model": "nemotron-super",
            "prompt_tokens": 3120,
            "completion_tokens": 310,
            "latency_ms": 2100,
            "ok": True,
        },
        {
            "stage": "s3_diagnose",
            "purpose": "root_cause",
            "model": "nemotron-super",
            "prompt_tokens": 2890,
            "completion_tokens": 275,
            "latency_ms": 1950,
            "ok": True,
        },
        {
            "stage": "s3_diagnose",
            "purpose": "root_cause",
            "model": "nemotron-super",
            "prompt_tokens": 3340,
            "completion_tokens": 340,
            "latency_ms": 2260,
            "ok": True,
        },
        {
            "stage": "s4_fix",
            "purpose": "patch_gen",
            "model": "nemotron-super",
            "prompt_tokens": 4210,
            "completion_tokens": 520,
            "latency_ms": 3100,
            "ok": True,
        },
        {
            "stage": "s4_fix",
            "purpose": "patch_review",
            "model": "nemotron-nano",
            "prompt_tokens": 980,
            "completion_tokens": 60,
            "latency_ms": 380,
            "ok": True,
        },
        {
            "stage": "s4_fix",
            "purpose": "patch_gen",
            "model": "nemotron-super",
            "prompt_tokens": 3890,
            "completion_tokens": 410,
            "latency_ms": 2740,
            "ok": True,
        },
        {
            "stage": "s4_fix",
            "purpose": "patch_review",
            "model": "nemotron-nano",
            "prompt_tokens": 910,
            "completion_tokens": 55,
            "latency_ms": 360,
            "ok": True,
        },
        {
            "stage": "s4_fix",
            "purpose": "patch_gen",
            "model": "nemotron-super",
            "prompt_tokens": 4050,
            "completion_tokens": 480,
            "latency_ms": 2990,
            "ok": True,
        },
        {
            "stage": "s4_fix",
            "purpose": "patch_review",
            "model": "nemotron-nano",
            "prompt_tokens": 940,
            "completion_tokens": 58,
            "latency_ms": 370,
            "ok": True,
        },
        {
            "stage": "s6_report",
            "purpose": "report",
            "model": "nemotron-nano",
            "prompt_tokens": 5200,
            "completion_tokens": 640,
            "latency_ms": 1800,
            "ok": True,
        },
    ]


def _build_sandbox_ops() -> list[db.SandboxOpInsert]:
    ops: list[db.SandboxOpInsert] = [
        {
            "kind": "create_env",
            "label": "provision: clone + install",
            "image_in": None,
            "image_out": "img_base_9f2a",
            "exit_code": 0,
            "duration_ms": 48000,
            "status": "ok",
        }
    ]
    ops += [
        {
            "kind": "fork_run",
            "label": f"detect fork #{i}",
            "image_in": "img_base_9f2a",
            "image_out": f"img_detect_{i}",
            "exit_code": 1 if i % 4 == 0 else 0,
            "duration_ms": 8200 + i * 340,
            "status": "ok",
        }
        for i in range(1, 7)
    ]
    ops += [
        {
            "kind": "fork_run",
            "label": f"diagnose order fork #{i} (test_retry)",
            "image_in": "img_base_9f2a",
            "image_out": f"img_diag_order_{i}",
            "exit_code": 1 if i <= 2 else 0,
            "duration_ms": 640 + i * 40,
            "status": "ok",
        }
        for i in range(1, 4)
    ]
    ops += [
        {
            "kind": "write_file",
            "label": "apply patch: test_retry",
            "image_in": "img_base_9f2a",
            "image_out": "img_patched_test_retry",
            "exit_code": 0,
            "duration_ms": 210,
            "status": "ok",
        },
        {
            "kind": "fork_run",
            "label": "verify after fork sample (test_retry)",
            "image_in": "img_patched_test_retry",
            "image_out": "img_verify_after_1",
            "exit_code": 0,
            "duration_ms": 710,
            "status": "ok",
        },
        {
            "kind": "read_file",
            "label": "read /tmp/report.xml (detect fork #1)",
            "image_in": "img_detect_1",
            "image_out": None,
            "exit_code": None,
            "duration_ms": 40,
            "status": "ok",
        },
    ]
    return ops


async def seed() -> None:
    client = db.get_client()
    now = datetime.now(UTC)
    created_at = now - timedelta(minutes=25)
    started_at = now - timedelta(minutes=24)
    finished_at = now - timedelta(minutes=1)
    wall_clock_s = int((finished_at - started_at).total_seconds())

    # idempotent: remove any prior demo run with this slug (children cascade-delete)
    await asyncio.to_thread(lambda: client.table("runs").delete().eq("slug", DEMO_SLUG).execute())

    test_stats = _build_test_stats()
    flaky_tests = _build_flaky_tests()
    llm_calls = _build_llm_calls()
    sandbox_ops = _build_sandbox_ops()

    fork_op_count = sum(1 for op in sandbox_ops if op["kind"] == "fork_run")

    def _insert_run() -> dict[str, Any]:
        return (
            client.table("runs")
            .insert(
                {
                    "slug": DEMO_SLUG,
                    "repo_url": f"https://github.com/{REPO_OWNER}/{REPO_NAME}",
                    "repo_owner": REPO_OWNER,
                    "repo_name": REPO_NAME,
                    "git_ref": "main",
                    "commit_sha": "a1b2c3d4e5f60718293a4b5c6d7e8f901234567",
                    "status": "done",
                    "error": None,
                    "config": RUN_CONFIG,
                    "totals": {
                        "tests_collected": len(test_stats),
                        "detect_runs": 20,
                        "flaky_found": 3,
                        "always_failing": 1,
                        "fixed_verified": 2,
                        "fix_failed": 1,
                        "sandbox_forks": fork_op_count,
                        "llm_calls": len(llm_calls),
                        "wall_clock_s": wall_clock_s,
                    },
                    "env_image_id": "img_base_9f2a",
                    "test_framework": "pytest",
                    "ip_hash": None,
                    "created_at": _iso(created_at),
                    "started_at": _iso(started_at),
                    "finished_at": _iso(finished_at),
                }
            )
            .execute()
            .data[0]
        )

    run = await asyncio.to_thread(_insert_run)
    run_id = run["id"]

    for row in test_stats:
        row["run_id"] = run_id
    for row in flaky_tests:
        row["run_id"] = run_id
    for row in llm_calls:
        row["run_id"] = run_id
    for row in sandbox_ops:
        row["run_id"] = run_id

    test_results: list[db.TestResultInsert] = []
    test_results += _detect_results(run_id, TEST_RETRY, fail_count=7)
    test_results += _detect_results(run_id, TEST_EXPIRY, fail_count=4)
    test_results += _detect_results(run_id, TEST_CONCURRENT_WRITES, fail_count=9)
    test_results += _detect_results(run_id, TEST_BROKEN, fail_count=20)
    test_results += _verify_results(run_id, TEST_RETRY, "verify_before", "order", fail_count=7)
    test_results += _verify_results(run_id, TEST_RETRY, "verify_after", "order", fail_count=0)
    test_results += _verify_results(run_id, TEST_EXPIRY, "verify_before", "time_shift", fail_count=4)
    test_results += _verify_results(run_id, TEST_EXPIRY, "verify_after", "time_shift", fail_count=0)
    test_results += _verify_results(run_id, TEST_CONCURRENT_WRITES, "verify_before", "cpu_stress", fail_count=9)
    test_results += _verify_results(run_id, TEST_CONCURRENT_WRITES, "verify_after", "cpu_stress", fail_count=2)

    await db.insert_test_stats(client, test_stats)
    await db.insert_flaky_tests(client, flaky_tests)
    await db.insert_llm_calls(client, llm_calls)
    await db.insert_sandbox_ops(client, sandbox_ops)
    await db.insert_test_results(client, test_results)

    for stage, level, message, payload in RUN_EVENTS:
        await db.emit_event(client, run_id, stage, level, message, payload)

    print(f"Seeded demo run {DEMO_SLUG} (id={run_id}, {len(test_results)} test_results rows)")


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
