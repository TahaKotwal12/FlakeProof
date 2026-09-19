# 00 — Master Plan

## One-liner

> **FlakeProof** — an autonomous agent that *proves* which of your tests are flaky, finds the root cause by controlled experiment, fixes them with NVIDIA Nemotron, and proves the fix works. Powered by the git-like branching of Nebius Token Factory Sandboxes.

## Target hackathon

- **Event:** Nebius x NVIDIA Global AI Hackathon — https://nebiusglobalaihackathon.devpost.com/
- **Deadline:** October 30, 2026 @ 10:00 AM PDT (10:30 PM IST)
- **Track:** Coding and Agentic Engineering ("Build coding agents and developer tools: agents that write, run, and test code in Token Factory Sandboxes")
- **Hard requirements:**
  1. Must run on Nebius Token Factory or Nebius AI Cloud.
  2. Must use at least one NVIDIA open-source model (we use the Nemotron family).
  3. Public repo with visible OSS license (we use MIT).
  4. Working demo URL.
  5. Demo video ≤ 3 minutes on YouTube, with audio explaining how Token Factory and Nemotron were used.
  6. Written feedback on Token Factory / NVIDIA tools.
- **Bonus prizes we target:** Best Use of Tavily ($3,000), Most Valuable Feedback ($100 × 10), City Winner ($500 × 20 — attend a local Builders & Brews event if one exists nearby).

## The problem (use these citations in the submission)

Flaky tests — tests that pass and fail on the *same code* — are one of the most expensive annoyances in software engineering:

