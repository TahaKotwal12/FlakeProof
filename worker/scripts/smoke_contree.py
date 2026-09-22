#!/usr/bin/env python
"""Smoke test: proves branch isolation via Token Factory Sandboxes.

Creates one checkpoint, runs a trivial command on it, then forks 3 parallel
branches from that SAME checkpoint, each printing a random number. Different
outputs + different resulting image ids from an identical starting state is
the proof that forking actually isolates branches (docs/00-MASTER-PLAN.md:
"fork ONE environment checkpoint into N bit-identical VMs").

Usage: run from worker/ (needs NEBIUS_API_KEY + NEBIUS_PROJECT_ID with
Sandboxes permissions — see the note in executors/contree.py's module
docstring: an inference-only Token Factory key authenticates but gets a 403
on every call here):

    python scripts/smoke_contree.py
"""

from __future__ import annotations

import asyncio
import sys

from contree_sdk.sdk.exceptions import ContreeError, ForbiddenError
from dotenv import load_dotenv

from flakeproof.executors.base import SandboxCommand
from flakeproof.executors.contree import ContreeExecutor

BASE_IMAGE = "python:3.12-slim"
RANDOM_COMMAND = 'python3 -c "import random; print(random.random())"'


async def main() -> int:
    load_dotenv()
    executor = ContreeExecutor(run_id="smoke")

    print(f"Creating environment from {BASE_IMAGE} ...")
    env = await executor.create_env(BASE_IMAGE)
    print(f"  checkpoint: {env.id}")

    print("Running `echo hello` ...")
    result = await executor.run(env, "echo hello", timeout_s=120)
    print(f"  exit={result.exit_code} stdout={result.stdout!r} new checkpoint={result.env.id}")
    if result.exit_code != 0 or "hello" not in result.stdout:
        print("FAILED: `echo hello` did not behave as expected", file=sys.stderr)
        return 1

    print("Forking 3 branches from that SAME checkpoint, each printing a random number ...")
    commands = [SandboxCommand(command=RANDOM_COMMAND) for _ in range(3)]
    branches = await executor.fork_and_run(result.env, commands, concurrency=3)

    outputs = [b.stdout.strip() for b in branches]
    image_ids = [b.env.id for b in branches]
    for i, (out, img) in enumerate(zip(outputs, image_ids, strict=True)):
        print(f"  branch {i}: exit={branches[i].exit_code} output={out!r} image_id={img}")

    if any(b.exit_code != 0 for b in branches):
        print("FAILED: at least one branch exited non-zero", file=sys.stderr)
        return 1
    if len(set(outputs)) < len(outputs):
        print(f"FAILED: expected {len(outputs)} different random outputs, got duplicates: {outputs}", file=sys.stderr)
        return 1
    if len(set(image_ids)) < len(image_ids):
        print(f"FAILED: expected {len(image_ids)} different image ids, got duplicates: {image_ids}", file=sys.stderr)
        return 1

    print()
    print(f"PASSED: {len(branches)} branches forked from the same checkpoint ({result.env.id}) produced")
    print(f"{len(branches)} different outputs and {len(branches)} different image ids - branch isolation confirmed.")
    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
    except ForbiddenError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        print(
            "This key can authenticate but has no Sandboxes permissions (spawn/import/list/...).\n"
            "Sandboxes beta access is a separate grant from Token Factory inference access -\n"
            "request it from Nebius; it is not automatic. See executors/contree.py's module docstring.",
            file=sys.stderr,
        )
        exit_code = 1
    except ContreeError as exc:
        print(f"\nFAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        exit_code = 1
    raise SystemExit(exit_code)
