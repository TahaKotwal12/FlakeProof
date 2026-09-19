"""Scripted fake sandbox executor for offline UI development and worker tests.

Replays a scripted scenario matching the demo repo, with realistic delays, so
the full pipeline and UI can be built end-to-end before Sandboxes credits or
the ConTree API are available.
"""

from __future__ import annotations

from flakeproof.executors.base import EnvHandle, RunResult, SandboxCommand


class MockExecutor:
    """SandboxExecutor implementation that replays a scripted scenario."""

    async def create_env(self, base_image: str) -> EnvHandle:
        raise NotImplementedError

    async def run(
        self,
        env: EnvHandle,
        command: str,
        *,
        timeout_s: int,
        env_vars: dict[str, str] | None = None,
    ) -> RunResult:
        raise NotImplementedError

    async def fork_and_run(
        self,
        env: EnvHandle,
        commands: list[SandboxCommand],
        *,
        concurrency: int,
    ) -> list[RunResult]:
        raise NotImplementedError

    async def read_file(self, env: EnvHandle, path: str) -> str:
        raise NotImplementedError

    async def write_file(self, env: EnvHandle, path: str, content: str) -> EnvHandle:
        raise NotImplementedError
