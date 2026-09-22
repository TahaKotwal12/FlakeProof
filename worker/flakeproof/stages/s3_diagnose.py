"""Stage 3 — diagnose: run the perturbation matrix per flaky test and classify
root cause with Nemotron, backed by evidence from the forked runs.

Implements docs/03-PIPELINE.md "Stage 3 — DIAGNOSE": one `fork_and_run` wave
per usable perturbation (docs/05-LLM-PROMPTS.md P2 normalizes the raw failure
logs first, feeding structured records into P3's root-cause classification),
evidence assembly, optional Tavily enrichment (P7, docs/04-API.md B3), and a
`flaky_tests` update per test.
"""

from __future__ import annotations

import json
import os
from typing import Any

from supabase import Client

from flakeproof import db, llm, perturbations, pytest_parse, tavily_enrich
from flakeproof.executors.base import EnvHandle, SandboxExecutor

STAGE = "s3_diagnose"

_DEFAULT_MAX_CONCURRENT_SANDBOXES = 10
_CONTEXT_MAX_LINES = 400  # docs/05-LLM-PROMPTS.md: "source files -> max 400 lines each"
_MAX_SAMPLE_FAILURES = 3

_ROOT_CAUSE_LABELS: dict[str, str] = {
    "async_race": "async race condition",
    "order_dependent": "order-dependent shared state",
    "time_dependent": "time-dependent assertion",
    "network_external": "hidden network dependency",
    "randomness": "unseeded randomness",
    "resource_leak": "resource leak under load",
    "concurrency_shared_state": "concurrency shared-state race",
    "unknown": "inconclusive",
}


def _max_concurrent_sandboxes() -> int:
    return int(os.environ.get("MAX_CONCURRENT_SANDBOXES", _DEFAULT_MAX_CONCURRENT_SANDBOXES))


def _truncate_lines(text: str, max_lines: int = _CONTEXT_MAX_LINES) -> str:
    lines = text.splitlines()
    return "\n".join(lines[:max_lines])


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
    except Exception:  # noqa: BLE001 — a missing conftest.py (or read error) just means "no fixtures to show"
        return ""


def _format_evidence_table(matrix: dict[str, dict[str, int]]) -> str:
    return "\n".join(f"{name}: {data['runs']} runs, {data['failures']} failures" for name, data in matrix.items())


def _format_failure_blocks(sample_failures: list[dict[str, str]]) -> str:
    if not sample_failures:
        return "(none)"
    return "\n\n".join(
        f"{i}. perturbation={sf['perturbation']}\n{sf.get('log_tail') or sf.get('message') or '(no output)'}"
        for i, sf in enumerate(sample_failures)
    )


async def _run_perturbation_wave(
    executor: SandboxExecutor,
    env: EnvHandle,
    *,
    name: str,
    test_id: str,
    k: int,
    per_test_timeout_s: int,
) -> tuple[dict[str, int], list[dict[str, str]]]:
    """Run one perturbation's K forks and return (matrix entry, sample failures for this perturbation)."""
    commands = perturbations.build_commands(name, test_id, k=k, per_test_timeout_s=per_test_timeout_s)
    try:
        branches = await executor.fork_and_run(env, commands, concurrency=_max_concurrent_sandboxes())
    except Exception:  # noqa: BLE001 — docs/04-API.md: "surface as run_events warn + degrade" on any sandbox error
        return {"runs": 0, "failures": 0}, []

    observed = 0
    failures = 0
    samples: list[dict[str, str]] = []
    for branch in branches:
        try:
            report_xml = await executor.read_file(branch.env, perturbations.REPORT_PATH)
            testcases = pytest_parse.parse_junit_xml(report_xml)
        except Exception:  # noqa: BLE001, S112 — a fork that never produced a report contributes no data
            continue
        matches = [tc for tc in testcases if pytest_parse.classname_and_name_for_nodeid(test_id) == (tc.classname, tc.name)]
        if not matches:
            continue
        result = matches[0]
        observed += 1
        if result.outcome != "passed":
            failures += 1
            if len(samples) < 1:  # one representative sample per perturbation is enough
                samples.append(
                    {
                        "perturbation": name,
                        "message": result.message or "",
                        "log_tail": result.log_tail or "",
                    }
                )
    return {"runs": observed, "failures": failures}, samples