- Developers spend **≥ 2.5% of all productive time** investigating, repairing, and monitoring flaky tests (industrial case study, ~30 devs / 1M SLOC, ICST 2024: https://doi.org/10.1109/icst60714.2024.00037).
- **Google spends 2–16% of its test-infrastructure resources** just re-running flaky tests (same study's related-work data).
- **56% of developers** encounter flaky tests monthly, weekly, or daily (Parry et al. survey, cited in arXiv:2504.16777).
- Repairing flakes alone costs teams ~**$2,250/month** (arXiv:2504.16777, 2025). That paper's conclusion: *"Future studies should focus on developing automated techniques to detect and triage systemic flakiness."* — we are building exactly that.

## Why existing tools don't solve it (competitive positioning)

| Tool | How it works | What it can't do |
| --- | --- | --- |
| Trunk Flaky Tests | Passively watches weeks of CI history; autofix agent reasons from logs/git history and opens a PR | Cannot detect on demand (needs history); **never empirically verifies its fix** |
| BuildPulse | Ingests CI results over time, ranks/quarantines flakes | Detection only; remediation is docs + data for humans |
| pytest-rerunfailures etc. | Re-runs failures to mask flakiness | Hides the problem, fixes nothing |

**FlakeProof's wedge:** *active experimentation instead of passive observation.*

1. **On-demand:** paste a repo URL → report in minutes. No CI history, no SDK, no weeks of data collection.
2. **Provable detection:** we fork ONE environment checkpoint into N *bit-identical* VMs and run the suite in parallel. Same code + same starting state + different outcomes = flakiness proven, environment drift eliminated as an explanation. Plain Docker/CI cannot do this cheaply; Sandboxes' git-like branching makes it one API call.
3. **Root cause by experiment, not guesswork:** forked branches with injected perturbations (order shuffle, CPU stress, clock shift, network cut, seed change) identify *which condition* triggers the failure.
4. **Verified fixes:** patch applied → 20 fresh forks re-run under the triggering condition → "Before: 7/20 failed. After: 0/20." Numbers, not vibes.

One-line pitch for the video: **"Flaky-test tools watch your CI history and guess. FlakeProof runs the experiment."**

## Judging criteria → how we score

| Criterion | Our answer |
| --- | --- |
| **Technological implementation** (use of Token Factory + Nemotron) | Sandboxes branching is the *core mechanism*, not a checkbox. Nemotron model routing: Nano for fast parsing/classification, Super/Ultra for diagnosis + patch generation. Every LLM call logged and shown in the UI ("powered by" transparency panel). |
| **Design** (complete product, not a proof of concept) | Full product loop: URL in → live pipeline visualization → shareable report page → downloadable patch. Empty/loading/error states specced in `07-UI-SPEC.md`. |
| **Potential impact** | Quantified problem (see citations), specific audience (OSS maintainers + any team with a test suite), evidence at submission time: a published "Flakiness Report" of 30–50 real OSS repos scanned by the tool. |
| **Quality of the idea** | Non-obvious use of the sponsor's flagship beta feature; demonstrates genuine understanding of the space by naming the incumbents and their gap. |

## System input / output (product level)

- **Input:** a public GitHub repository URL (MVP: Python projects using pytest), optional git ref, optional config (number of detection runs, perturbations to use, max tests to fix).
- **Output:**
  1. **Flake Report** (web page + JSON + Markdown export): list of proven-flaky tests with failure rates, root-cause category, evidence matrix, human-readable diagnosis.
  2. **Verified fix patch** (unified diff, downloadable, PR-ready) with before/after verification scoreboard.
  3. **Sandbox tree visualization**: the branching experiment shown live as it runs.

## Scope guardrails (what we will NOT build)

- **Python + pytest only.** No JS/Java/Go in the MVP. One language done flawlessly.
- **Patches modify test code only** (plus obvious test fixtures/conftest). We do not attempt production-code fixes — safer, reviewable, still valuable.
- **No auth/accounts.** Public runs, shareable slugs. Rate limiting by IP.
- **No payment, no GitHub App, no CI integration.** Those are "future work" slides, not code.
- **Max 3–5 flaky tests fixed per run** (configurable). Cap compute, keep demos tight.

## Milestones (ordered; each ends with commit + push + working state)

| # | Milestone | Definition of done |
| --- | --- | --- |
| M0 | Repo scaffold | `web/` (Next.js) + `worker/` (Python) skeletons run locally; CI lint |
| M1 | Database live | Supabase schema migrated; typed clients in web + worker; seed script |
| M2 | API + UI shell | POST/GET runs endpoints work against DB; home page submits, run page shows queued state via realtime |
| M3 | Worker + mock executor | Full pipeline runs end-to-end in MOCK mode; UI shows a complete fake run (this is the vertical slice — everything after this is swapping mock for real) |
| M4 | Real sandboxes: provision + detect | ConTree executor: clone, install (agent-assisted), checkpoint, 20-fork detection on the demo repo |
| M5 | Diagnosis | Perturbation matrix runs; Nemotron classifies root cause with evidence |
| M6 | Fix + verify | Patch generation, guarded apply, 20-fork verification scoreboard |
| M7 | Report + polish | Report page, patch/markdown export, gallery, OG images, mobile |
| M8 | Evidence run | Scan 30–50 real OSS repos; publish leaderboard page |
| M9 | Submission kit | Demo video, Devpost writeup, feedback doc, Tavily integration confirmed |

Working rule: **after M3 the product is always demoable.** If time runs out at any later milestone, we still submit something complete (e.g., detection-only is already a valid, impressive product: "we prove your tests are flaky").

## Team workflow

- Everything is built by pasting the sequenced prompts from `docs/06-CURSOR-PROMPTS.md` into Cursor, reviewing the diffs, and running the acceptance checks listed with each prompt.
- Commit and push after every milestone (the hackathon rewards authentic commit history; it also feeds #BuildInPublic content).
- Register on Devpost **now**, get the Nebius Token Factory API key **now** (credits + model catalog access), and join the Nebius Discord (needed for Sandboxes beta feedback → Most Valuable Feedback prize).

## First actions checklist

- [ ] Register on the Devpost hackathon page.
- [ ] Create Nebius Token Factory account, claim hackathon credits, generate `NEBIUS_API_KEY`.
- [ ] Verify the exact Nemotron model IDs in the Token Factory catalog and set them in env (see `01-ARCHITECTURE.md` → env vars). Do NOT hardcode model IDs.
- [ ] Verify Sandboxes/ConTree API base URL + auth from https://docs.tokenfactory.nebius.com/sandboxes/overview (start at https://docs.tokenfactory.nebius.com/llms.txt).
- [ ] Create Supabase project (free tier), note URL + anon key + service-role key.
- [ ] Create Tavily account (free tier) for the enrichment feature.
- [ ] Create the companion demo repo (`flakeproof-demo`, spec in `08-DEMO-AND-SUBMISSION.md`).
- [ ] Start M0 with Prompt 1 from `docs/06-CURSOR-PROMPTS.md`.
