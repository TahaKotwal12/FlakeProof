"""Optional enrichment of diagnosis results via the Tavily Search API
(docs/04-API.md B3, docs/05-LLM-PROMPTS.md P7): a bonus-prize integration,
never a hard requirement for diagnosis to proceed.

Feature-flagged on `TAVILY_API_KEY` being set (and `config.tavily_enrichment`
not explicitly `false`); skipped silently otherwise. `TavilyEnrichment`
caches results per `(repo, test)` for the lifetime of one S3 run and enforces
a strict budget of at most 2 raw Tavily searches per flaky test
(docs/06-CURSOR-PROMPTS.md Prompt 11).
"""

from __future__ import annotations

import json
import os

import httpx
from supabase import Client

from flakeproof import llm

TAVILY_SEARCH_URL = "https://api.tavily.com/search"

_REQUEST_TIMEOUT_S = 20.0
_MAX_RESULTS = 5  # docs/04-API.md B3: "max_results": 5
_MAX_KNOWN_REPORTS = 3  # docs/04-API.md B3: "summarized ... into known_reports (<= 3 items)"
_MAX_SEARCHES_PER_TEST = 2


def is_enabled() -> bool:
    """The feature flag: Tavily enrichment needs a real API key. Nothing else
    (config, budget, cache) matters if this is false.
    """
    return bool(os.environ.get("TAVILY_API_KEY"))


async def search_known_issue(query: str, *, max_results: int = _MAX_RESULTS) -> list[dict[str, str]]:
    """Raw Tavily search (docs/04-API.md B3's request/response shape). Returns
    `[]` on a missing key or any request/parse failure -- Tavily is a bonus
    enrichment, never worth failing a diagnosis over.
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return []

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_S) as client:
            response = await client.post(
                TAVILY_SEARCH_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "query": query,
                    "search_depth": "basic",
                    "max_results": max_results,
                    "include_domains": ["github.com", "stackoverflow.com"],
                },
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        return []

    return [
        {"title": str(r.get("title", "")), "url": str(r["url"]), "content": str(r.get("content", ""))}
        for r in data.get("results", [])
        if r.get("url")
    ]


class TavilyEnrichment:
    """One instance per S3 run: caches summarized `known_reports` per
    `(owner/repo, test_id)` and caps raw searches at `_MAX_SEARCHES_PER_TEST`
    for that same key, regardless of how many times `enrich()` is called for it.
    """

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], list[dict[str, str]]] = {}
        self._search_counts: dict[tuple[str, str], int] = {}

    async def enrich(
        self,
        *,
        owner: str,
        repo: str,
        test_id: str,
        db_client: Client,
        run_id: str,
        stage: str,
    ) -> list[dict[str, str]]:
        """Search + P7-summarize known reports for one flaky test. Returns `[]`
        immediately (no network call at all) when the feature flag is off.

        Only a genuine hit (non-empty `known_reports`) is cached -- a search
        that finds nothing, or an LLM summarization failure, is worth one
        retry (still within `_MAX_SEARCHES_PER_TEST`) rather than being
        remembered as a permanent miss.
        """
        if not is_enabled():
            return []

        key = (f"{owner}/{repo}", test_id)
        cached = self._cache.get(key)
        if cached:
            return cached
        if self._search_counts.get(key, 0) >= _MAX_SEARCHES_PER_TEST:
            return []

        test_name = test_id.rsplit("::", 1)[-1]
        query = f'"{owner}/{repo}" "{test_name}" flaky OR intermittent'
        self._search_counts[key] = self._search_counts.get(key, 0) + 1

        raw_results = await search_known_issue(query)
        if not raw_results:
            return []

        p7_result = await llm.run(
            db_client,
            "tavily_summarize",
            {"test_id": test_id, "owner": owner, "repo": repo, "results_json": json.dumps(raw_results)},
            run_id=run_id,
            stage=stage,
        )
        if not p7_result.ok or p7_result.data is None:
            return []

        known_reports = [
            {
                "title": str(r.get("title", "")),
                "url": str(r["url"]),
                "snippet": str(r.get("snippet", ""))[:200],
                "relevance": str(r.get("relevance", "")),
            }
            for r in (p7_result.data.get("known_reports") or [])
            if r.get("url")
        ][:_MAX_KNOWN_REPORTS]

        if known_reports:
            self._cache[key] = known_reports
        return known_reports