async def run(
    run_id: str,
    executor: SandboxExecutor,
    env: EnvHandle,
    flaky_nodeids: list[str],
    db_client: Client,
) -> dict[str, str]:
    """Run each perturbation against each flaky test and return
    {nodeid: root_cause_category}.
    """
    if not flaky_nodeids:
        await db.update_run_status(db_client, run_id, "fixing")
        return {}

    run_row = await db.get_run(db_client, run_id)
    config: dict[str, Any] = run_row.get("config") or {}
    per_test_timeout_s = int(config.get("per_run_timeout_s", 900))
    detect_runs = int(config.get("detect_runs", 20))
    diagnose_k = int(config.get("diagnose_runs_per_perturbation", 6))
    requested_perturbations = list(config.get("perturbations") or perturbations.PERTURBATION_NAMES)
    tavily_wanted = config.get("tavily_enrichment", True)
    owner = run_row["repo_owner"]
    repo = run_row["repo_name"]
    tavily = tavily_enrich.TavilyEnrichment()

    flaky_rows = {
        row["test_id"]: row
        for row in await db.list_flaky_tests(db_client, run_id)
        if row["test_id"] in flaky_nodeids
    }

    available_features = await perturbations.detect_available_features(executor, env)
    usable, skipped = perturbations.usable_perturbations(requested_perturbations, available_features)
    for name in skipped:
        feature = perturbations.ALL_PERTURBATIONS[name].requires_feature
        await db.emit_event(
            db_client, run_id, STAGE, "warn", f"Skipping perturbation '{name}': {feature} not available in this environment"
        )

    await db.emit_event(db_client, run_id, STAGE, "info", f"Running perturbation matrix for {len(flaky_nodeids)} flaky tests...")

    diagnoses: dict[str, str] = {}

    for test_id in flaky_nodeids:
        row = flaky_rows.get(test_id)
        if row is None:
            continue
        await db.update_flaky_test(db_client, row["id"], status="diagnosing")

        matrix: dict[str, dict[str, int]] = {}
        sample_failures: list[dict[str, str]] = []
        for name in perturbations.PERTURBATION_NAMES:
            if name not in usable:
                matrix[name] = {"runs": 0, "failures": 0}
                continue
            entry, samples = await _run_perturbation_wave(
                executor, env, name=name, test_id=test_id, k=diagnose_k, per_test_timeout_s=per_test_timeout_s
            )
            matrix[name] = entry
            if samples and len(sample_failures) < _MAX_SAMPLE_FAILURES:
                sample_failures.extend(samples[: _MAX_SAMPLE_FAILURES - len(sample_failures)])

        file_path = row["file_path"]
        test_source = _truncate_lines(await _read_best_effort(executor, env, _sandbox_path(file_path)))
        fixtures_source = _truncate_lines(await _read_best_effort(executor, env, _conftest_path(file_path)))

        known_reports: list[dict[str, str]] = []
        if tavily_wanted:
            known_reports = await tavily.enrich(
                owner=owner, repo=repo, test_id=test_id, db_client=db_client, run_id=run_id, stage=STAGE
            )

        normalized_failures_json = "[]"
        if sample_failures:
            p2_result = await llm.run(
                db_client,
                "failure_parse",
                {"n": len(sample_failures), "failure_blocks_with_indices": _format_failure_blocks(sample_failures)},
                run_id=run_id,
                stage=STAGE,
            )
            if p2_result.ok and p2_result.data is not None:
                normalized_failures_json = json.dumps(p2_result.data)

        failure_rate = float(row["failure_rate"])
        baseline_k = round(failure_rate * detect_runs)

        p3_result = await llm.run(
            db_client,
            "root_cause",
            {
                "test_id": test_id,
                "k": baseline_k,
                "n": detect_runs,
                "rate": round(failure_rate, 2),
                "evidence_matrix_table": _format_evidence_table(matrix),
                "normalized_failures_json": normalized_failures_json,
                "file_path": file_path,
                "test_source": test_source,
                "fixtures_source": fixtures_source,
                "tavily_known_reports": json.dumps(known_reports) if known_reports else "(none)",
            },
            run_id=run_id,
            stage=STAGE,
        )

        evidence = {"baseline_failure_rate": failure_rate, "matrix": matrix, "sample_failures": sample_failures}

        if p3_result.ok and p3_result.data is not None:
            root_cause = str(p3_result.data.get("root_cause", "unknown"))
            if root_cause not in _ROOT_CAUSE_LABELS:
                root_cause = "unknown"
            confidence = float(p3_result.data.get("confidence", 0.0))
            diagnosis_md = str(p3_result.data.get("diagnosis_md", ""))
        else:
            root_cause = "unknown"
            confidence = 0.0
            diagnosis_md = f"Diagnosis unavailable: {p3_result.error or 'model call failed'}"

        await db.update_flaky_test(
            db_client,
            row["id"],
            status="diagnosed",
            root_cause=root_cause,
            confidence=confidence,
            diagnosis_md=diagnosis_md,
            evidence=evidence,
            known_reports=known_reports or None,
        )

        short_name = test_id.rsplit("::", 1)[-1]
        await db.emit_event(
            db_client,
            run_id,
            STAGE,
            "success",
            f"\U0001f52c Diagnosed {short_name}: {_ROOT_CAUSE_LABELS[root_cause]} (confidence {confidence:.2f})",
        )
        diagnoses[test_id] = root_cause

    await db.update_run_status(db_client, run_id, "fixing")
    return diagnoses
