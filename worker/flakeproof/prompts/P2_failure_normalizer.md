<!--
ID: P2 · Purpose: failure_parse · Model: FAST (Nemotron Nano) · Stages: S2/S3 (batched)
Output: JSON {"failures": [...]}
Source: docs/05-LLM-PROMPTS.md "P2 — Failure normalizer (stages S2/S3, batched)". Verbatim.
-->

## System

You normalize pytest failure output into structured records. Be precise; copy exact
error class names. Respond with strict JSON only.

## User

Here are {n} raw pytest failure blocks from different runs of the same test suite.

{failure_blocks_with_indices}

For each block return:
{"failures": [{"index": 0, "test_id": "<nodeid>", "error_type": "<e.g. AssertionError, TimeoutError>",
  "message": "<first line>", "top_frame": "<file:line of deepest in-repo frame>",
  "smells": ["<any of: sleep_in_test, real_network_call, shared_module_state, time_now_usage, unseeded_random, thread_or_asyncio, external_service, tmpfile_collision>"]}]}
