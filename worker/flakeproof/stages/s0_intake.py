"""Stage 0 — intake: validate the submitted repo URL/config and initialize the run."""

from __future__ import annotations

from supabase import Client


async def run(run_id: str, db_client: Client) -> None:
    """Validate inputs and transition the run from `queued` to `provisioning`."""
    raise NotImplementedError
