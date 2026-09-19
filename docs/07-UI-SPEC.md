# 07 — UI Specification

## Design direction

- **Feel:** precision instrument, not toy. Think "lab equipment for code" — the product's whole pitch is *proof*, so the UI leans on numbers, monospace accents, and live telemetry.
- **Theme:** dark by default. Background `#0a0e14`, surface `#11161f`, border `#1e2633`. Accent: electric green `#22c55e` for pass/verified, `#ef4444` for fail, `#f59e0b` for flaky (the brand color — flaky = amber warning), `#38bdf8` for info/running.
- **Type:** Inter for UI, JetBrains Mono for test IDs, logs, diffs, numbers.
- **Components:** shadcn/ui primitives only (button, input, card, badge, dialog, progress, tabs, table, sonner toasts). No second component library.
- Subtle motion: forks appearing in the grid animate in with a 150ms scale/fade; no gratuitous animation elsewhere.

## Pages

### 1. Home `/`

| Section | Content |
| --- | --- |
| Hero | Wordmark + tagline: **"Flaky-test tools watch your CI and guess. FlakeProof runs the experiment."** Sub-line: "Paste a repo. Get proof, root causes, and verified fixes — powered by NVIDIA Nemotron on Nebius Token Factory Sandboxes." |
| RepoSubmitForm | Single input (placeholder `https://github.com/owner/repo`) + "Advanced" disclosure (git ref, detect runs slider 5–30, max fixes 0–5) + primary button **"Run the experiment"**. Client-side URL validation; on 201 → navigate to `/runs/{slug}`; on 409 → toast with link to the active run; on 429 → toast explaining the limit. |
| How it works | 4 horizontal steps with mono numerals: ① Clone into a sandbox checkpoint → ② Fork into 20 identical VMs → ③ Perturb: order, clock, CPU, network → ④ Fix with Nemotron, verify with 20 more forks. One sentence each. |
| RecentRunsGallery | Grid of run cards: `owner/repo`, status badge, headline stat ("3 flaky · 2 fixed ✓" or "clean in 20×"), relative time. Click → run page. |
| Footer | GitHub repo, "Built for the Nebius x NVIDIA Global AI Hackathon", MIT, Tavily attribution. |

**States:** gallery empty → "No public runs yet. Yours can be first." with arrow to form. Gallery loading → 6 skeleton cards.

### 2. Run page `/runs/[slug]` — the centerpiece

Layout (desktop): left column 2/3, right column 1/3.

```
┌────────────────────────────────────────────┬──────────────────────┐
│ RunHeader: owner/repo @sha7 · status badge │ NemotronPanel        │
│ PipelineStepper (S0→S6)                    │ (model usage, live)  │
│ SandboxGrid  ← the wow element             │ RunMetaCard          │
│ FindingsList (cards appear live)           │ (config, commit,     │
│ LiveConsole (collapsible, autoscroll)      │  cancel button)      │
└────────────────────────────────────────────┴──────────────────────┘
```

Components:

- **PipelineStepper** — 7 steps (Intake, Provision, Detect, Diagnose, Fix, Verify, Report) with states pending/running(pulse)/done/failed/skipped. Driven by `runs.status` realtime.
- **SandboxGrid** — the signature visualization. A grid of small squares, one per fork in the current wave (from `sandbox_ops` inserts). States: spawning (gray pulse) → running (blue) → pass (green) / fail (red flash then persistent amber ring). Wave label above: `"Detection: 20 identical forks from checkpoint img_4f2a"` / `"Perturbation: order shuffle ×6"`. During verify: two grids side by side labeled **BEFORE** / **AFTER** with big mono counters `7/20 failed` vs `0/20 failed`. On `done`, the grid area collapses into per-wave summary chips.
- **FindingsList** — one **FlakeCard** per `flaky_tests` row, appearing live (realtime insert) and upgrading as status advances:
  - Header: mono `tests/test_api.py::test_retry` + failure-rate badge `35%` + status chip (Detected → Diagnosing → Diagnosed → Fixing → Verifying → ✅ Fix verified / ⚠️ Fix failed / ⏭ Skipped).
  - Body tabs: **Diagnosis** (root-cause badge + confidence meter + `diagnosis_md` rendered + evidence matrix as a compact table with failure cells highlighted) · **Fix** (diff viewer, mono, +green/−red lines, copy button, `fix_rationale_md`) · **Proof** (before/after scoreboard + triggering condition label) · **Evidence** (sample failure log, Tavily `known_reports` chips).
