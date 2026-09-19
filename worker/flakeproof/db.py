"""Supabase/Postgres helpers: run claiming, status transitions, event emission,
and typed insert helpers for the per-run result tables.

The worker polls the DB instead of using a message queue, so state lives
entirely in Postgres and restarts are safe. Runs are claimed via the
`claim_next_run()` Postgres RPC (supabase/migrations/0001_init.sql), which
does `SELECT ... FOR UPDATE SKIP LOCKED` and the queued->provisioning
transition in one atomic statement.

supabase-py's `Client` is synchronous; every DB call here is offloaded to a
thread with `asyncio.to_thread` so it doesn't block the worker's event loop.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Literal, TypedDict

from dotenv import load_dotenv
from supabase import Client, create_client

# ============ enums (mirror supabase/migrations/0001_init.sql) ============

RunStatus = Literal[
    "queued",
    "provisioning",
    "detecting",
    "diagnosing",
    "fixing",
    "verifying",
    "reporting",
    "done",
    "failed",
    "canceled",
]

TestOutcome = Literal["passed", "failed", "error", "skipped", "timeout"]

ResultPhase = Literal["detect", "diagnose", "verify_before", "verify_after"]

FlakyStatus = Literal[
    "detected",
    "diagnosing",
    "diagnosed",
    "fixing",
    "fix_proposed",
    "verifying",
    "fix_verified",
    "fix_failed",
    "skipped",
]

RootCause = Literal[
    "async_race",
    "order_dependent",
    "time_dependent",
    "network_external",
    "randomness",
    "resource_leak",
    "concurrency_shared_state",
    "unknown",
]

RunEventLevel = Literal["info", "warn", "error", "success"]

LlmCallPurpose = Literal[
    "install_fix",
    "failure_parse",
    "root_cause",
    "patch_gen",
    "patch_review",
    "report",
    "tavily_summarize",
]

SandboxOpKind = Literal["create_env", "run", "fork_run", "read_file", "write_file"]
SandboxOpStatus = Literal["ok", "error", "timeout"]


# ============ typed insert payloads (columns only; id/defaults are server-generated) ============


class TestStatInsert(TypedDict, total=False):
    run_id: str
    test_id: str
    file_path: str
    pass_count: int
    fail_count: int
    error_count: int
    timeout_count: int
    mean_duration_ms: int | None
    is_flaky: bool
    is_always_failing: bool


class TestResultInsert(TypedDict, total=False):
    run_id: str
    test_id: str
    phase: ResultPhase
    branch_index: int
    perturbation: str  # 'none' | Perturbation
    outcome: TestOutcome
    duration_ms: int | None
    failure_message: str | None
    failure_log: str | None


class FlakyTestInsert(TypedDict, total=False):
    run_id: str
    test_id: str
    file_path: str
    failure_rate: float
    status: FlakyStatus
    root_cause: RootCause | None
    confidence: float | None
    diagnosis_md: str | None
    evidence: dict[str, Any] | None
    known_reports: list[dict[str, Any]] | None
    fix_patch: str | None
    fix_rationale_md: str | None
    verify_before_failures: int | None
    verify_after_failures: int | None
    verify_total: int | None


class LlmCallInsert(TypedDict, total=False):
    run_id: str | None
    stage: str
    purpose: LlmCallPurpose
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int | None
    ok: bool


class SandboxOpInsert(TypedDict, total=False):
    run_id: str
    kind: SandboxOpKind
    label: str | None
    image_in: str | None
    image_out: str | None
    exit_code: int | None
    duration_ms: int | None
    status: SandboxOpStatus


# ============ client ============


def get_client() -> Client:
    """Return a Supabase client authenticated with the service-role key.

    Reads SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY from the environment
    (loading worker/.env via python-dotenv if present).
    """
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not service_role_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set (see worker/.env.example)"
        )
    return create_client(url, service_role_key)


# ============ run claiming & status ============


async def claim_next_queued_run(client: Client) -> dict[str, Any] | None:
    """Atomically claim the oldest queued run via the `claim_next_run()` RPC.

    The RPC does `SELECT ... FOR UPDATE SKIP LOCKED` and transitions the
    claimed row queued -> provisioning (stamping started_at) in one
    statement, so concurrent worker processes never double-claim a run.
    Returns the claimed run row, or None if no run is queued.
    """

    def _call() -> dict[str, Any] | None:
        response = client.rpc("claim_next_run", {}).execute()
        rows = response.data or []
        return rows[0] if rows else None

    return await asyncio.to_thread(_call)


async def update_run_status(client: Client, run_id: str, status: RunStatus, **fields: Any) -> None:
    """Transition a run's status column and update any additional fields
    (e.g. error, env_image_id, totals, finished_at).
    """

    def _call() -> None:
        client.table("runs").update({"status": status, **fields}).eq("id", run_id).execute()

    await asyncio.to_thread(_call)


# ============ events ============


async def emit_event(
    client: Client,
    run_id: str,
    stage: str,
    level: RunEventLevel,
    message: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Write a structured row to run_events; the UI log console renders this
    table directly (no other channel for user-visible progress).
    """

    def _call() -> None:
        client.table("run_events").insert(
            {
                "run_id": run_id,
                "stage": stage,
                "level": level,
                "message": message,
                "payload": payload,
            }
        ).execute()

    await asyncio.to_thread(_call)


# ============ typed insert helpers ============


async def insert_test_stats(client: Client, rows: list[TestStatInsert]) -> list[dict[str, Any]]:
    """Bulk-insert test_stats aggregate rows (one per collected test per run)."""
    if not rows:
        return []

    def _call() -> list[dict[str, Any]]:
        return client.table("test_stats").insert(list(rows)).execute().data

    return await asyncio.to_thread(_call)


async def insert_test_results(client: Client, rows: list[TestResultInsert]) -> list[dict[str, Any]]:
    """Bulk-insert individual test_results rows (all results for flaky tests,
    failures only for everything else, per the retention rule in 02-DATABASE.md).
    """
    if not rows:
        return []

    def _call() -> list[dict[str, Any]]:
        return client.table("test_results").insert(list(rows)).execute().data

    return await asyncio.to_thread(_call)


async def insert_flaky_tests(client: Client, rows: list[FlakyTestInsert]) -> list[dict[str, Any]]:
    """Bulk-insert flaky_tests findings rows, returning the inserted rows
    (including server-generated ids) for later stage updates.
    """
    if not rows:
        return []

    def _call() -> list[dict[str, Any]]:
        return client.table("flaky_tests").insert(list(rows)).execute().data

    return await asyncio.to_thread(_call)


async def insert_llm_calls(client: Client, rows: list[LlmCallInsert]) -> list[dict[str, Any]]:
    """Bulk-insert llm_calls audit rows; powers the 'How we used Nemotron' UI panel."""
    if not rows:
        return []

    def _call() -> list[dict[str, Any]]:
        return client.table("llm_calls").insert(list(rows)).execute().data

    return await asyncio.to_thread(_call)


async def insert_sandbox_ops(client: Client, rows: list[SandboxOpInsert]) -> list[dict[str, Any]]:
    """Bulk-insert sandbox_ops audit rows; powers the branching-tree visualization."""
    if not rows:
        return []

    def _call() -> list[dict[str, Any]]:
        return client.table("sandbox_ops").insert(list(rows)).execute().data

    return await asyncio.to_thread(_call)
