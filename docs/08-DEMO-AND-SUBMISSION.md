# 08 — Demo, Evidence, and Submission Kit

## A. The companion demo repo: `flakeproof-demo`

A **separate public GitHub repo** (create it under your account) — a small, realistic Python package with a pytest suite seeded with one flake of each root-cause family. It guarantees the live demo and the video always have something spectacular to catch, and it doubles as the mock executor's script.

Structure:

```
flakeproof-demo/
├── README.md            # honest: "intentionally flaky test suite for demoing FlakeProof"
├── pyproject.toml       # name: taskqueue-demo; deps: requests; test dep: pytest
├── src/taskqueue/       # ~150 lines: a tiny in-memory task queue with a worker thread,
│   ├── __init__.py      #   a rate limiter using time.time(), and a stats module with a
│   ├── queue.py         #   module-level cache (deliberate shared state)
│   ├── ratelimit.py
│   └── stats.py
└── tests/  (~42 tests total; 36 stable + these 6)
    ├── test_race.py          # async_race: starts worker thread, asserts task done after
    │                         #   0.05s sleep — loses the race under CPU stress (~35%)
    ├── test_order.py         # order_dependent: test_a mutates stats._cache; test_b
    │                         #   asserts on it — fails when shuffled after/before
    ├── test_time.py          # time_dependent: asserts rate-limit window using
    │                         #   datetime.now() minute boundary — fails near :59
    ├── test_net.py           # network_external: calls https://httpbin.org/status/200
    │                         #   with 2s timeout — fails on blackhole/slow network
    ├── test_seed.py          # randomness: samples random.random() without seed,
    │                         #   asserts value > 0.15 (~15% natural failure)
    └── test_always_broken.py # fails 100% — proves we distinguish broken from flaky
```

Design rules: each flaky test looks *plausible* (like real code a busy dev writes), comments do NOT reveal the flakiness, and the seeded failure rates roughly match the mock scenario numbers (so mock and real demos tell the same story). The correct fixes are the textbook ones from P4's "GOOD fixes" list — so Nemotron has a fair shot at verified fixes.

## B. Evidence run (M8) — the impact proof

1. Curate `repos.txt`: 30–50 medium-size Python OSS projects. Where to find candidates: GitHub issue searches for label `flaky`, `flaky-test`, or issue titles "flaky test" in pytest-based projects; awesome-python lists for well-known libraries.
2. Run `batch_scan.py` in detect-only mode (cheap: ~21 sandbox runs per repo).
3. Pin 2–3 full runs where FlakeProof produced a **verified fix on a real repo** — these are your headline artifacts.
4. Optional but powerful: open a friendly GitHub issue (or PR) on one real project with the report + verified patch, linking the public report page. One accepted fix on a real OSS repo = the strongest "real user completed the workflow" evidence a judge can ask for. Be polite, disclose it's a tool run, follow the project's contributing guide.
5. Publish the leaderboard and post it with #BuildInPublic.

## C. The 3-minute demo video (script)

Rules from the hackathon: ≤ 3 min, public YouTube, audio must explain how Token Factory and NVIDIA open models were used. Screen-record the real product; no slides except the first 10 seconds.

| Time | Visual | Voiceover beats |
| --- | --- | --- |
| 0:00–0:20 | Title card → CI screenshot with a red ❌ rerun | "Flaky tests. Studies show developers lose 2.5% of their time to them, and Google spends up to 16% of its test infrastructure just re-running them. Every existing tool watches your CI history and guesses. FlakeProof runs the experiment." |
| 0:20–0:50 | Home page → paste `flakeproof-demo` URL → run page; SandboxGrid lights up | "Paste any repo. FlakeProof clones it into a Nebius Token Factory Sandbox and — this is the trick — forks that checkpoint into 20 bit-identical VMs. Same code, same state. Any test that fails in some forks and passes in others is *provably* flaky." |
| 0:50–1:30 | Flake cards appear; open Diagnosis tab; evidence matrix highlights | "It caught three. Now it finds the root cause by experiment: forked branches with shuffled test order, a stressed CPU, a shifted clock, a blackholed network. This one only fails when order changes — shared state between tests. The diagnosis is written by NVIDIA's Nemotron reasoning model; fast calls like log parsing run on Nemotron Nano to keep it cheap." |
| 1:30–2:10 | Fix tab: diff appears → Verify: BEFORE 7/20 vs AFTER 0/20 side-by-side grids | "Nemotron writes a minimal fix — test code only, no sleep hacks, and a reviewer model rejects anything that weakens assertions. Then the proof: twenty fresh forks under the exact condition that triggered the flake. Before: seven failures. After: zero. That's not a guess; that's a verified fix, ready as a PR." |
| 2:10–2:40 | Leaderboard page; a real OSS run report; the GitHub issue/PR with the patch | "We scanned {N} real open-source projects: {X} proven-flaky tests, {Y} verified fixes — including this one accepted upstream. Every report is public and reproducible: pinned commit, pinned image, published config." |
| 2:40–3:00 | Architecture slide (one diagram) → repo + URL | "Built on Token Factory end to end: Sandboxes' git-like branching is the engine, Nemotron Super and Nano are the brains. Open source, MIT, live at {url}. FlakeProof — stop guessing, run the experiment." |