- **LiveConsole** — mono log of `run_events` (ts, stage tag, message), autoscroll with pin-to-bottom toggle, level coloring, collapsed to last 3 lines by default on mobile.
- **NemotronPanel** — "Powered by NVIDIA Nemotron on Nebius Token Factory": live counters of calls by model (from `llm_calls` realtime), last purpose ("diagnosing root cause…"), and a Sandboxes counter ("96 forks executed"). This panel is deliberate judging material — it makes the sponsor-tech usage visible in every screenshot.
- **RunMetaCard** — repo link, commit, config summary, created/elapsed, Cancel button (confirm dialog) while cancelable, share button (copies URL).

**States:**

- `queued` → stepper all pending + "Waiting for a worker… usually a few seconds" + gentle skeleton grid.
- `failed` → red banner with `error` code translated to a human sentence + "What you can try" hints (e.g., unsupported stack → "MVP supports Python + pytest") + console open.
- `canceled` → neutral banner.
- Websocket drop → silent switch to 5s polling; tiny "live" dot turns amber.
- Deep-linked finished run (most judges!) → renders instantly from the composite GET, no websocket needed.

### 3. Report view (same route, `status=done`)

Replaces the live area with:

1. **VerdictBanner** — big headline: `"3 flaky tests caught · 2 fixed with proof"` or `"Clean: no flakiness in 20 identical runs"` + method one-liner + `Scanned {n} tests at {sha7}`.
2. FindingsList in final form (all tabs populated).
3. **AlwaysFailingCallout** (if any): "These tests failed in all 20 runs — broken, not flaky. Excluded from fixing."
4. **ExportBar** — buttons: `Download report.md` · `Download patch.diff` · `Copy shareable link`.
5. **MethodologyFootnote** — collapsible: exact config JSON, base image, sandbox counts, LLM call counts, links to the repo + hackathon.

### 4. Leaderboard `/leaderboard`

- Hero stat bar: `Repos scanned · Identical runs executed · Flaky tests caught · Fixes verified` (big mono numbers).
- Table: repo (link to GitHub) · tests · detect runs · flaky found · worst offender (test id, failure rate) · fixed · report link. Sortable by flaky found. Row click → run page.
- Methodology note + "Scan your repo" CTA back to home.
- Empty state (pre-M8): "The public scan is coming — run your own repo meanwhile."

## Accessibility & responsiveness

- All state colors paired with icons/text (never color-only). Focus rings visible. `prefers-reduced-motion` disables grid animations (counters still update).
- Mobile: single column; SandboxGrid becomes wave counters (`Detect: 14/20 done · 5 fail`); FlakeCard tabs become an accordion; console collapsed by default.

## Polish checklist (executed by Prompt 12)

- [ ] OG image per run (`/runs/[slug]/opengraph-image`): dark card with repo name + headline stat — this is what gets shared on X/LinkedIn for #BuildInPublic.
- [ ] Favicon + wordmark (simple: mono "F/" glyph in amber).
- [ ] Skeletons for every data region; no layout shift on load.
- [ ] Error toasts with retry actions; API error codes mapped to human copy in one `errorCopy.ts` map.
- [ ] Cancel flow wired with confirm dialog + optimistic status.
- [ ] Keyboard: form submittable via Enter, tabs arrow-navigable, dialog focus-trapped.
- [ ] Lighthouse accessibility ≥ 90.
- [ ] Real copy everywhere (no lorem, no "Welcome to your app").
- [ ] 404 page for unknown slugs with link home.
