"""Local Docker fallback executor for development without Sandboxes credits.

Approximates checkpoints with `docker commit` (slower, weaker isolation than
ConTree — dev only, not used in the judged demo).
"""

from __future__ import annotations

from flakeproof.executors.base import EnvHandle, RunResult, SandboxCommand


class DockerExecutor:
    """SandboxExecutor implementation backed by local Docker."""

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
