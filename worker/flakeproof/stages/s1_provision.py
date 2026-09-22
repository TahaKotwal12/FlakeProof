"""Stage 1 — provision: clone the repo, install it, and checkpoint the environment.

Implements docs/03-PIPELINE.md "Stage 1 — PROVISION" end to end: OS toolchain
install, pinned-SHA clone, a heuristic install command built from whichever
manifests are actually present, an agent-assisted repair loop (Nemotron P1,
docs/05-LLM-PROMPTS.md) when the heuristic command fails, a
`pytest --collect-only` sanity gate, and `test_stats` seeding. The checkpoint
returned by the sandbox's last successful `run()` becomes `runs.env_image_id`
(checkpoint tagging itself is the executor's job — see
`executors/contree.py`'s `_new_tag`/`tag_as`).

Every step emits a `run_events` row: per docs/03-PIPELINE.md, the live log
console is the only window the user has into a multi-minute install.
"""

from __future__ import annotations

import re
from typing import Any

from supabase import Client

from flakeproof import db, llm
from flakeproof.executors.base import EnvHandle, SandboxExecutor

STAGE = "s1_provision"

# docs/03-PIPELINE.md step 1: one run installs everything every later stage
# needs — git to clone, build-essential to compile wheels, libfaketime/
# stress-ng for S3's time_shift/cpu_stress perturbations.
_TOOLCHAIN_INSTALL_CMD = "apt-get update && apt-get install -y git build-essential libfaketime stress-ng"

_SETUP_TIMEOUT_S = 300  # apt-get / clone / manifest probe — administrative, not a test run
_COLLECT_TIMEOUT_S = 120

# Any of these present in /app is worth telling the install-fixer model about
# and worth feeding into the heuristic install command (docs/03-PIPELINE.md
# step 3: "requirements*.txt when present").
_MANIFEST_PROBE_CMD = (
    "cd /app && for f in pyproject.toml setup.py setup.cfg requirements*.txt; do [ -f \"$f\" ] && echo \"$f\"; done"
)

# docs/05-LLM-PROMPTS.md P1: "guard: reject commands containing rm -rf /,
# curl | sh, backgrounding".
_FORBIDDEN_COMMAND_PATTERNS = (
    re.compile(r"rm\s+-rf\s+/(?:\s|$)"),
    re.compile(r"(?:curl|wget)[^\n|]*\|\s*(?:sh|bash)\b"),
    re.compile(r"&\s*$"),
)


class InstallFailedError(RuntimeError):
    """Toolchain/clone/heuristic+agent install exhausted, or the collect-only gate failed.

    Maps to `docs/03-PIPELINE.md`'s only failure edge out of `provisioning`:
    `provisioning --> failed : install impossible`.
    """


def _is_forbidden_command(command: str) -> bool:
    return any(pattern.search(command) for pattern in _FORBIDDEN_COMMAND_PATTERNS)


def _tail_lines(text: str, n: int = 120) -> str:
    return "\n".join(text.splitlines()[-n:])


def parse_collected_node_ids(stdout: str) -> list[str]:
    """Parse `pytest --collect-only -q` stdout into pytest node ids.

    `-q` collect-only output is one node id per line (e.g.
    `tests/test_api.py::test_retry`); summary/warning lines never contain
    `::`, so filtering on that is enough without depending on exact pytest
    version formatting (blank-line placement, trailing summary wording, ...).
    """
    return [
        stripped
        for line in stdout.splitlines()
        if "::" in (stripped := line.strip()) and not stripped.startswith(("=", "<"))
    ]


def build_heuristic_install_command(manifests: list[str]) -> str:
    """docs/03-PIPELINE.md step 3a's heuristic, built from detected manifests.

    Extended beyond the doc's literal "if pyproject.toml" wording to also
    cover setup.py/setup.cfg-only packages (a real, live-caught gap: a repo
    with only setup.cfg got nothing but a bare `pip install pytest` here,
    which trivially "succeeds" while never installing the project's own
    test-only dependencies -- the failure only surfaced later, confusingly,
    at the collect-only gate).
    """
    steps = ["cd /app"]
    if any(name in manifests for name in ("pyproject.toml", "setup.py", "setup.cfg")):
        steps.append("(pip install -e '.[test,dev]' || pip install -e .)")
    steps.extend(f"pip install -r {m}" for m in manifests if m.startswith("requirements") and m.endswith(".txt"))
    steps.append("pip install pytest pytest-random-order pytest-timeout")
    return " && ".join(steps)


