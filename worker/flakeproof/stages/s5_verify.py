"""Stage 5 — verify: re-run each fixed test across fresh forks under its
triggering condition to prove the fix ("Before: 7/20 failed. After: 0/20.").
"""

from __future__ import annotations

from supabase import Client

from flakeproof.executors.base import EnvHandle, SandboxExecutor


async def run(
    run_id: str,
    executor: SandboxExecutor,
    env: EnvHandle,
    db_client: Client,
    *,
    num_forks: int = 20,
) -> dict[str, tuple[int, int]]:
    """Return {nodeid: (failures_before, failures_after)} verification scoreboard."""
    raise NotImplementedError
