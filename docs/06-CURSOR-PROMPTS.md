# 06 — Cursor Vibecoding Playbook

How to use: paste the prompts below into Cursor **one at a time, in order**. After each one, run the acceptance checks, fix anything red (tell Cursor the error output), then **commit and push** before moving on. The docs in `docs/` are the source of truth — every prompt tells Cursor which docs to read first, so keep them in the repo.

Golden rules while vibecoding:

1. **Never skip the acceptance checks.** A green vertical slice beats five half-features.
2. **Mock first.** Prompts 1–7 need zero API keys. Don't touch real credits until Prompt 8.
3. If Cursor invents an API detail for Token Factory/Sandboxes, tell it to fetch the real docs (`https://docs.tokenfactory.nebius.com/llms.txt`) and correct itself.
4. Commit after every prompt: `feat: <what the prompt built>`.

---

## Prompt 1 — Scaffold the monorepo

```text
Read docs/00-MASTER-PLAN.md and docs/01-ARCHITECTURE.md first.

Scaffold this repository exactly per the repo layout in docs/01-ARCHITECTURE.md:

1. `web/`: Next.js 15 (App Router) + TypeScript + Tailwind + shadcn/ui initialized with the
   default components we need (button, input, card, badge, dialog, progress, tabs, table,
   sonner). Dev server must run on port 4310. Add lib/supabase.ts with browser (anon) and
   server (service-role) client factories reading the env vars from docs/01-ARCHITECTURE.md.
   Add web/.env.example.
2. `worker/`: Python 3.12 package `flakeproof` with the module skeleton from the layout
   (main.py, config.py, db.py, llm.py, executors/, stages/, perturbations.py,
   pytest_parse.py, tavily_enrich.py) — files created with typed function signatures and
   docstrings, bodies raising NotImplementedError for now. requirements.txt: supabase,
   openai, httpx, pydantic, python-dotenv, pytest, pytest-asyncio. Add worker/.env.example.
3. `supabase/migrations/` folder (empty for now).
4. Root: keep README.md, LICENSE, docs/ as they are. Add a simple GitHub Action that
   runs `npm run lint` in web/ and `ruff check` + `pytest` in worker/ on push.

Scaffold Next.js into a temporary subdirectory and move it into web/ if the CLI refuses
to target an existing directory. Do not add auth, a database ORM, or any paid service.
```

**Accept when:** `cd web && npm run dev -- -p 4310` serves the default page; `cd worker && pip install -r requirements.txt && python -c "import flakeproof"` works; CI file exists.

---

## Prompt 2 — Database schema + typed clients

```text
Read docs/02-DATABASE.md fully.

1. Create supabase/migrations/0001_init.sql containing EXACTLY the schema in that doc
   (enums, tables, indexes, trigger, RLS policies, realtime publication statements).
2. In web/lib/types.ts, write TypeScript types mirroring every table and enum, plus the
   RunConfig type from docs/03-PIPELINE.md.
3. In worker/flakeproof/db.py, implement: get_client() (supabase-py, service role),
   claim_next_queued_run() using a Postgres RPC with FOR UPDATE SKIP LOCKED (create the
   RPC in the migration as claim_next_run()), emit_event(run_id, stage, level, message,
   payload), update_run_status(), and typed insert helpers for test_stats, test_results,
   flaky_tests, llm_calls, sandbox_ops.
4. Write worker/flakeproof/seed_demo.py: inserts one fake completed run with 3 flaky
   tests (realistic data copied from the shapes in docs/04-API.md) so the UI has data.

Print for me the exact steps to apply the migration to a Supabase cloud project
(dashboard SQL editor paste is fine).
```

**Accept when:** migration applies cleanly in the Supabase SQL editor; `python -m flakeproof.seed_demo` inserts a run; selecting from `runs` in Supabase shows it.

---

## Prompt 3 — REST API routes

