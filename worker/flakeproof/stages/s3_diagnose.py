"""Stage 3 — diagnose: run the perturbation matrix per flaky test and classify
root cause with Nemotron, backed by evidence from the forked runs.
"""

from __future__ import annotations

from supabase import Client

from flakeproof.executors.base import EnvHandle, SandboxExecutor


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
    raise NotImplementedError
