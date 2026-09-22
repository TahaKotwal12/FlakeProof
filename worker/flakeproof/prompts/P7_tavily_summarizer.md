<!--
ID: P7 · Purpose: tavily_summarize · Model: FAST (Nemotron Nano) · Stage: S3 (optional)
Output: JSON {"known_reports": [...]}
Source: docs/05-LLM-PROMPTS.md "P7 — Tavily result summarizer (stage S3, optional)". Verbatim.
-->

## System

You extract only genuinely relevant references. Strict JSON.

## User

We are diagnosing flaky test {test_id} in {owner}/{repo}.
Tavily search results:
{results_json}

Keep only results that plausibly discuss THIS test or THIS repo's flakiness
(same repo, same test name, or same error signature). Return JSON:
{"known_reports": [{"title": "...", "url": "...", "snippet": "<=200 chars", "relevance": "<why>"}]}
Return {"known_reports": []} if nothing is truly relevant.
