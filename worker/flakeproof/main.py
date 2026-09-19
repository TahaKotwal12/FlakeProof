"""Poll loop entry point: claims queued runs and drives the pipeline state machine.

Run with `python -m flakeproof.main`.
"""

from __future__ import annotations


async def poll_loop() -> None:
    """Continuously poll Supabase for queued runs (up to MAX_ACTIVE_RUNS) and
    dispatch each to run_pipeline.
    """
    raise NotImplementedError


async def run_pipeline(run_id: str) -> None:
    """Execute stages s0 through s6 in order for a single run, updating status
    and emitting events as it goes.
    """
    raise NotImplementedError


def main() -> None:
    """Synchronous entrypoint: load settings, then run poll_loop under asyncio."""
    raise NotImplementedError


if __name__ == "__main__":
    main()
