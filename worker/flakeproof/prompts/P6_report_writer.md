<!--
ID: P6 · Purpose: report · Model: FAST (Nemotron Nano) · Stage: S6
Output: Markdown prose (not JSON) — per-flake sections are assembled from stored fields
in code, not by this prompt (docs/05-LLM-PROMPTS.md).
Source: docs/05-LLM-PROMPTS.md "P6 — Report writer (stage S6)". Verbatim.
-->

## System

You write crisp engineering reports. Markdown. No hype, no emojis, no filler. Use the
exact numbers provided. Audience: the repo's maintainers.

## User

Write the summary section (150-250 words) of a flaky-test report for {owner}/{repo}@{sha7}.
Data:
- tests collected: {tests_collected}; identical detection runs: {detect_runs}
- proven flaky: {flaky_list_with_rates}
- always-failing (excluded): {broken_list}
- diagnoses: {cause_summary_list}
- verified fixes: {verified_list_with_before_after}
- unfixed: {unfixed_list_with_reasons}
Explain in one sentence how detection works (N forks of one checkpoint = same code, same
starting state) so readers trust the numbers. End with next-step advice for maintainers.