```text
Read docs/04-API.md section A fully. Implement all routes in web/app/api exactly to spec:

POST /api/runs (zod validation, URL normalization, config clamping, ip_hash =
sha256(ip + UTC-date salt), slug via nanoid(10), 409 on active duplicate repo, 429 when
>5 runs/hour/ip_hash or >2 globally active), GET /api/runs (pagination + filters),
GET /api/runs/[idOrSlug] (the full composite response from the spec), GET .../events
polling endpoint, POST .../cancel, GET .../report.md and .../patch.diff (reading stored
fields; 404 codes per spec). Use the service-role client server-side only. Every error
uses the shared { error: { code, message } } shape.

Add web/tests with vitest covering: happy-path create, invalid URL 422, duplicate 409,
rate limit 429 (mock the supabase client).
```

**Accept when:** vitest green; `curl POST /api/runs` with the demo repo URL returns 201 and the row appears in Supabase; `GET /api/runs/{slug}` returns the composite JSON of the seeded run.

---

## Prompt 4 — UI shell with realtime

```text
Read docs/07-UI-SPEC.md fully (all pages, components, and states). Build the UI:

1. Home page (/): hero with one-line pitch, RepoSubmitForm, RecentRunsGallery.
2. Run page (/runs/[slug]): PipelineStepper, SandboxGrid, LiveConsole, FindingsList,
   NemotronPanel — all driven by the composite GET endpoint + the four Supabase Realtime
   subscriptions listed in docs/02-DATABASE.md, with 5s polling fallback.
3. Report view: when status=done, the run page renders the final report layout
   (verdict banner, per-flake cards with evidence matrix table, diff viewer with
   copy button, before/after scoreboard, export buttons).
4. Leaderboard page (/leaderboard): table of done runs sorted by flaky_found.
5. Every page implements the empty/loading/error states from the spec. Dark theme
   default per the spec's design tokens. Mobile responsive.

Use the seeded demo run to verify everything renders. No new libraries beyond
shadcn/ui, lucide-react, and a small diff-render helper you write yourself.
```

**Accept when:** with the seeded run, home → click run → full report renders; inserting a `run_events` row by hand in Supabase appears in the LiveConsole within 2 s without refresh.

---

## Prompt 5 — Worker loop + mock executor (the vertical slice)

```text
Read docs/03-PIPELINE.md and docs/01-ARCHITECTURE.md (executor interface) fully.

1. Implement executors/base.py exactly per the SandboxExecutor Protocol (plus EnvHandle,
   RunResult, SandboxCommand dataclasses).
2. Implement executors/mock.py: a scripted scenario engine that replays the demo-repo
   story from docs/08-DEMO-AND-SUBMISSION.md — 42 tests collected; 20 detect forks where
   test_race fails 7x, test_order fails 5x, test_time fails 2x, test_always_broken fails
   20x; realistic JUnit XML strings; perturbation waves with the matrix numbers from the
   evidence example in docs/03-PIPELINE.md; patched runs all green. Configurable delays
   (default 0.4s per fork) so the UI animates.
3. Implement main.py: poll loop (2s), claim run, drive stages s0→s6 as a state machine
   with per-stage try/except → failed status + error event; global 45-min timeout;
   cancellation checks between waves; stale-run reaper on startup.
4. Implement stages s0 (real GitHub API calls per docs/03) and s2, s3, s4, s5, s6
   against the executor + a FakeLLM class in llm.py that returns canned P1–P7 responses
   when EXECUTOR=mock (so no API key is needed). s1 in mock mode just returns the
   scripted checkpoint.
5. Every stage writes run_events + sandbox_ops + test_* rows exactly per the docs so the
   real UI animates from mock data.

Write worker/tests/test_pipeline_mock.py: submit a run row directly to the DB, run the
worker loop once, assert final status=done, 3 flaky_tests rows, 2 fix_verified.
```

**Accept when:** `EXECUTOR=mock python -m flakeproof.main` + creating a run from the UI produces a full animated run ending in `done`, with findings, patch, scoreboard, report; pytest green.

