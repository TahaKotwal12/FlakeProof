"""Real Token Factory Sandboxes (ConTree) executor.

Maps SandboxExecutor onto the Sandboxes API via the `contree-sdk` Python
package (docs/04-API.md B2 prefers the SDK over raw REST — it wraps
operations/polling for us). Raw `httpx` against the REST endpoints was the
documented fallback if the SDK "fights us"; it didn't — every method below
maps cleanly onto `contree_sdk.Contree`, so there's no REST-level code here.

Corrections against the live docs/SDK source, verified 2026-09-22 (see
`docs/01-ARCHITECTURE.md` — its `CONTREE_BASE_URL` example was a guess before
this; `worker/.env.example` now has the checked value):

- Sandboxes has its own base path, distinct from the inference API base:
  `https://api.tokenfactory.nebius.com/sandboxes/`
  (`contree_sdk._internals.utils.config.ContreeEndpoint.TOKEN_FACTORY_SANDBOXES`;
  cross-checked by triggering a real 403 and reading the request URL back).
- Auth is TWO headers, not one: `Authorization: Bearer {NEBIUS_API_KEY}` and
  `Project: {NEBIUS_PROJECT_ID}` (`contree_sdk.auth.IAMAuth.get_headers`).
- Sandboxes access is a separate grant from inference access. An
  inference-only Token Factory key authenticates fine (`whoami` succeeds) but
  gets `ForbiddenError` (403, "Insufficient permissions: list and spawn") on
  every actual call — confirmed live against this project's own key, which
  has all Sandboxes permissions (`import`/`spawn`/`list`/...) set to `False`.
  If `scripts/smoke_contree.py` fails with a 403, this is why — request
  Sandboxes beta access from Nebius; it is not automatic.
- The SDK's `run()` defaults to `disposable=True`, which discards the
  resulting image — useless for us, since every `RunResult.env` must be a
  checkpoint the pipeline can fork from later. Every call here passes
  `disposable=False` explicitly.
- The high-level SDK is a fluent builder, not spawn-then-poll: `image.run(...)`
  returns an unawaited, unexecuted copy; awaiting it is what spawns the
  instance, polls the operation, and populates `.exit_code`/`.stdout`/
  `.stderr`/`.uuid` (the new checkpoint). The old REST-level mental model
  (`POST /instances` -> poll an operation UUID) still exists underneath
  (`contree_sdk._internals.client.v1.instances`) but the SDK does it for us.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import TypeVar

from contree_sdk import Contree
from contree_sdk.auth import IAMAuth
from contree_sdk.config import ContreeConfig
from contree_sdk.sdk.exceptions import (
    ApiStatusCodeError,
    ApiTimeoutError,
    ContreeError,
    ContreeTransportError,
    OperationTimedOutError,
)
from contree_sdk.sdk.exceptions.api import (
    TooManyRequestsError,  # not re-exported from sdk.exceptions
)

from flakeproof import db
from flakeproof.executors.base import EnvHandle, RunResult, SandboxCommand

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

# Matches docs/03-PIPELINE.md RunConfig's `per_run_timeout_s` default — used by
# fork_and_run() when a caller doesn't pass a different budget per branch.
DEFAULT_TIMEOUT_S = 900

_DEFAULT_MAX_CONCURRENT_SANDBOXES = 10  # beta hard cap is 50; project default is lower


def _is_transient(exc: Exception) -> bool:
    """docs/04-API.md B2: "Treat every sandbox error as retryable once" — but only
    errors that might genuinely succeed on a second try. Permission/not-found/
    validation errors (403/404/422) are certain to fail identically again.
    """
    if isinstance(exc, (TooManyRequestsError, ApiTimeoutError, ContreeTransportError, OperationTimedOutError)):
        return True
    return isinstance(exc, ApiStatusCodeError) and exc.status is not None and exc.status >= 500


def _status_for(exc: Exception) -> db.SandboxOpStatus:
    if isinstance(exc, (OperationTimedOutError, ApiTimeoutError)):
        return "timeout"
    return "error"


def _build_client() -> Contree:
    """Nebius Token Factory Sandboxes client. `NEBIUS_API_KEY`/`NEBIUS_PROJECT_ID`
    are picked up automatically by `IAMAuth`'s own env resolution (its field
    defaults *are* those env var names — see contree_sdk.auth.IAMAuth); we only
    need to check they're actually set, and to apply `CONTREE_BASE_URL` if given.
    """
    if "NEBIUS_API_KEY" not in os.environ:
        raise RuntimeError("NEBIUS_API_KEY must be set (see worker/.env.example)")
    if "NEBIUS_PROJECT_ID" not in os.environ:
        raise RuntimeError("NEBIUS_PROJECT_ID must be set (see worker/.env.example)")

    base_url = os.environ.get("CONTREE_BASE_URL")
    auth = IAMAuth(base_url=base_url) if base_url else IAMAuth()
    return Contree(config=ContreeConfig(auth=auth))


class ContreeExecutor:
    """SandboxExecutor implementation backed by Token Factory Sandboxes (ConTree).

    `run_id` scopes checkpoint tags (`flakeproof/{run_id}/{label}-{seq}`) and is
    required for every `sandbox_ops` row this executor writes — the
    SandboxExecutor protocol has no per-call run context, so it's supplied once
    at construction, the same way `DockerExecutor` takes it (see
    `executors/docker_local.py`). Pass `db_client=None` (the default) to skip
    `sandbox_ops` logging entirely, e.g. from `scripts/smoke_contree.py`.
    """

    def __init__(
        self,
        run_id: str | None = None,
        *,
        db_client=None,  # type: ignore[no-untyped-def]  # supabase.Client — kept loose to avoid importing it just for a type
        client: Contree | None = None,
    ) -> None:
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self._db_client = db_client
        self._client = client or _build_client()
        self._next_seq = 0
        self._max_concurrent = int(os.environ.get("MAX_CONCURRENT_SANDBOXES", _DEFAULT_MAX_CONCURRENT_SANDBOXES))

    # ============ SandboxExecutor ============

    async def create_env(self, base_image: str) -> EnvHandle:
        start = time.monotonic()

        async def _do() -> object:
            return await self._client.images.docker(base_image)

        try:
            image = await self._with_one_retry("create_env", _do)
        except ContreeError as exc:
            await self._log_op(
                "create_env",
                f"create_env: {base_image}",
                image_in=None,
                image_out=None,
                exit_code=None,
                duration_ms=self._elapsed_ms(start),
                status=_status_for(exc),
            )
            raise

        # Tag the provision checkpoint so it's identifiable/retained in the
        # ConTree dashboard (docs/04-API.md B2: "Tag the provision checkpoint
        # ... so it survives cleanup"). Best-effort: tagging needs
        # `set_image_tag` permission separately from `import`/`spawn`, and a
        # failure here shouldn't block the run over a cosmetic label.
        tag = self._new_tag("base")
        try:
            image = await image.tag_as(tag)
        except ContreeError:
            logger.warning("Could not tag provision checkpoint %s as %s", image.uuid, tag, exc_info=True)

        image_id = str(image.uuid)
        await self._log_op(
            "create_env",
            f"create_env: {base_image}",
            image_in=base_image,
            image_out=image_id,
            exit_code=0,
            duration_ms=self._elapsed_ms(start),
            status="ok",
        )
        return EnvHandle(id=image_id)

    async def run(
        self,
        env: EnvHandle,
        command: str,
        *,
        timeout_s: int,
        env_vars: dict[str, str] | None = None,
    ) -> RunResult:
        return await self._execute(env, command, timeout_s=timeout_s, env_vars=env_vars, kind="run", label=command)

    async def fork_and_run(
        self,
        env: EnvHandle,
        commands: list[SandboxCommand],
        *,
        concurrency: int,
        timeout_s: int = DEFAULT_TIMEOUT_S,
    ) -> list[RunResult]:
        """THE branching primitive: N spawns from the SAME parent image, bounded
        by a semaphore. `concurrency` is clamped to `MAX_CONCURRENT_SANDBOXES`
        (default 10, hard beta ceiling 50) as a safety net — callers are
        expected to pass `concurrency=MAX_CONCURRENT_SANDBOXES` already, per
        docs/03-PIPELINE.md's own example.
        """
        limit = max(1, min(concurrency, self._max_concurrent))
        semaphore = asyncio.Semaphore(limit)

        async def _run_one(index: int, cmd: SandboxCommand) -> RunResult:
            async with semaphore:
                return await self._execute(
                    env,
                    cmd.command,
                    timeout_s=timeout_s,
                    env_vars=cmd.env_vars,
                    kind="fork_run",
                    label=f"fork #{index}: {cmd.command}",
                )

        return await asyncio.gather(*(_run_one(i, cmd) for i, cmd in enumerate(commands)))

    async def read_file(self, env: EnvHandle, path: str) -> str:
        start = time.monotonic()

        async def _do() -> bytes:
            image_ref = await self._client.images.use(env.id)
            return await image_ref.read(path)

        try:
            content = await self._with_one_retry(f"read_file {path}", _do)
        except ContreeError as exc:
            await self._log_op(
                "read_file",
                f"read {path}",
                image_in=env.id,
                image_out=None,
                exit_code=None,
                duration_ms=self._elapsed_ms(start),
                status=_status_for(exc),
            )
            raise

        await self._log_op(
            "read_file",
            f"read {path}",
            image_in=env.id,
            image_out=None,
            exit_code=None,
            duration_ms=self._elapsed_ms(start),
            status="ok",
        )
        return content.decode("utf-8", errors="replace")

    async def write_file(self, env: EnvHandle, path: str, content: str) -> EnvHandle:
        start = time.monotonic()

        async def _do() -> object:
            image_ref = await self._client.images.use(env.id)
            # apply_files bakes the file in via a disposable=False `run(shell="true")`
            # internally (contree_sdk.sdk.objects.image_like._base._apply_files) —
            # exactly "write a file, get a new checkpoint back".
            return await image_ref.apply_files({path: content.encode("utf-8")})

        try:
            result_image = await self._with_one_retry(f"write_file {path}", _do)
        except ContreeError as exc:
            await self._log_op(
                "write_file",
                f"write {path}",
                image_in=env.id,
                image_out=None,
                exit_code=None,
                duration_ms=self._elapsed_ms(start),
                status=_status_for(exc),
            )
            raise

        new_image_id = str(result_image.uuid)
        await self._log_op(
            "write_file",
            f"write {path}",
            image_in=env.id,
            image_out=new_image_id,
            exit_code=0,
            duration_ms=self._elapsed_ms(start),
            status="ok",
        )
        return EnvHandle(id=new_image_id)

    # ============ internals ============

    async def _execute(
        self,
        env: EnvHandle,
        command: str,
        *,
        timeout_s: int,
        env_vars: dict[str, str] | None,
        kind: db.SandboxOpKind,
        label: str,
    ) -> RunResult:
        tag = self._new_tag("run")
        start = time.monotonic()

        async def _do() -> object:
            image_ref = await self._client.images.use(env.id)
            prepared = image_ref.run(shell=command, env=env_vars, timeout=timeout_s, disposable=False, tag=tag)
            return await prepared

        try:
            result_image = await self._with_one_retry(label, _do)
        except ContreeError as exc:
            await self._log_op(
                kind,
                label,
                image_in=env.id,
                image_out=None,
                exit_code=None,
                duration_ms=self._elapsed_ms(start),
                status=_status_for(exc),
            )
            raise

        duration_ms = self._elapsed_ms(start)
        new_image_id = str(result_image.uuid)
        await self._log_op(
            kind,
            label,
            image_in=env.id,
            image_out=new_image_id,
            exit_code=result_image.exit_code,
            duration_ms=duration_ms,
            status="ok",
        )
        return RunResult(
            exit_code=result_image.exit_code,
            stdout=result_image.stdout,
            stderr=result_image.stderr,
            duration_s=duration_ms / 1000,
            env=EnvHandle(id=new_image_id),
        )

    async def _with_one_retry(self, label: str, coro_fn: Callable[[], Awaitable[_T]]) -> _T:
        """"One retry per transient error, then degrade" (per the task / docs/
        04-API.md B2) — this is the retry half; "degrade" (warn + skip rather
        than fail the whole run) is the calling stage's job once the error
        propagates, since that needs run_events/DB context this executor
        doesn't have.
        """
        try:
            return await coro_fn()
        except ContreeError as exc:
            if not _is_transient(exc):
                raise
            logger.warning("Transient ConTree error on %s, retrying once: %s", label, exc)
            return await coro_fn()

    def _new_tag(self, label: str) -> str:
        self._next_seq += 1
        return f"flakeproof/{self.run_id}/{label}-{self._next_seq}"

    @staticmethod
    def _elapsed_ms(start: float) -> int:
        return int((time.monotonic() - start) * 1000)

    async def _log_op(
        self,
        kind: db.SandboxOpKind,
        label: str,
        *,
        image_in: str | None,
        image_out: str | None,
        exit_code: int | None,
        duration_ms: int | None,
        status: db.SandboxOpStatus,
    ) -> None:
        """Log every call to `sandbox_ops` (docs/03-PIPELINE.md: "Record every call
        in sandbox_ops — this is both audit and the UI tree animation data").
        No-ops if this executor wasn't given a `db_client`. Never raises: losing
        one audit row is not worth failing the run over.
        """
        if self._db_client is None:
            return
        try:
            await db.insert_sandbox_ops(
                self._db_client,
                [
                    {
                        "run_id": self.run_id,
                        "kind": kind,
                        "label": label,
                        "image_in": image_in,
                        "image_out": image_out,
                        "exit_code": exit_code,
                        "duration_ms": duration_ms,
                        "status": status,
                    }
                ],
            )
        except Exception:
            logger.exception("Failed to write sandbox_ops row for %s", label)