def _format_previous_attempts(attempts: list[tuple[str, int, str]]) -> str:
    if not attempts:
        return "(none)"
    return "\n\n".join(
        f"{i}. `{command}` -> exit {exit_code}\n{stderr_tail}"
        for i, (command, exit_code, stderr_tail) in enumerate(attempts, start=1)
    )


async def run(run_id: str, executor: SandboxExecutor, db_client: Client) -> EnvHandle:
    """Clone the target repo, install it inside a sandbox (agent-assisted), and
    return the baseline checkpoint used by all later stages.
    """
    run_row = await db.get_run(db_client, run_id)
    owner: str = run_row["repo_owner"]
    repo: str = run_row["repo_name"]
    commit_sha: str = run_row["commit_sha"]
    config: dict[str, Any] = run_row.get("config") or {}

    install_timeout_s = int(config.get("install_timeout_s", 900))
    install_max_attempts = int(config.get("install_max_attempts", 4))
    base_image = config.get("base_image", "python:3.12-slim")

    await db.emit_event(db_client, run_id, STAGE, "info", f"Provisioning sandbox from {base_image} ...")
    env = await executor.create_env(base_image)

    env = await _install_toolchain(run_id, executor, db_client, env)
    env = await _clone_repo(run_id, executor, db_client, env, owner=owner, repo=repo, commit_sha=commit_sha)

    manifests, env = await _detect_manifests(executor, env)
    await db.emit_event(
        db_client, run_id, STAGE, "info", f"Detected manifests: {', '.join(manifests) if manifests else '(none)'}"
    )

    env = await _install_loop(
        run_id=run_id,
        owner=owner,
        repo=repo,
        executor=executor,
        db_client=db_client,
        env=env,
        manifests=manifests,
        install_timeout_s=install_timeout_s,
        install_max_attempts=install_max_attempts,
    )

    node_ids, env = await _collect_sanity_gate(run_id, executor, db_client, env)

    await db.insert_test_stats(
        db_client,
        [{"run_id": run_id, "test_id": node_id, "file_path": node_id.split("::", 1)[0]} for node_id in node_ids],
    )

    await db.update_run_status(db_client, run_id, "detecting", env_image_id=env.id)
    await db.emit_event(db_client, run_id, STAGE, "success", f"Environment ready: {len(node_ids)} tests collected")
    return env


async def _fail(db_client: Client, run_id: str, message: str, payload: dict[str, Any] | None = None) -> None:
    await db.emit_event(db_client, run_id, STAGE, "error", message, payload)
    await db.update_run_status(db_client, run_id, "failed", error="install_failed")


async def _install_toolchain(run_id: str, executor: SandboxExecutor, db_client: Client, env: EnvHandle) -> EnvHandle:
    await db.emit_event(
        db_client, run_id, STAGE, "info", "Installing toolchain: git, build-essential, libfaketime, stress-ng ..."
    )
    result = await executor.run(env, _TOOLCHAIN_INSTALL_CMD, timeout_s=_SETUP_TIMEOUT_S)
    if result.exit_code != 0:
        await _fail(
            db_client,
            run_id,
            "Failed to install base toolchain (git/build-essential/libfaketime/stress-ng)",
            {"exit_code": result.exit_code, "stderr_tail": _tail_lines(result.stderr)},
        )
        raise InstallFailedError("toolchain install failed")
    return result.env


async def _clone_repo(
    run_id: str, executor: SandboxExecutor, db_client: Client, env: EnvHandle, *, owner: str, repo: str, commit_sha: str
) -> EnvHandle:
    await db.emit_event(db_client, run_id, STAGE, "info", f"Cloning {owner}/{repo}@{commit_sha[:7]} ...")
    clone_cmd = f"git clone --depth 50 https://github.com/{owner}/{repo}.git /app && cd /app && git checkout {commit_sha}"
    result = await executor.run(env, clone_cmd, timeout_s=_SETUP_TIMEOUT_S)
    if result.exit_code != 0:
        await _fail(
            db_client,
            run_id,
            f"Failed to clone {owner}/{repo}@{commit_sha[:7]}",
            {"exit_code": result.exit_code, "stderr_tail": _tail_lines(result.stderr)},
        )
        raise InstallFailedError("clone failed")
    return result.env


