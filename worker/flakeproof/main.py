"""Poll loop entry point: claims queued runs and drives the pipeline state machine.

Run with `python -m flakeproof.main`.
"""

from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv
from supabase import Client

from flakeproof import db
from flakeproof.executors.base import SandboxExecutor
from flakeproof.executors.contree import ContreeExecutor
from flakeproof.executors.docker_local import DockerExecutor
from flakeproof.executors.mock import MockExecutor
from flakeproof.stages import (
    s0_intake,
    s1_provision,
    s2_detect,
    s3_diagnose,
    s4_fix,
    s5_verify,
    s6_report,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 2.0  # docs/06-CURSOR-PROMPTS.md Prompt 5: "poll loop (2s)"
_DEFAULT_MAX_ACTIVE_RUNS = 2
_RUN_TIMEOUT_S = 45 * 60  # docs/03-PIPELINE.md "Cancellation & timeouts": global 45-min wall clock

# Any run left in one of these when the worker starts belonged to a process
# that's no longer running -- reap_stale_runs() marks them failed.
_NON_TERMINAL_STATUSES = ("provisioning", "detecting", "diagnosing", "fixing", "verifying", "reporting")


def _max_active_runs() -> int:
    return int(os.environ.get("MAX_ACTIVE_RUNS", _DEFAULT_MAX_ACTIVE_RUNS))


def get_executor(run_id: str, db_client: Client) -> SandboxExecutor:
    """Select the sandbox backend from `EXECUTOR` (mock | docker | contree)."""
    kind = os.environ.get("EXECUTOR", "mock").strip().lower()
    if kind == "docker":
        return DockerExecutor(run_id=run_id)
    if kind == "contree":
        return ContreeExecutor(run_id=run_id, db_client=db_client)
    if kind == "mock":
        return MockExecutor()
    raise RuntimeError(f"Unknown EXECUTOR={kind!r} (expected mock | docker | contree)")


async def _check_canceled(db_client: Client, run_id: str) -> bool:
    """docs/03-PIPELINE.md: "the worker checks the status between waves and
    aborts gracefully" -- the cancel endpoint already sets status='canceled'
    itself; this just notices it before starting the next stage.
    """
    row = await db.get_run(db_client, run_id)
    if row["status"] == "canceled":
        await db.emit_event(db_client, run_id, "system", "warn", "Run canceled; stopping before the next stage.")
        return True
    return False


async def reap_stale_runs(db_client: Client) -> None:
    """On startup, fail any run stuck in a non-terminal, non-queued status --
    this process just started, so it can't be the one that was working on it.
    """

    def _fetch() -> list[dict]:
        return db_client.table("runs").select("id").in_("status", list(_NON_TERMINAL_STATUSES)).execute().data

    stale = await asyncio.to_thread(_fetch)
    for row in stale:
        run_id = row["id"]
        await db.update_run_status(db_client, run_id, "failed", error="worker_lost")
        await db.emit_event(db_client, run_id, "system", "error", "Worker restarted mid-run; marking this run failed.")
    if stale:
        logger.info("Reaped %d stale run(s) on startup", len(stale))


async def _drive_stages(run_id: str, db_client: Client, executor: SandboxExecutor) -> None:
    if await _check_canceled(db_client, run_id):
        return
    await s0_intake.run(run_id, db_client)

    if await _check_canceled(db_client, run_id):
        return
    env = await s1_provision.run(run_id, executor, db_client)

    if await _check_canceled(db_client, run_id):
        return
    run_row = await db.get_run(db_client, run_id)
    config = run_row.get("config") or {}
    flaky_nodeids = await s2_detect.run(run_id, executor, env, db_client, num_forks=int(config.get("detect_runs", 20)))

    if flaky_nodeids:
        if await _check_canceled(db_client, run_id):
            return
        diagnoses = await s3_diagnose.run(run_id, executor, env, flaky_nodeids, db_client)

        if await _check_canceled(db_client, run_id):
            return
        await s4_fix.run(run_id, executor, env, diagnoses, db_client)

        if await _check_canceled(db_client, run_id):
            return
        await s5_verify.run(run_id, executor, env, db_client, num_forks=int(config.get("verify_runs", 20)))

    if await _check_canceled(db_client, run_id):
        return
    await s6_report.run(run_id, db_client)


async def run_pipeline(run_id: str) -> None:
    """Execute stages s0 through s6 in order for a single run, updating status
    and emitting events as it goes. Never raises: every failure path here
    marks the run `failed` and returns, so one bad run can't take down the
    poll loop or leave a run stuck in a non-terminal status forever.
    """
    db_client = db.get_client()
    executor = get_executor(run_id, db_client)
    try:
        await asyncio.wait_for(_drive_stages(run_id, db_client, executor), timeout=_RUN_TIMEOUT_S)
    except TimeoutError:
        current = await db.get_run(db_client, run_id)
        if current["status"] not in ("failed", "canceled", "done"):
            await db.update_run_status(db_client, run_id, "failed", error="run_timeout")
            await db.emit_event(db_client, run_id, "system", "error", "Run exceeded the 45-minute budget and was stopped.")
    except Exception:
        logger.exception("run_pipeline(%s) crashed", run_id)
        current = await db.get_run(db_client, run_id)
        if current["status"] not in ("failed", "canceled", "done"):
            await db.update_run_status(db_client, run_id, "failed", error="internal_error")
            await db.emit_event(db_client, run_id, "system", "error", "The run crashed unexpectedly.")
    finally:
        if isinstance(executor, DockerExecutor):
            await executor.cleanup()


async def poll_loop() -> None:
    """Continuously poll Supabase for queued runs (up to MAX_ACTIVE_RUNS) and
    dispatch each to run_pipeline.
    """
    db_client = db.get_client()
    await reap_stale_runs(db_client)

    logger.info(
        "FlakeProof worker started (EXECUTOR=%s, MAX_ACTIVE_RUNS=%d)",
        os.environ.get("EXECUTOR", "mock"),
        _max_active_runs(),
    )

    active: dict[str, asyncio.Task[None]] = {}
    while True:
        active = {run_id: task for run_id, task in active.items() if not task.done()}

        if len(active) < _max_active_runs():
            claimed = await db.claim_next_queued_run(db_client)
            if claimed:
                run_id = claimed["id"]
                logger.info("Claimed run %s (%s/%s)", run_id, claimed.get("repo_owner"), claimed.get("repo_name"))
                active[run_id] = asyncio.create_task(run_pipeline(run_id))

        await asyncio.sleep(POLL_INTERVAL_S)


def main() -> None:
    """Synchronous entrypoint: load settings, then run poll_loop under asyncio."""
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(poll_loop())


if __name__ == "__main__":
    main()
