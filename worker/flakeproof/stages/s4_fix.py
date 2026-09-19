"""Stage 4 — fix: generate a patch for each diagnosed flaky test and apply it
inside the sandbox. Patches touch test code and fixtures/conftest only.
"""

from __future__ import annotations

from supabase import Client

from flakeproof.executors.base import EnvHandle, SandboxExecutor


async def run(
    run_id: str,
    executor: SandboxExecutor,
    env: EnvHandle,
    diagnoses: dict[str, str],
    db_client: Client,
) -> EnvHandle:
    """Generate and apply a guarded patch per diagnosed test, returning the
    patched checkpoint.
    """
    raise NotImplementedError
