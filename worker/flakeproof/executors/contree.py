"""Real Token Factory Sandboxes (ConTree) executor.

Maps SandboxExecutor onto the Sandboxes API: spawn instance from image, poll
operation, read artifacts/files, fork = spawn N instances from the same
checkpoint image id. Endpoints documented in docs/04-API.md.
"""

from __future__ import annotations

from flakeproof.executors.base import EnvHandle, RunResult, SandboxCommand


class ContreeExecutor:
    """SandboxExecutor implementation backed by Token Factory Sandboxes (ConTree)."""

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
