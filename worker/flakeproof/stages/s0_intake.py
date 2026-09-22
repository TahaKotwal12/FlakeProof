"""Stage 0 — intake: validate the submitted repo URL/config and initialize the run.

Implements docs/03-PIPELINE.md "Stage 0 — INTAKE" and docs/04-API.md B4
(GitHub REST): repo existence/visibility/size checks, an abuse guard for
unstarred forks of huge upstreams, `git_ref` -> `commit_sha` resolution, and
Python+pytest stack detection from the repo's file tree.

Correction against the stub's original docstring ("transition the run from
queued to provisioning"): `claim_next_run()` (supabase/migrations/
0001_init.sql) already does that transition atomically as part of claiming
the run (docs/03-PIPELINE.md state diagram: "queued --> provisioning :
worker claims run") -- by the time this stage runs, `runs.status` is already
`provisioning`, and there's no separate "intake" state in the `run_status`
enum. This stage stays within `provisioning` on success (S1 is what advances
to `detecting`) and only writes status itself on failure.
"""

from __future__ import annotations

import os

import httpx
from supabase import Client

from flakeproof import db

STAGE = "s0_intake"

GITHUB_API_BASE = "https://api.github.com"
_REQUEST_TIMEOUT_S = 20.0
_MAX_REPO_SIZE_KB = 200_000  # docs/03-PIPELINE.md: "size > 200 MB"
_ABUSE_GUARD_PARENT_SIZE_KB = 50_000  # "a fork with zero stars pointing at a huge upstream"

# Root-level manifests worth checking for a pytest mention (matches which
# files s1_provision.py's install heuristic itself looks at).
_PYTEST_MANIFEST_NAMES = ("pyproject.toml", "setup.cfg")


