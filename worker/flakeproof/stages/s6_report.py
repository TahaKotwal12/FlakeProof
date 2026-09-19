"""Stage 6 — report: assemble the final Flake Report (JSON/Markdown) and mark
the run complete.
"""

from __future__ import annotations

from supabase import Client


async def run(run_id: str, db_client: Client) -> None:
    """Render the report artifacts and transition the run to `completed`."""
    raise NotImplementedError