> 🎉 After this prompt the entire product works end-to-end with zero credentials. Everything else swaps mock for real.

---

## Prompt 6 — Real LLM client (Nemotron via Token Factory)

```text
Read docs/05-LLM-PROMPTS.md and docs/04-API.md section B1.

Implement llm.py for real calls: AsyncOpenAI client with TOKEN_FACTORY_BASE_URL,
model router (FAST/SMART from env), retries w/ exponential backoff on 429/5xx (max 4),
120s timeout, JSON-mode with fenced-JSON fallback and one strict-JSON re-ask, prompt
templates loaded from worker/flakeproof/prompts/*.md (create all seven P1–P7 files with
the exact text from docs/05-LLM-PROMPTS.md), token/latency logging to llm_calls, and a
`purpose` enum. Add scripts/verify_models.py that lists {base}/models and checks the two
configured model IDs exist, printing a clear error if not.

Keep FakeLLM as the EXECUTOR=mock path. Add unit tests with a stubbed transport for:
retry on 429, fenced-JSON fallback, re-ask on invalid JSON.
```

**Accept when:** with a real `NEBIUS_API_KEY`, `python scripts/verify_models.py` passes and a one-off P2 call on a sample log returns valid JSON; tests green.

---

## Prompt 7 — Docker fallback executor

```text
Implement executors/docker_local.py per docs/01-ARCHITECTURE.md: create_env pulls the
base image and returns a container-committed image tag as the checkpoint; run = docker
run from a checkpoint image, capture exit/stdout/stderr, docker commit to a new tag;
fork_and_run = asyncio.gather of N runs from the same tag with a semaphore; read_file /
write_file via docker cp on temp containers. Tag naming: flakeproof/{run_id}:{seq}.
Add cleanup of run-scoped images on run end. This executor is for local development
only — note that in its docstring.
```

**Accept when:** `EXECUTOR=docker` runs the full pipeline against the real demo repo locally (slow is fine) and produces genuine detection numbers.

---

## Prompt 8 — Real ConTree executor (Sandboxes)

```text
First fetch https://docs.tokenfactory.nebius.com/llms.txt and read the Sandboxes
overview, SDK, and API reference pages it lists. Correct any assumption in your head
against those docs — especially base URL, auth headers, spawn/operation/file endpoints,
and how forking from an image works.

Then implement executors/contree.py per the SandboxExecutor interface using contree-sdk
(fallback to raw httpx against the REST API if the SDK fights us): create_env from
tag:python:3.12-slim, run() = spawn instance {image, command, shell:true, env} → await
operation → capture exit/stdout/stderr → new image id; fork_and_run = N parallel spawns
from one parent image with MAX_CONCURRENT_SANDBOXES semaphore; read_file/write_file per
the files API; tag the provision checkpoint. Log every call to sandbox_ops with parent
and child image ids. One retry per transient error, then degrade per docs/03-PIPELINE.md.

Add scripts/smoke_contree.py: create env → run `echo hello` → fork 3 branches running
`python3 -c "import random; print(random.random())"` → print the three different outputs
and the image ids, proving branch isolation.
```

**Accept when:** smoke script passes on real credits; `EXECUTOR=contree` full pipeline on `flakeproof-demo` finds the seeded flakes with real numbers.

---

## Prompt 9 — Real stage S1 (agent-assisted provisioning)

```text
Read docs/03-PIPELINE.md Stage 1. Implement s1_provision.py for real executors:
tool install run, pinned-SHA clone, heuristic install command builder from the repo's
manifests, then the P1 install-fixer loop (max install_max_attempts, command safety
guard from docs/05), pytest --collect-only sanity gate, checkpoint tagging, test_stats
seeding, and the exact failure taxonomy from docs/03. Emit progress events at every step
(the UI console is the only window the user has into a 3-minute install).
```

**Accept when:** provisioning succeeds on `flakeproof-demo` AND on two real OSS repos of your choice (pick medium-size pytest projects); a repo with an impossible install fails gracefully with `install_failed` and the error tail in events.