class IntakeFailedError(RuntimeError):
    """A repo/ref/stack check failed. `code` matches docs/03-PIPELINE.md's
    "Failure modes -> user-facing errors" (repo_not_found, repo_private,
    repo_too_large, unsupported_stack) and web/lib/error-copy.ts's `RUN_FAILURE_COPY`.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _github_get(client: httpx.AsyncClient, path: str) -> httpx.Response:
    return await client.get(f"{GITHUB_API_BASE}{path}", headers=_github_headers(), timeout=_REQUEST_TIMEOUT_S)


async def _fetch_repo(client: httpx.AsyncClient, owner: str, repo: str) -> dict:
    try:
        resp = await _github_get(client, f"/repos/{owner}/{repo}")
    except httpx.HTTPError as exc:
        raise IntakeFailedError("repo_not_found", f"Couldn't reach GitHub to check {owner}/{repo}: {exc}") from exc
    if resp.status_code == 404:
        raise IntakeFailedError("repo_not_found", f"{owner}/{repo} not found (or private).")
    resp.raise_for_status()
    data = resp.json()

    if data.get("private"):
        raise IntakeFailedError("repo_private", f"{owner}/{repo} is private.")
    if data.get("size", 0) > _MAX_REPO_SIZE_KB:
        raise IntakeFailedError("repo_too_large", f"{owner}/{repo} is larger than the 200 MB MVP limit.")
    if data.get("fork") and data.get("stargazers_count", 0) == 0:
        parent_size = (data.get("parent") or {}).get("size", 0)
        if parent_size > _ABUSE_GUARD_PARENT_SIZE_KB:
            raise IntakeFailedError(
                "unsupported_stack", f"{owner}/{repo} is an unstarred fork of a very large upstream repo."
            )
    return data


async def _resolve_commit_sha(client: httpx.AsyncClient, owner: str, repo: str, ref: str) -> str:
    try:
        resp = await _github_get(client, f"/repos/{owner}/{repo}/commits/{ref}")
    except httpx.HTTPError as exc:
        raise IntakeFailedError("repo_not_found", f"Couldn't resolve ref '{ref}' on {owner}/{repo}: {exc}") from exc
    if resp.status_code == 404:
        raise IntakeFailedError("repo_not_found", f"Ref '{ref}' not found on {owner}/{repo}.")
    resp.raise_for_status()
    return resp.json()["sha"]


async def _fetch_tree_paths(client: httpx.AsyncClient, owner: str, repo: str, sha: str) -> list[str]:
    try:
        resp = await _github_get(client, f"/repos/{owner}/{repo}/git/trees/{sha}?recursive=1")
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise IntakeFailedError("repo_not_found", f"Couldn't fetch the file tree for {owner}/{repo}@{sha}: {exc}") from exc
    data = resp.json()
    return [entry["path"] for entry in data.get("tree", []) if entry.get("type") == "blob"]


def _looks_like_pytest_test_file(path: str) -> bool:
    parts = path.split("/")
    basename = parts[-1]
    return len(parts) > 1 and ("tests" in parts[:-1] or "test" in parts[:-1]) and basename.startswith("test_") and basename.endswith(".py")


async def _manifest_mentions_pytest(client: httpx.AsyncClient, owner: str, repo: str, sha: str, path: str) -> bool:
    """Raw file content via raw.githubusercontent.com (a different host, so
    it doesn't count against the GitHub REST API rate limit at all).
    """
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{sha}/{path}"
    try:
        resp = await client.get(url, timeout=_REQUEST_TIMEOUT_S)
    except httpx.HTTPError:
        return False
    return resp.status_code == 200 and "pytest" in resp.text.lower()


async def _detect_pytest(client: httpx.AsyncClient, owner: str, repo: str, sha: str, paths: list[str]) -> bool:
    """docs/03-PIPELINE.md step 3: pytest.ini, a `tests/` dir of `test_*.py`,
    or pyproject.toml/setup.cfg/requirements*.txt mentioning pytest.
    """
    root_names = {p for p in paths if "/" not in p}

    if "pytest.ini" in root_names:
        return True
    if any(_looks_like_pytest_test_file(p) for p in paths):
        return True
    for manifest in _PYTEST_MANIFEST_NAMES:
        if manifest in root_names and await _manifest_mentions_pytest(client, owner, repo, sha, manifest):
            return True
    for name in root_names:
        if name.startswith("requirements") and name.endswith(".txt") and await _manifest_mentions_pytest(
            client, owner, repo, sha, name
        ):
            return True
    return False


async def run(run_id: str, db_client: Client) -> None:
    """Validate the repo and resolve `commit_sha`/`test_framework`, or fail
    the run with one of docs/03-PIPELINE.md's Stage 0 failure codes.
    """
    run_row = await db.get_run(db_client, run_id)
    owner: str = run_row["repo_owner"]
    repo: str = run_row["repo_name"]
    requested_ref: str | None = run_row.get("git_ref")

    try:
        async with httpx.AsyncClient() as http_client:
            repo_data = await _fetch_repo(http_client, owner, repo)
            ref = requested_ref or repo_data["default_branch"]
            commit_sha = await _resolve_commit_sha(http_client, owner, repo, ref)
            paths = await _fetch_tree_paths(http_client, owner, repo, commit_sha)
            has_pytest = await _detect_pytest(http_client, owner, repo, commit_sha, paths)
    except IntakeFailedError as exc:
        await db.emit_event(db_client, run_id, STAGE, "error", str(exc))
        await db.update_run_status(db_client, run_id, "failed", error=exc.code)
        raise

    if not has_pytest:
        message = "Only Python projects using pytest are supported in the MVP"
        await db.emit_event(db_client, run_id, STAGE, "error", message)
        await db.update_run_status(db_client, run_id, "failed", error="unsupported_stack")
        raise IntakeFailedError("unsupported_stack", message)

    await db.update_run_status(db_client, run_id, "provisioning", commit_sha=commit_sha, test_framework="pytest")

    test_file_count = sum(1 for p in paths if _looks_like_pytest_test_file(p))
    await db.emit_event(
        db_client,
        run_id,
        STAGE,
        "success",
        f"Repo OK: {owner}/{repo}@{commit_sha[:7]}, pytest detected, ~{test_file_count} test files",
    )
