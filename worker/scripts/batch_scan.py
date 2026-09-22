#!/usr/bin/env python
"""Batch-scan repos.txt through the public FlakeProof API (docs/06-CURSOR-PROMPTS.md
Prompt 13): submits one detect-only run per repo (`max_flaky_to_fix: 0` --
detect + report, no diagnose/fix/verify, per docs/03-PIPELINE.md's RunConfig
and the `max_flaky_to_fix=0` handling already in `stages/s2_detect.py`),
waits for each to finish, then prints a summary table. `--fix` follows up
with a full-pipeline re-run (fresh submission, `max_flaky_to_fix>0`) on every
repo where detection found at least one flaky test.

Talks to the real POST /api/runs endpoint like any other client, including
its rate limits (docs/04-API.md: 5 runs/hour/IP, 2 globally active) -- on 429
it waits out the rolling hour window rather than bypassing or hammering the
endpoint, so a real 30+ repo scan legitimately takes multiple hours. Run it
with nohup/in the background for a real evidence run.

Usage:
    python scripts/batch_scan.py [--repos-file repos.txt] [--api-base URL]
                                  [--fix] [--max-fixes 3]
                                  [--poll-interval 5] [--run-timeout 1800] [--fix-timeout 2700]
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

DEFAULT_API_BASE = "http://localhost:4310"
DEFAULT_POLL_INTERVAL_S = 5.0
DEFAULT_RUN_TIMEOUT_S = 1800  # 30 min -- generous for a detect-only run
DEFAULT_FIX_TIMEOUT_S = 2700  # 45 min -- matches the worker's own global run-timeout budget
# docs/04-API.md: "> 5 runs/hour per IP". Wait out the whole rolling window
# (plus a minute of slack) rather than guessing at a shorter retry.
RATE_LIMIT_BACKOFF_S = 65 * 60

TERMINAL_STATUSES = {"done", "failed", "canceled"}


@dataclass
class ScanResult:
    repo_url: str
    slug: str | None = None
    status: str = "not_started"
    error: str | None = None
    tests_collected: int = 0
    detect_runs: int = 0
    flaky_found: int = 0
    always_failing: int = 0
    fixed_verified: int = 0
    fix_failed: int = 0
    elapsed_s: float = 0.0
    fix_status: str | None = None  # None (no --fix attempt) | the fix run's terminal status


def _read_repos(path: Path) -> list[str]:
    repos = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        repos.append(line)
    return repos


def _submit_run(client: httpx.Client, repo_url: str, *, max_flaky_to_fix: int) -> tuple[str | None, str | None]:
    """POST /api/runs. Returns (slug, error_message) -- exactly one is None.

    409 (already active): follows the existing run instead of erroring, since
    "there's already a run for this repo" isn't a scan failure. 429 (rate
    limited): waits out the rolling hour and retries indefinitely.
    """
    while True:
        resp = client.post("/api/runs", json={"repo_url": repo_url, "config": {"max_flaky_to_fix": max_flaky_to_fix}})

        if resp.status_code == 201:
            return resp.json()["slug"], None

        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        code = body.get("error", {}).get("code", str(resp.status_code))
        message = body.get("error", {}).get("message", resp.text)

        if resp.status_code == 409:
            slug = body.get("slug")
            print(f"  already active -> following existing run {slug}")
            return slug, None

        if resp.status_code == 429:
            print(f"  rate limited ({message}); waiting {RATE_LIMIT_BACKOFF_S // 60} min for the window to clear...")
            time.sleep(RATE_LIMIT_BACKOFF_S)
            continue

        return None, f"{code}: {message}"


def _poll_run(client: httpx.Client, slug: str, *, timeout_s: float, poll_interval_s: float) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        resp = client.get(f"/api/runs/{slug}")
        resp.raise_for_status()
        body = resp.json()
        if body["run"]["status"] in TERMINAL_STATUSES:
            return body
        time.sleep(poll_interval_s)
    raise TimeoutError(f"run {slug} did not finish within {timeout_s:.0f}s")


def _scan_one(
    client: httpx.Client, repo_url: str, *, max_flaky_to_fix: int, timeout_s: float, poll_interval_s: float
) -> ScanResult:
    result = ScanResult(repo_url=repo_url)
    start = time.monotonic()

    slug, error = _submit_run(client, repo_url, max_flaky_to_fix=max_flaky_to_fix)
    if error:
        result.status = "submit_failed"
        result.error = error
        return result
    result.slug = slug

    try:
        body = _poll_run(client, slug, timeout_s=timeout_s, poll_interval_s=poll_interval_s)
    except TimeoutError as exc:
        result.status = "timeout"
        result.error = str(exc)
        result.elapsed_s = time.monotonic() - start
        return result

    run = body["run"]
    totals = run.get("totals") or {}
    result.status = run["status"]
    result.error = run.get("error")
    result.elapsed_s = time.monotonic() - start
    result.tests_collected = totals.get("tests_collected", 0)
    result.detect_runs = totals.get("detect_runs", 0)
    result.flaky_found = totals.get("flaky_found", 0)
    result.always_failing = totals.get("always_failing", 0)
    result.fixed_verified = totals.get("fixed_verified", 0)
    result.fix_failed = totals.get("fix_failed", 0)
    return result


def _print_table(results: list[ScanResult], *, show_fix: bool) -> None:
    headers = ["Repo", "Status", "Tests", "Flaky", "Broken"]
    if show_fix:
        headers.append("Fix")
    headers.append("Time")

    rows: list[list[str]] = []
    for r in results:
        repo_short = r.repo_url.removeprefix("https://github.com/").removeprefix("http://github.com/")
        row = [repo_short, r.status, str(r.tests_collected), str(r.flaky_found), str(r.always_failing)]
        if show_fix:
            row.append(f"{r.fix_status} ({r.fixed_verified} verified)" if r.fix_status else "-")
        row.append(f"{r.elapsed_s:.0f}s")
        rows.append(row)

    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) if rows else len(headers[i]) for i in range(len(headers))]

    def _fmt(cells: list[str]) -> str:
        return "  ".join(cell.ljust(width) for cell, width in zip(cells, widths, strict=True))

    print(_fmt(headers))
    print("-" * (sum(widths) + 2 * (len(widths) - 1)))
    for row in rows:
        print(_fmt(row))

    scanned_ok = sum(1 for r in results if r.status == "done")
    total_flaky = sum(r.flaky_found for r in results)
    repos_with_flaky = sum(1 for r in results if r.flaky_found > 0)
    summary = f"\nScanned {len(results)} repos ({scanned_ok} completed cleanly). {total_flaky} flaky tests found across {repos_with_flaky} repos."
    if show_fix:
        total_verified = sum(r.fixed_verified for r in results)
        summary += f" {total_verified} fixes verified."
    print(summary)


def _run_detect_scan(
    client: httpx.Client, repos: list[str], *, timeout_s: float, poll_interval_s: float
) -> list[ScanResult]:
    results: list[ScanResult] = []
    for i, repo_url in enumerate(repos, start=1):
        print(f"[{i}/{len(repos)}] {repo_url}")
        result = _scan_one(client, repo_url, max_flaky_to_fix=0, timeout_s=timeout_s, poll_interval_s=poll_interval_s)
        print(f"  -> {result.status} ({result.elapsed_s:.0f}s), {result.flaky_found} flaky, {result.always_failing} broken")
        results.append(result)
    return results


def _run_fix_pass(
    client: httpx.Client, results: list[ScanResult], *, max_fixes: int, timeout_s: float, poll_interval_s: float
) -> None:
    candidates = [r for r in results if r.status == "done" and r.flaky_found > 0]
    print(f"\n--fix: re-running the full pipeline on {len(candidates)} repo(s) with flakes found...\n")
    for i, result in enumerate(candidates, start=1):
        print(f"[{i}/{len(candidates)}] {result.repo_url}")
        fix_result = _scan_one(
            client, result.repo_url, max_flaky_to_fix=max_fixes, timeout_s=timeout_s, poll_interval_s=poll_interval_s
        )
        result.fix_status = fix_result.status
        result.fixed_verified = fix_result.fixed_verified
        result.fix_failed = fix_result.fix_failed
        result.slug = fix_result.slug or result.slug
        print(
            f"  -> {fix_result.status} ({fix_result.elapsed_s:.0f}s), "
            f"{fix_result.fixed_verified} verified, {fix_result.fix_failed} fix failed"
        )


def main() -> int:
    # A real scan runs for hours in the background (redirected to a log file
    # for tailing) -- stdout must be line-buffered, or progress is invisible
    # until the whole process exits (caught live: an interrupted run's
    # redirected output file was completely empty despite real progress).
    sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repos-file", type=Path, default=Path("repos.txt"))
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--fix", action="store_true", help="also run the full pipeline on repos where detection found flakes")
    parser.add_argument("--max-fixes", type=int, default=3, help="max_flaky_to_fix used for --fix re-runs")
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL_S)
    parser.add_argument("--run-timeout", type=float, default=DEFAULT_RUN_TIMEOUT_S)
    parser.add_argument("--fix-timeout", type=float, default=DEFAULT_FIX_TIMEOUT_S)
    args = parser.parse_args()

    if not args.repos_file.exists():
        print(f"No such file: {args.repos_file}", file=sys.stderr)
        return 1
    repos = _read_repos(args.repos_file)
    if not repos:
        print(f"{args.repos_file} has no repo URLs (one per line; '#' comments allowed).", file=sys.stderr)
        return 1

    print(f"Scanning {len(repos)} repos (detect-only) against {args.api_base}...\n")
    results: list[ScanResult] = []
    with httpx.Client(base_url=args.api_base, timeout=30.0) as client:
        try:
            results = _run_detect_scan(client, repos, timeout_s=args.run_timeout, poll_interval_s=args.poll_interval)
            if args.fix:
                _run_fix_pass(
                    client, results, max_fixes=args.max_fixes, timeout_s=args.fix_timeout, poll_interval_s=args.poll_interval
                )
        except KeyboardInterrupt:
            print("\nInterrupted -- printing results collected so far.\n")

        print()
        _print_table(results, show_fix=args.fix)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
