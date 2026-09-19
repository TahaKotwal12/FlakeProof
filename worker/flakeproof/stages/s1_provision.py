"""Stage 1 — provision: clone the repo, install it, and checkpoint the environment."""

from __future__ import annotations

from supabase import Client

from flakeproof.executors.base import EnvHandle, SandboxExecutor


async def run(run_id: str, executor: SandboxExecutor, db_client: Client) -> EnvHandle:
    """Clone the target repo, install it inside a sandbox (agent-assisted), and
    return the baseline checkpoint used by all later stages.
    """
    raise NotImplementedError
