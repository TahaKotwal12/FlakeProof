"""Local Docker fallback executor for development without Sandboxes credits.

Approximates checkpoints with `docker commit` (slower, weaker isolation than
ConTree — dev only, not used in the judged demo).

LOCAL DEVELOPMENT ONLY. This shells out to the `docker` CLI on the machine the
worker runs on: no remote provisioning, no multi-tenant isolation beyond a
single container, and cleanup depends on `cleanup()` actually being called.
It exists so the pipeline can be exercised against a real (if slow, if weakly
isolated) sandbox before Token Factory Sandboxes credits/API access are
available — swap `EXECUTOR=contree` for the real thing.

Checkpoints are Docker image tags named `flakeproof/{run_id}:{seq}` (docs/
01-ARCHITECTURE.md "DockerExecutor approximates checkpoints with `docker
commit`"). Every image tag this executor creates for a run is tracked and
removed by `cleanup()`, which the caller must invoke once the run ends —
nothing here does that automatically, since the executor has no signal for
"the run is over."
"""

from __future__ import annotations

import asyncio
import tempfile
import time
import uuid
from pathlib import Path

from flakeproof.executors.base import EnvHandle, RunResult, SandboxCommand

IMAGE_TAG_PREFIX = "flakeproof"

# Matches docs/03-PIPELINE.md RunConfig's `per_run_timeout_s` default — used by
# fork_and_run() when a caller doesn't need a different budget per branch.
DEFAULT_TIMEOUT_S = 900

_SETUP_TIMEOUT_S = 60.0  # pull/tag/create/cp/commit — administrative commands, not test runs


class DockerCommandError(RuntimeError):
    """A `docker` CLI invocation exited non-zero when success was required."""

    def __init__(self, args: list[str], returncode: int, stderr: str) -> None:
        super().__init__(f"docker {' '.join(args)} failed (exit {returncode}): {stderr.strip()}")
        self.args_ = args
        self.returncode = returncode
        self.stderr = stderr