---

## Prompt 10 — Real detection, diagnosis, fix, verify

```text
Read docs/03-PIPELINE.md stages 2-5 and docs/05-LLM-PROMPTS.md P2-P5. Replace the mock
logic in s2-s5 with the real implementations: JUnit XML parsing in pytest_parse.py
(namespaced properties, reruns, timeouts), aggregation + flaky/always-failing math,
perturbations.py building the exact command mutations from the matrix table (feature-
detect faketime/stress-ng from S1, skip a perturbation with a warn event when
unavailable), evidence assembly, P3 diagnosis call, P4 patch generation with the
deterministic pre-checks + P5 review gate, patch apply via git apply in a fork,
regression guard, before/after verification waves, and verdict math — all emitting the
event strings and DB writes exactly as specced so the UI needs zero changes.

Extend worker tests: pytest_parse edge cases, verdict math, patch gate rejections
(sleep fix, deleted assertion, non-test file).
```

**Accept when:** full real run on `flakeproof-demo` ends `done` with ≥2 `fix_verified` findings and a sensible report; tests green.

---

## Prompt 11 — Tavily enrichment (bonus prize)

```text
Read docs/04-API.md B3 and docs/05-LLM-PROMPTS.md P7. Implement tavily_enrich.py
(httpx POST, feature flag on TAVILY_API_KEY presence, per-(repo,test) in-run cache,
strict budget: max 2 searches per flaky test), wire into s3, render known_reports as
linked chips on the finding card (update the UI component), and add a "Search context by
Tavily" attribution line. Skip silently when the key is missing.
```

**Accept when:** a run on a popular OSS repo with documented flaky tests shows at least one relevant linked report; runs without the key behave identically minus the chips.

---

## Prompt 12 — Polish pass

```text
Read docs/07-UI-SPEC.md "Polish checklist" section. Execute it fully: OG/social images
for run pages, favicon + logo wordmark, loading skeletons everywhere data loads, error
toasts with retry, cancel-run button wiring, mobile layouts for the run page (grid
collapses to counters), keyboard focus states, empty-state illustrations (CSS/SVG only),
the "How it works" section on the home page with the 4-step diagram, and the footer
(GitHub link, 'Built for the Nebius x NVIDIA Global AI Hackathon', MIT).
Run Lighthouse; fix anything below 90 accessibility.
```

**Accept when:** checklist all green; Lighthouse a11y ≥ 90; the app looks like a product, not a hackathon scaffold.

---

## Prompt 13 — Evidence run + leaderboard

```text
Add worker/scripts/batch_scan.py: reads repos.txt (one GitHub URL per line), submits
runs sequentially through the public API with detect-only config
(max_flaky_to_fix=0 override — add support for 0 meaning detect+report only), waits for
completion, prints a summary table. Add a --fix flag to run the full pipeline on repos
where detection found flakes. Then update /leaderboard to feature these results with a
hero stat bar (total repos scanned, total identical runs executed, flaky tests caught)
and a methodology note linking to the report pages.
```

**Accept when:** 30+ real repos scanned (curate `repos.txt` from lists of Python projects with known flaky-test labels in their issue trackers); leaderboard renders the real data; 2–3 spotlight runs with verified fixes are pinned.

---

## If something breaks that Cursor can't fix in two attempts

- Sandboxes API mismatch → re-run the "fetch llms.txt and correct yourself" instruction from Prompt 8; if the beta blocks us entirely, ship on `EXECUTOR=docker` hosted on a free Oracle Cloud ARM VM and say so honestly in the submission (the architecture doc shows Sandboxes-first design; partial credit beats no demo).
- Model IDs missing from catalog → pick the closest Nemotron reasoning + small models present, update env; the requirement is "at least one NVIDIA open model," which stays satisfied.
- Supabase realtime flaky on Vercel preview → the 5s polling fallback already covers judging; don't burn time.
