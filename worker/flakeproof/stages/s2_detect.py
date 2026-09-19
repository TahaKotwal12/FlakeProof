"""Stage 2 — detect: fork the baseline checkpoint N times and run the suite in
parallel to prove flakiness (same code + same starting state, different outcomes).
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
) -> list[str]:
    """Run the full suite across `num_forks` identical forks and return the nodeids
    of tests proven flaky (inconsistent pass/fail across forks).
    """
    raise NotImplementedError