async def _detect_manifests(executor: SandboxExecutor, env: EnvHandle) -> tuple[list[str], EnvHandle]:
    result = await executor.run(env, _MANIFEST_PROBE_CMD, timeout_s=_SETUP_TIMEOUT_S)
    manifests = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return manifests, result.env


async def _install_loop(
    *,
    run_id: str,
    owner: str,
    repo: str,
    executor: SandboxExecutor,
    db_client: Client,
    env: EnvHandle,
    manifests: list[str],
    install_timeout_s: int,
    install_max_attempts: int,
) -> EnvHandle:
    """docs/03-PIPELINE.md step 3: heuristic install, then on failure hand the
    stderr tail to Nemotron's install-fixer (P1) for the next command, up to
    `install_max_attempts` total attempts.
    """
    command = build_heuristic_install_command(manifests)
    attempts: list[tuple[str, int, str]] = []

    for attempt_number in range(1, install_max_attempts + 1):
        await db.emit_event(
            db_client, run_id, STAGE, "info", f"Install attempt {attempt_number}/{install_max_attempts}: {command}"
        )
        result = await executor.run(env, command, timeout_s=install_timeout_s)
        env = result.env
        if result.exit_code == 0:
            await db.emit_event(db_client, run_id, STAGE, "success", "Install succeeded")
            return env

        stderr_tail = _tail_lines(result.stderr)
        attempts.append((command, result.exit_code, stderr_tail))
        await db.emit_event(
            db_client,
            run_id,
            STAGE,
            "warn",
            f"Install attempt {attempt_number} failed (exit {result.exit_code})",
            {"exit_code": result.exit_code, "stderr_tail": stderr_tail},
        )

        if attempt_number == install_max_attempts:
            break

        await db.emit_event(db_client, run_id, STAGE, "info", "Asking Nemotron install-fixer for the next command ...")
        chat_result = await llm.run(
            db_client,
            "install_fix",
            {
                "owner": owner,
                "repo": repo,
                "relevant_manifest_list": ", ".join(manifests) if manifests else "(none found)",
                "failed_command": command,
                "exit_code": result.exit_code,
                "stderr_tail_120_lines": stderr_tail,
                "numbered_list_of_previous_commands_and_results": _format_previous_attempts(attempts),
            },
            run_id=run_id,
            stage=STAGE,
        )
        if not chat_result.ok or chat_result.data is None:
            await db.emit_event(db_client, run_id, STAGE, "error", f"Install-fixer call failed: {chat_result.error}")
            break

        fix = chat_result.data
        if fix.get("give_up"):
            await db.emit_event(
                db_client, run_id, STAGE, "error", f"Install-fixer gave up: {fix.get('reasoning', '(no reason given)')}"
            )
            break

        next_command = str(fix.get("command", "")).strip()
        if not next_command or _is_forbidden_command(next_command):
            await db.emit_event(
                db_client, run_id, STAGE, "error", f"Install-fixer proposed an unsafe or empty command: {next_command!r}"
            )
            break

        await db.emit_event(db_client, run_id, STAGE, "info", f"Install-fixer: {fix.get('reasoning', '')}")
        command = f"cd /app && {next_command}"

    await _fail(
        db_client,
        run_id,
        "Install failed after all attempts",
        {"attempts": len(attempts), "last_stderr_tail": attempts[-1][2] if attempts else None},
    )
    raise InstallFailedError("install attempts exhausted")


async def _collect_sanity_gate(
    run_id: str, executor: SandboxExecutor, db_client: Client, env: EnvHandle
) -> tuple[list[str], EnvHandle]:
    await db.emit_event(db_client, run_id, STAGE, "info", "Running pytest --collect-only sanity gate ...")
    result = await executor.run(env, "cd /app && pytest --collect-only -q", timeout_s=_COLLECT_TIMEOUT_S)
    node_ids = parse_collected_node_ids(result.stdout)
    if result.exit_code != 0 or not node_ids:
        await _fail(
            db_client,
            run_id,
            "pytest --collect-only failed or found zero tests",
            {
                "exit_code": result.exit_code,
                "stdout_tail": _tail_lines(result.stdout),
                "stderr_tail": _tail_lines(result.stderr),
            },
        )
        raise InstallFailedError("collect-only sanity gate failed")
    return node_ids, result.env
