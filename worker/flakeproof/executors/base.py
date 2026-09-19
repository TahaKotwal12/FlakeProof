"""The SandboxExecutor interface: everything that touches a sandbox goes through this.

Implementations: ContreeExecutor (real Token Factory Sandboxes), DockerExecutor
(local Docker fallback), MockExecutor (scripted fake runs).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EnvHandle:
    """Handle to a sandbox checkpoint — a node in the git-like execution tree."""

    id: str


@dataclass(frozen=True)
class SandboxCommand:
    """A single shell command to run inside one forked branch of fork_and_run."""

    command: str
    env_vars: dict[str, str] | None = None


@dataclass(frozen=True)
class RunResult:
    """Result of running a command in a sandbox, including the checkpoint it produced."""

    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    env: EnvHandle


class SandboxExecutor(Protocol):
    """Everything the pipeline needs from a sandbox provider."""

    async def create_env(self, base_image: str) -> EnvHandle:
        """Start from a base image (e.g. python:3.12-slim). Returns handle to current checkpoint."""
        ...

    async def run(
        self,
        env: EnvHandle,
        command: str,
        *,
        timeout_s: int,
        env_vars: dict[str, str] | None = None,
    ) -> RunResult:
        """Execute a shell command from the given checkpoint.

        Returns exit code, stdout, stderr, duration, and the NEW checkpoint handle
        produced by the run (git-like: every run = new node).
        """
        ...

    async def fork_and_run(
        self,
        env: EnvHandle,
        commands: list[SandboxCommand],
        *,
        concurrency: int,
    ) -> list[RunResult]:
        """THE branching primitive: run N commands in parallel, each in its own fork
        of the SAME checkpoint. Identical starting state for every branch.
        """
        ...

    async def read_file(self, env: EnvHandle, path: str) -> str:
        """Read a file's contents from the given checkpoint."""
        ...

    async def write_file(self, env: EnvHandle, path: str, content: str) -> EnvHandle:
        """Write a file's contents, returning the new checkpoint produced by the write."""
        ...