class DockerExecutor:
    """SandboxExecutor implementation backed by local Docker. See module docstring."""

    def __init__(self, run_id: str | None = None, *, docker_bin: str = "docker") -> None:
        """`run_id` scopes image tags (`flakeproof/{run_id}:{seq}`) and `cleanup()`.

        Generates a random one if not given — the caller should pass the
        actual `runs.id` so tags are traceable back to a run and cleanup is
        scoped to only that run's images.
        """
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self._docker_bin = docker_bin
        self._next_seq = 0
        self._created_tags: list[str] = []

    # ============ SandboxExecutor ============

    async def create_env(self, base_image: str) -> EnvHandle:
        await self._exec_checked(["pull", base_image], timeout_s=_SETUP_TIMEOUT_S)
        tag = self._new_tag()
        await self._exec_checked(["tag", base_image, tag], timeout_s=_SETUP_TIMEOUT_S)
        self._created_tags.append(tag)
        return EnvHandle(id=tag)

    async def run(
        self,
        env: EnvHandle,
        command: str,
        *,
        timeout_s: int,
        env_vars: dict[str, str] | None = None,
    ) -> RunResult:
        container_name = self._container_name("run")
        env_args = [arg for k, v in (env_vars or {}).items() for arg in ("-e", f"{k}={v}")]
        run_args = ["run", "--name", container_name, *env_args, env.id, "sh", "-c", command]

        start = time.monotonic()
        try:
            exit_code, stdout, stderr = await self._exec(run_args, timeout_s=timeout_s)
        except TimeoutError:
            # `docker run` (without -d) streams until the container exits, so our
            # subprocess timing out means the container itself is still running —
            # stop it explicitly, or it lingers even though our await gave up.
            await self._exec(["kill", container_name], timeout_s=_SETUP_TIMEOUT_S)
            exit_code, stdout, stderr = 124, "", f"Command timed out after {timeout_s}s"
        duration_s = time.monotonic() - start

        try:
            new_tag = self._new_tag()
            await self._exec_checked(["commit", container_name, new_tag], timeout_s=_SETUP_TIMEOUT_S)
            self._created_tags.append(new_tag)
        finally:
            await self._exec(["rm", "-f", container_name], timeout_s=_SETUP_TIMEOUT_S)

        return RunResult(
            exit_code=exit_code, stdout=stdout, stderr=stderr, duration_s=duration_s, env=EnvHandle(id=new_tag)
        )

    async def fork_and_run(
        self,
        env: EnvHandle,
        commands: list[SandboxCommand],
        *,
        concurrency: int,
        timeout_s: int = DEFAULT_TIMEOUT_S,
    ) -> list[RunResult]:
        """THE branching primitive: N `docker run`s from the same checkpoint image,
        bounded by an `asyncio.Semaphore` so at most `concurrency` containers run
        at once (unlike ConTree, a laptop's CPU/memory is a real ceiling).
        """
        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def _run_one(cmd: SandboxCommand) -> RunResult:
            async with semaphore:
                return await self.run(env, cmd.command, timeout_s=timeout_s, env_vars=cmd.env_vars)

        return await asyncio.gather(*(_run_one(cmd) for cmd in commands))

    async def read_file(self, env: EnvHandle, path: str) -> str:
        container_name = self._container_name("read")
        await self._exec_checked(["create", "--name", container_name, env.id], timeout_s=_SETUP_TIMEOUT_S)
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                local_path = Path(tmp_dir) / "out"
                await self._exec_checked(
                    ["cp", f"{container_name}:{path}", str(local_path)], timeout_s=_SETUP_TIMEOUT_S
                )
                return local_path.read_text(encoding="utf-8", errors="replace")
        finally:
            await self._exec(["rm", "-f", container_name], timeout_s=_SETUP_TIMEOUT_S)

    async def write_file(self, env: EnvHandle, path: str, content: str) -> EnvHandle:
        container_name = self._container_name("write")
        await self._exec_checked(["create", "--name", container_name, env.id], timeout_s=_SETUP_TIMEOUT_S)
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                local_path = Path(tmp_dir) / (Path(path).name or "in")
                local_path.write_text(content, encoding="utf-8")
                await self._exec_checked(
                    ["cp", str(local_path), f"{container_name}:{path}"], timeout_s=_SETUP_TIMEOUT_S
                )

            new_tag = self._new_tag()
            await self._exec_checked(["commit", container_name, new_tag], timeout_s=_SETUP_TIMEOUT_S)
            self._created_tags.append(new_tag)
            return EnvHandle(id=new_tag)
        finally:
            await self._exec(["rm", "-f", container_name], timeout_s=_SETUP_TIMEOUT_S)

    # ============ cleanup ============

    async def cleanup(self) -> None:
        """Remove every image tag this executor created for `run_id`. The caller
        must invoke this once the run ends (success, failure, or cancellation) —
        nothing here does it automatically. Best-effort: a tag that's already
        gone, or still referenced elsewhere, doesn't stop the rest from cleaning up.
        """
        for tag in self._created_tags:
            await self._exec(["rmi", "-f", tag], timeout_s=_SETUP_TIMEOUT_S)
        self._created_tags.clear()

    # ============ internals ============

    def _new_tag(self) -> str:
        self._next_seq += 1
        return f"{IMAGE_TAG_PREFIX}/{self.run_id}:{self._next_seq}"

    def _container_name(self, label: str) -> str:
        self._next_seq += 1
        return f"flakeproof-{label}-{self.run_id}-{self._next_seq}"

    async def _exec(self, args: list[str], *, timeout_s: float | None) -> tuple[int, str, str]:
        """Run `docker <args>`, returning (exit_code, stdout, stderr) regardless of
        exit code — used where a non-zero exit is meaningful data (the command
        under test failing), not an executor error.
        """
        proc = await asyncio.create_subprocess_exec(
            self._docker_bin, *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise
        exit_code = proc.returncode if proc.returncode is not None else -1
        return (
            exit_code,
            stdout_b.decode("utf-8", errors="replace"),
            stderr_b.decode("utf-8", errors="replace"),
        )

    async def _exec_checked(self, args: list[str], *, timeout_s: float | None) -> tuple[str, str]:
        """Like `_exec`, but raises `DockerCommandError` on a non-zero exit — for
        administrative commands (pull/tag/create/cp/commit) where failure is
        always our error, never test-command data.
        """
        exit_code, stdout, stderr = await self._exec(args, timeout_s=timeout_s)
        if exit_code != 0:
            raise DockerCommandError(args, exit_code, stderr)
        return stdout, stderr
