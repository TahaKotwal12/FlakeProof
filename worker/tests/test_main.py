"""Unit tests for flakeproof.main's pure/semi-pure helpers: the EXECUTOR
factory and the cancellation check (stubbed db) -- no real Docker/ConTree/DB.
"""

from __future__ import annotations

from typing import Any

import pytest

from flakeproof import main
from flakeproof.executors.contree import ContreeExecutor
from flakeproof.executors.docker_local import DockerExecutor
from flakeproof.executors.mock import MockExecutor


def test_get_executor_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECUTOR", "docker")
    executor = main.get_executor("run-1", db_client=object())
    assert isinstance(executor, DockerExecutor)
    assert executor.run_id == "run-1"


def test_get_executor_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECUTOR", "mock")
    assert isinstance(main.get_executor("run-1", db_client=object()), MockExecutor)


def test_get_executor_contree(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECUTOR", "contree")
    monkeypatch.setenv("NEBIUS_API_KEY", "k")
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "p")
    executor = main.get_executor("run-1", db_client=object())
    assert isinstance(executor, ContreeExecutor)
    assert executor.run_id == "run-1"


def test_get_executor_defaults_to_mock_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXECUTOR", raising=False)
    assert isinstance(main.get_executor("run-1", db_client=object()), MockExecutor)


def test_get_executor_rejects_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECUTOR", "bogus")
    with pytest.raises(RuntimeError, match="Unknown EXECUTOR"):
        main.get_executor("run-1", db_client=object())


class _StubClient:
    """Minimal stand-in for supabase.Client covering only what
    db.get_run()/db.emit_event() touch, so _check_canceled is testable
    without a real Supabase connection.
    """

    def __init__(self, status: str) -> None:
        self.status = status
        self.events: list[dict[str, Any]] = []

    def table(self, name: str) -> _StubTable:
        return _StubTable(self, name)


class _StubTable:
    def __init__(self, client: _StubClient, name: str) -> None:
        self._client = client
        self._name = name
        self._insert_payload: dict[str, Any] | None = None

    def select(self, *_args: Any) -> _StubTable:
        return self

    def eq(self, *_args: Any) -> _StubTable:
        return self

    def insert(self, payload: dict[str, Any]) -> _StubTable:
        self._insert_payload = payload
        return self

    def single(self) -> _StubTable:
        return self

    def execute(self) -> Any:
        if self._name == "runs":
            return type("Resp", (), {"data": {"id": "run-1", "status": self._client.status}})()
        if self._name == "run_events":
            self._client.events.append(self._insert_payload or {})
            return type("Resp", (), {"data": [self._insert_payload]})()
        raise AssertionError(f"Unexpected table: {self._name}")


@pytest.mark.asyncio
async def test_check_canceled_true_and_emits_event() -> None:
    client = _StubClient(status="canceled")
    result = await main._check_canceled(client, "run-1")
    assert result is True
    assert len(client.events) == 1
    assert client.events[0]["level"] == "warn"


@pytest.mark.asyncio
async def test_check_canceled_false_for_active_run() -> None:
    client = _StubClient(status="detecting")
    result = await main._check_canceled(client, "run-1")
    assert result is False
    assert client.events == []