Record with OBS (free). Do at least 3 takes; keep cursor movement slow; 1080p.

## D. Devpost submission checklist

- [ ] **Track:** Coding and Agentic Engineering.
- [ ] **Project description:** reuse `00-MASTER-PLAN.md` problem/wedge/judging sections; include the citations; explicitly name where Token Factory accelerated the build (Sandboxes branching, model routing, one bill) — the form asks for this.
- [ ] **Demo URL:** the Vercel deployment (worker must be running during judging window — see 01-ARCHITECTURE hosting note; pin 3 finished runs so the site impresses even if a live run hiccups).
- [ ] **Video:** YouTube link, ≤ 3 min, audio covers Token Factory + Nemotron usage (script above).
- [ ] **Repo:** public GitHub, MIT license visible at repo top, README with setup instructions (both mock mode and real mode), architecture diagram, "How we use Nemotron/Token Factory" section.
- [ ] **Feedback** (required field + $100×10 prize): write it from real notes — keep a `FEEDBACK.md` scratchpad during Prompts 8–10 logging every Sandboxes/Token Factory paper cut with repro details, and every delight. Specific > polite. Include SDK/API versions and timestamps. Email/Discord per the Sandboxes beta docs if they ask for direct feedback too.
- [ ] **Tavily:** ensure the integration is on in the demo runs and described in one paragraph (targets the $3,000 prize).
- [ ] **City event:** check the hackathon's events page for a nearby Builders & Brews; attending qualifies you for a $500 City Winner award.
- [ ] Register team members on Devpost before the deadline; submit at least a day early (Devpost forms reject late edits).

## E. #BuildInPublic content plan (free marketing, better Grand Prize odds)

Post short clips at milestones — each is a natural viral-ish artifact:

1. M3: the mock run animating ("built the whole product before spending a rupee on compute").
2. M4: first real detection on the demo repo (screen recording of the grid).
3. M6: first BEFORE 7/20 → AFTER 0/20 scoreboard.
4. M8: the leaderboard + any upstream-accepted fix (tag the project, be gracious).
5. Submission day: the video itself.

## F. Risk register

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| Sandboxes beta API differs from assumptions / breaks | Medium | Executor abstraction; Prompt 8 forces reading live docs; DockerExecutor fallback on a free Oracle ARM VM; honest note in submission |
| Nemotron model IDs/catalog different than expected | Medium | Env-pinned IDs + `verify_models.py`; requirement is "≥1 NVIDIA open model", any Nemotron works |
| Real repos too slow/heavy to provision | High for big repos | Size cap in S0; curate leaderboard repos by install simplicity; per-stage timeouts degrade gracefully |
| Patch quality poor on real repos | Medium | Verification gate means we only ever *claim* verified fixes; detection+diagnosis alone is already a complete product story |
| Free-tier limits (Supabase 500MB, Tavily credits) | Low | Volume budgets in 02; Tavily capped per run |
| Worker offline during judging | Medium | Pinned finished runs make the site fully demoable statically; deploy worker before submission and monitor |
| Scope creep (more languages, auth, CI app) | High (self-inflicted) | The guardrails list in 00 is contractual: MVP = Python+pytest, no auth |

## G. Naming note

"FlakeProof" = the product promise (flake-proof tests) + what it produces (proof of flakes). Before publishing, do a quick trademark/name-collision sanity check (GitHub, PyPI, npm, domain). If taken, fallbacks: **ForkProof**, **FlakeLab**, **HeisenBust**. Renaming is one find-and-replace at M0 — decide before the first public post.
