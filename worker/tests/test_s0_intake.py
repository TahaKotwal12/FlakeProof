"""Unit tests for the pure/semi-pure helpers in flakeproof.stages.s0_intake:
pytest-test-file detection, repo/size/fork checks, and pytest-stack detection
against a stubbed GitHub API (httpx) -- no real network calls.
"""

from __future__ import annotations

from typing import Any, Self

import httpx
import pytest

from flakeproof.stages import s0_intake as s0


def test_looks_like_pytest_test_file_matches_tests_dir() -> None:
    assert s0._looks_like_pytest_test_file("tests/test_api.py")
    assert s0._looks_like_pytest_test_file("pkg/tests/test_nested.py")


def test_looks_like_pytest_test_file_matches_test_dir_singular() -> None:
    assert s0._looks_like_pytest_test_file("test/test_api.py")


def test_looks_like_pytest_test_file_rejects_non_test_files() -> None:
    assert not s0._looks_like_pytest_test_file("tests/conftest.py")
    assert not s0._looks_like_pytest_test_file("src/app.py")
    assert not s0._looks_like_pytest_test_file("test_api.py")  # no directory at all


class _FakeResponse:
    def __init__(self, status_code: int, json_data: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=httpx.Request("GET", "https://x"), response=httpx.Response(self.status_code))

    def json(self) -> Any:
        return self._json_data


class _FakeAsyncClient:
    def __init__(self, responses: dict[str, _FakeResponse]) -> None:
        self._responses = responses
        self.requested: list[str] = []

    async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.requested.append(url)
        for prefix, response in self._responses.items():
            if url.startswith(prefix):
                return response
        raise AssertionError(f"Unexpected request: {url}")

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False


@pytest.mark.asyncio
async def test_fetch_repo_rejects_404() -> None:
    client = _FakeAsyncClient({"https://api.github.com/repos/o/r": _FakeResponse(404)})
    with pytest.raises(s0.IntakeFailedError) as exc_info:
        await s0._fetch_repo(client, "o", "r")
    assert exc_info.value.code == "repo_not_found"


@pytest.mark.asyncio
async def test_fetch_repo_rejects_private() -> None:
    client = _FakeAsyncClient({"https://api.github.com/repos/o/r": _FakeResponse(200, {"private": True})})
    with pytest.raises(s0.IntakeFailedError) as exc_info:
        await s0._fetch_repo(client, "o", "r")
    assert exc_info.value.code == "repo_private"


@pytest.mark.asyncio
async def test_fetch_repo_rejects_too_large() -> None:
    client = _FakeAsyncClient(
        {"https://api.github.com/repos/o/r": _FakeResponse(200, {"private": False, "size": 999_999})}
    )
    with pytest.raises(s0.IntakeFailedError) as exc_info:
        await s0._fetch_repo(client, "o", "r")
    assert exc_info.value.code == "repo_too_large"


@pytest.mark.asyncio
async def test_fetch_repo_rejects_unstarred_fork_of_huge_upstream() -> None:
    client = _FakeAsyncClient(
        {
            "https://api.github.com/repos/o/r": _FakeResponse(
                200,
                {
                    "private": False,
                    "size": 10,
                    "fork": True,
                    "stargazers_count": 0,
                    "parent": {"size": 999_999},
                },
            )
        }
    )
    with pytest.raises(s0.IntakeFailedError) as exc_info:
        await s0._fetch_repo(client, "o", "r")
    assert exc_info.value.code == "unsupported_stack"


@pytest.mark.asyncio
async def test_fetch_repo_allows_starred_fork_of_huge_upstream() -> None:
    client = _FakeAsyncClient(
        {
            "https://api.github.com/repos/o/r": _FakeResponse(
                200,
                {
                    "private": False,
                    "size": 10,
                    "fork": True,
                    "stargazers_count": 5,
                    "parent": {"size": 999_999},
                    "default_branch": "main",
                },
            )
        }
    )
    data = await s0._fetch_repo(client, "o", "r")
    assert data["default_branch"] == "main"


@pytest.mark.asyncio
async def test_fetch_repo_allows_normal_public_repo() -> None:
    client = _FakeAsyncClient(
        {"https://api.github.com/repos/o/r": _FakeResponse(200, {"private": False, "size": 100, "default_branch": "main"})}
    )
    data = await s0._fetch_repo(client, "o", "r")
    assert data["default_branch"] == "main"


@pytest.mark.asyncio
async def test_resolve_commit_sha_rejects_missing_ref() -> None:
    client = _FakeAsyncClient({"https://api.github.com/repos/o/r/commits/bogus": _FakeResponse(404)})
    with pytest.raises(s0.IntakeFailedError) as exc_info:
        await s0._resolve_commit_sha(client, "o", "r", "bogus")
    assert exc_info.value.code == "repo_not_found"


@pytest.mark.asyncio
async def test_resolve_commit_sha_returns_sha() -> None:
    client = _FakeAsyncClient(
        {"https://api.github.com/repos/o/r/commits/main": _FakeResponse(200, {"sha": "abc123"})}
    )
    assert await s0._resolve_commit_sha(client, "o", "r", "main") == "abc123"


@pytest.mark.asyncio
async def test_detect_pytest_true_via_pytest_ini() -> None:
    client = _FakeAsyncClient({})
    paths = ["pytest.ini", "src/app.py"]
    assert await s0._detect_pytest(client, "o", "r", "sha", paths)


@pytest.mark.asyncio
async def test_detect_pytest_true_via_tests_dir() -> None:
    client = _FakeAsyncClient({})
    paths = ["src/app.py", "tests/test_app.py"]
    assert await s0._detect_pytest(client, "o", "r", "sha", paths)


@pytest.mark.asyncio
async def test_detect_pytest_true_via_pyproject_mentioning_pytest() -> None:
    client = _FakeAsyncClient(
        {
            "https://raw.githubusercontent.com/o/r/sha/pyproject.toml": _FakeResponse(
                200, text="[project]\ndependencies = ['pytest']"
            )
        }
    )
    paths = ["pyproject.toml", "src/app.py"]
    assert await s0._detect_pytest(client, "o", "r", "sha", paths)


@pytest.mark.asyncio
async def test_detect_pytest_false_when_no_signal() -> None:
    client = _FakeAsyncClient(
        {"https://raw.githubusercontent.com/o/r/sha/pyproject.toml": _FakeResponse(200, text="[project]\nname='x'")}
    )
    paths = ["pyproject.toml", "src/app.js"]
    assert not await s0._detect_pytest(client, "o", "r", "sha", paths)
