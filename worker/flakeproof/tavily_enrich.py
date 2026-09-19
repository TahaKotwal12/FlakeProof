"""Optional enrichment of diagnosis results via the Tavily search API.

Feature-flagged on TAVILY_API_KEY being set; used to surface known-issue
context (e.g. upstream bug reports) alongside a root-cause diagnosis.
"""

from __future__ import annotations


async def search_known_issue(query: str) -> list[dict[str, str]]:
    """Search Tavily for known issues/discussions matching a flaky-test root cause query."""
    raise NotImplementedError
