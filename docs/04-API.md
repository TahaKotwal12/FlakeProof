# 04 — API Reference

Two halves: **(A)** the REST API our Next.js app exposes (what the UI and any external user calls), and **(B)** the external APIs the worker consumes (Token Factory inference, Sandboxes/ConTree, Tavily, GitHub).

---

## A. FlakeProof REST API (Next.js route handlers)

Base URL: `{APP_BASE_URL}/api`. JSON everywhere. No auth (public product); abuse is controlled by rate limits. All errors share one shape:

```json
{ "error": { "code": "unsupported_stack", "message": "Only Python projects using pytest are supported in the MVP." } }
```

### POST `/api/runs` — start an analysis

Request body (zod-validated):

```json
{
  "repo_url": "https://github.com/owner/repo",
  "git_ref": "main",                 // optional; branch, tag, or SHA
  "config": {                        // optional; every key optional (defaults in 03-PIPELINE.md)
    "detect_runs": 20,
    "verify_runs": 20,
    "max_flaky_to_fix": 3,
    "perturbations": ["alone", "order", "cpu_stress", "time_shift", "net_off", "seed"]
  }
}
```

Behavior: normalize URL → basic GitHub existence check is deferred to the worker (S0) → clamp config to allowed ranges → compute `ip_hash` → insert `runs` row with `status='queued'` and a fresh 10-char slug.

Responses:

| Status | Body |
| --- | --- |
| `201` | `{ "run_id": "8f14…", "slug": "x7Kp2mQ9aB", "url": "/runs/x7Kp2mQ9aB", "status": "queued" }` |
| `409` | code `run_already_active` — same repo already has a run in a non-terminal state (returns existing `slug`) |
| `422` | code `invalid_repo_url` \| `invalid_config` |
| `429` | code `rate_limited` — > 5 runs/hour per IP or global active-run cap reached |

Example:

```bash
curl -X POST "$APP/api/runs" -H 'content-type: application/json' \
  -d '{"repo_url": "https://github.com/yourname/flakeproof-demo"}'
```

### GET `/api/runs` — recent runs (gallery / leaderboard data)

Query params: `limit` (default 20, max 100), `offset`, `status` (optional filter), `flaky_only=true` (only runs with ≥1 finding).

`200` response:

```json
{
  "runs": [
    {
      "id": "8f14…", "slug": "x7Kp2mQ9aB",
      "repo_owner": "yourname", "repo_name": "flakeproof-demo",
      "status": "done", "created_at": "2026-09-20T10:11:12Z", "finished_at": "…",
      "totals": { "tests_collected": 42, "flaky_found": 3, "fixed_verified": 2, "detect_runs": 20 }
    }
  ],
  "total": 137
}
```

### GET `/api/runs/:idOrSlug` — full run detail

