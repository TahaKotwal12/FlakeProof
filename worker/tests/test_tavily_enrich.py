"""Unit tests for flakeproof.tavily_enrich: the TAVILY_API_KEY feature flag,
raw search parsing/error handling (stubbed httpx), and TavilyEnrichment's
per-(repo,test) cache + 2-search budget (stubbed search + llm.run) -- no
real network or LLM calls.
"""

from __future__ import annotations

from typing import Any, Self

import httpx
import pytest

from flakeproof import llm, tavily_enrich


@pytest.fixture(autouse=True)
def _no_key_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)


# ============ is_enabled() ============


def test_is_enabled_false_without_key() -> None:
    assert tavily_enrich.is_enabled() is False


def test_is_enabled_true_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "tk-test")
    assert tavily_enrich.is_enabled() is True


# ============ search_known_issue() ============


@pytest.mark.asyncio
async def test_search_known_issue_returns_empty_without_key() -> None:
    assert await tavily_enrich.search_known_issue("some query") == []


class _FakeResponse:
    def __init__(self, json_data: dict[str, Any]) -> None:
        self._json_data = json_data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._json_data


class _FakeAsyncClient:
    last_request: dict[str, Any] | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        _FakeAsyncClient.last_request = {"url": url, **kwargs}
        return _FakeResponse(
            {
                "results": [
                    {"title": "Flaky test_retry on CI", "url": "https://github.com/o/r/issues/1", "content": "..."},
                    {"title": "no url here", "content": "should be dropped"},
                ]
            }
        )


@pytest.mark.asyncio
async def test_search_known_issue_parses_results_and_sends_expected_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "tk-test")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    results = await tavily_enrich.search_known_issue('"o/r" "test_retry" flaky OR intermittent')

    assert results == [{"title": "Flaky test_retry on CI", "url": "https://github.com/o/r/issues/1", "content": "..."}]
    assert _FakeAsyncClient.last_request["url"] == tavily_enrich.TAVILY_SEARCH_URL
    assert _FakeAsyncClient.last_request["headers"]["Authorization"] == "Bearer tk-test"
    assert _FakeAsyncClient.last_request["json"]["query"] == '"o/r" "test_retry" flaky OR intermittent'
    assert _FakeAsyncClient.last_request["json"]["include_domains"] == ["github.com", "stackoverflow.com"]


class _RaisingAsyncClient(_FakeAsyncClient):
    async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        raise httpx.HTTPError("connection reset")


@pytest.mark.asyncio
async def test_search_known_issue_returns_empty_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "tk-test")
    monkeypatch.setattr(httpx, "AsyncClient", _RaisingAsyncClient)

    assert await tavily_enrich.search_known_issue("query") == []


# ============ TavilyEnrichment.enrich() ============


@pytest.mark.asyncio
async def test_enrich_skips_entirely_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom(*args: Any, **kwargs: Any) -> list[dict[str, str]]:
        raise AssertionError("search_known_issue should not be called when the feature flag is off")

    monkeypatch.setattr(tavily_enrich, "search_known_issue", _boom)
    enrichment = tavily_enrich.TavilyEnrichment()

    result = await enrichment.enrich(owner="o", repo="r", test_id="t.py::test_x", db_client=object(), run_id="run1", stage="s3")
    assert result == []


def _stub_llm_run(known_reports: list[dict[str, str]], *, ok: bool = True) -> Any:
    async def _run(db_client: Any, purpose: str, template_vars: dict[str, Any], *, run_id: str, stage: str) -> Any:
        return llm.ChatResult(ok=ok, purpose=purpose, content="{}", data={"known_reports": known_reports} if ok else None)

    return _run


@pytest.mark.asyncio
async def test_enrich_caches_successful_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "tk-test")
    search_calls = 0

    async def _search(query: str, **kwargs: Any) -> list[dict[str, str]]:
        nonlocal search_calls
        search_calls += 1
        return [{"title": "t", "url": "https://github.com/o/r/issues/1", "content": "c"}]

    monkeypatch.setattr(tavily_enrich, "search_known_issue", _search)
    monkeypatch.setattr(
        llm, "run", _stub_llm_run([{"title": "t", "url": "https://github.com/o/r/issues/1", "snippet": "s", "relevance": "r"}])
    )

    enrichment = tavily_enrich.TavilyEnrichment()
    first = await enrichment.enrich(owner="o", repo="r", test_id="t.py::test_x", db_client=object(), run_id="run1", stage="s3")
    second = await enrichment.enrich(owner="o", repo="r", test_id="t.py::test_x", db_client=object(), run_id="run1", stage="s3")

    assert first == [{"title": "t", "url": "https://github.com/o/r/issues/1", "snippet": "s", "relevance": "r"}]
    assert second == first
    assert search_calls == 1  # second call served from cache, no new search


@pytest.mark.asyncio
async def test_enrich_retries_empty_search_up_to_budget_then_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "tk-test")
    search_calls = 0

    async def _search(query: str, **kwargs: Any) -> list[dict[str, str]]:
        nonlocal search_calls
        search_calls += 1
        return []  # never finds anything

    monkeypatch.setattr(tavily_enrich, "search_known_issue", _search)
    enrichment = tavily_enrich.TavilyEnrichment()

    for _ in range(5):
        result = await enrichment.enrich(owner="o", repo="r", test_id="t.py::test_x", db_client=object(), run_id="run1", stage="s3")
        assert result == []

    assert search_calls == tavily_enrich._MAX_SEARCHES_PER_TEST


@pytest.mark.asyncio
async def test_enrich_does_not_cache_llm_failure_but_respects_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "tk-test")

    async def _search(query: str, **kwargs: Any) -> list[dict[str, str]]:
        return [{"title": "t", "url": "https://github.com/o/r/issues/1", "content": "c"}]

    monkeypatch.setattr(tavily_enrich, "search_known_issue", _search)
    monkeypatch.setattr(llm, "run", _stub_llm_run([], ok=False))

    enrichment = tavily_enrich.TavilyEnrichment()
    for _ in range(5):
        result = await enrichment.enrich(owner="o", repo="r", test_id="t.py::test_x", db_client=object(), run_id="run1", stage="s3")
        assert result == []

    assert enrichment._search_counts[("o/r", "t.py::test_x")] == tavily_enrich._MAX_SEARCHES_PER_TEST


@pytest.mark.asyncio
async def test_enrich_scopes_cache_and_budget_per_repo_and_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "tk-test")
    search_calls: list[str] = []

    async def _search(query: str, **kwargs: Any) -> list[dict[str, str]]:
        search_calls.append(query)
        return []

    monkeypatch.setattr(tavily_enrich, "search_known_issue", _search)
    enrichment = tavily_enrich.TavilyEnrichment()

    await enrichment.enrich(owner="o", repo="r", test_id="t.py::test_a", db_client=object(), run_id="run1", stage="s3")
    await enrichment.enrich(owner="o", repo="r", test_id="t.py::test_b", db_client=object(), run_id="run1", stage="s3")

    # Two distinct tests each get their own budget -- not a shared counter.
    assert len(search_calls) == 2