`200` response (the run page's data source; also the polling fallback):

```json
{
  "run": { "…full runs row…" },
  "flaky_tests": [
    {
      "test_id": "tests/test_api.py::test_retry",
      "file_path": "tests/test_api.py",
      "failure_rate": 0.35,
      "status": "fix_verified",
      "root_cause": "order_dependent",
      "confidence": 0.86,
      "diagnosis_md": "### Why this test flakes …",
      "evidence": { "matrix": { "order": {"runs": 6, "failures": 5}, "…": {} } },
      "known_reports": [{ "title": "Issue #123: test_retry flaky on CI", "url": "…", "snippet": "…" }],
      "fix_patch": "--- a/tests/test_api.py\n+++ b/tests/test_api.py\n@@ …",
      "fix_rationale_md": "…",
      "verify_before_failures": 7, "verify_after_failures": 0, "verify_total": 20
    }
  ],
  "stats": { "tests_collected": 42, "always_failing": ["tests/test_broken.py::test_x"] },
  "events_tail": [ { "ts": "…", "stage": "s2_detect", "level": "success", "message": "🎯 Flaky caught: …" } ],
  "sandbox_tree": [ { "kind": "fork_run", "label": "detect fork #7", "image_in": "img_a", "image_out": "img_b", "status": "ok" } ],
  "llm_usage": { "calls": 41, "by_model": { "nemotron-nano": 33, "nemotron-super": 8 } }
}
```

`404` → code `run_not_found`.

### GET `/api/runs/:id/events?after={event_id}` — incremental event feed

Polling fallback when realtime websockets are unavailable. Returns up to 200 events with `id > after`, oldest first: `{ "events": [...], "last_id": 512 }`.

### POST `/api/runs/:id/cancel`

`200` `{ "status": "canceled" }` when the run was cancelable; `409` code `not_cancelable` for terminal states.

### GET `/api/runs/:id/report.md`

`200`, `content-type: text/markdown`. The full report (assembled in S6) — pasteable into a GitHub issue.

### GET `/api/runs/:id/patch.diff`

`200`, `content-type: text/x-diff`. Concatenated verified patches only (`status='fix_verified'`). `404` code `no_verified_fixes` when none.

---

## B. External APIs the worker consumes

### B1. Nebius Token Factory — Nemotron inference

- **Protocol:** OpenAI-compatible Chat Completions.
- **Base URL:** `TOKEN_FACTORY_BASE_URL` env (docs example shows `https://api.studio.nebius.ai/v1/`; **verify against current docs at build time**, start from `https://docs.tokenfactory.nebius.com/llms.txt`).
- **Auth:** `Authorization: Bearer $NEBIUS_API_KEY`.
- **Models:** IDs read from the catalog (`GET {base}/models`) and pinned via `NEMOTRON_FAST_MODEL` / `NEMOTRON_SMART_MODEL`. We must use NVIDIA open models (Nemotron) — a hackathon hard requirement.

```python
from openai import AsyncOpenAI
client = AsyncOpenAI(base_url=os.environ["TOKEN_FACTORY_BASE_URL"], api_key=os.environ["NEBIUS_API_KEY"])
resp = await client.chat.completions.create(
    model=os.environ["NEMOTRON_SMART_MODEL"],
    messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
    temperature=0.2,
    response_format={"type": "json_object"},   # if unsupported for a model: parse fenced JSON manually (llm.py handles both)
)
```

Wrapper requirements (`llm.py`): retries with exponential backoff on 429/5xx (max 4), per-call timeout 120 s, token/latency logging into `llm_calls`, strict-JSON re-ask on parse failure (one retry with "Return ONLY valid JSON").

### B2. Token Factory Sandboxes (ConTree) — branchable code execution

- **Docs:** https://docs.tokenfactory.nebius.com/sandboxes/overview (Beta). SDK: `pip install contree-sdk`. CLI: `contree-cli`. Base URL/auth: same Nebius key + `NEBIUS_PROJECT_ID`; **confirm exact endpoints from the docs at build time** (`CONTREE_BASE_URL` env).
- **Mental model:** every execution starts **from an image (checkpoint)** and produces a **new image**. Branching = spawning several instances from the same parent image. This maps 1:1 to our `SandboxExecutor` interface.

Conceptual REST surface (per public API reference):

| Operation | Call | Notes |
| --- | --- | --- |
| Spawn instance | `POST /instances` body `{"image": "tag:python:3.12-slim", "command": "pip install -e .", "shell": true, "env": {...}}` | `201` returns instance/operation id. `shell:true` for shell expressions; image env inherited only when `shell:true`. |
| Await result | poll the returned operation until terminal | long-running work is an operation; supports cancellation |
| Read artifacts | files/logs endpoints on the produced image | we read `/tmp/report.xml` after each pytest run |
| Fork | spawn N instances all referencing the same parent image id | our `fork_and_run` |

Executor implementation rules:

- Prefer the **`contree-sdk`** Python SDK over raw REST (it wraps operations/polling); raw REST is the fallback.
- Tag the provision checkpoint (`env_image_id`) so it survives cleanup; beta retains checkpoints ≤ 180 days, instance concurrency limit **50** (we stay ≤ `MAX_CONCURRENT_SANDBOXES=10`).
- Record every call in `sandbox_ops` (this is both audit and the UI tree animation data).
- Treat every sandbox error as retryable once, then surface as a `run_events` warn + degrade (e.g., skip a perturbation rather than failing the run).

### B3. Tavily Search API (bonus-prize integration, feature-flagged)

- **Endpoint:** `POST https://api.tavily.com/search`, header `Authorization: Bearer $TAVILY_API_KEY`.
- **Request:** `{"query": "\"{repo}\" \"{test_name}\" flaky OR intermittent", "search_depth": "basic", "max_results": 5, "include_domains": ["github.com", "stackoverflow.com"]}`.
- **Response used:** `results[].{title,url,content}` → summarized by FAST model into `known_reports` (≤ 3 items).
- Free tier ≈ 1,000 credits/month — cache per `(repo,test)` in-run; skip when key missing (`tavily_enrichment=false`).

### B4. GitHub REST (unauthenticated or `GITHUB_TOKEN`)

| Purpose | Endpoint |
| --- | --- |
| Repo exists / size / default branch | `GET https://api.github.com/repos/{owner}/{repo}` |
| Resolve ref → SHA | `GET /repos/{owner}/{repo}/commits/{ref}` |
| File tree for stack detection | `GET /repos/{owner}/{repo}/git/trees/{sha}?recursive=1` |

Unauthenticated limit is 60 req/h/IP — 3 calls per run is fine; set `GITHUB_TOKEN` to lift it. Cloning happens **inside the sandbox** via plain `git clone` (no API quota).

---

## Input/output cheat sheet (system boundaries)

| Boundary | In | Out |
| --- | --- | --- |
| Browser → API | repo URL (+ optional ref/config) | run slug; live state via Supabase Realtime |
| API → DB | `runs` row (queued) | — |
| Worker → Sandboxes | checkpoint id + shell command | exit code, stdout/stderr, JUnit XML, new checkpoint id |
| Worker → Nemotron | prompts from `05-LLM-PROMPTS.md` | strict-JSON verdicts / diffs / markdown prose |
| Worker → DB | events, stats, findings, patches, verdicts | — |
| API → user (export) | — | `report.md`, `patch.diff` |
