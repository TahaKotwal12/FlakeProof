"""Unit tests for flakeproof.llm, exercised with a stubbed LlmTransport — no network,
no Supabase (chat() is pure LLM interaction; see docs/05-LLM-PROMPTS.md, docs/04-API.md B1).
"""

from __future__ import annotations

from typing import Any

import pytest

from flakeproof import llm


class StubTransport:
    """Replays a scripted sequence of results/exceptions, one per `complete()` call."""

    def __init__(self, script: list[llm.CompletionResult | Exception]) -> None:
        self._script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def complete(self, **kwargs: Any) -> llm.CompletionResult:
        self.calls.append(kwargs)
        if not self._script:
            raise AssertionError("StubTransport script exhausted — unexpected extra call")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


async def _no_delay(_seconds: float) -> None:
    """Stand-in for asyncio.sleep so backoff tests don't actually wait."""
    return


@pytest.fixture(autouse=True)
def _model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEMOTRON_FAST_MODEL", "nemotron-nano-test")
    monkeypatch.setenv("NEMOTRON_SMART_MODEL", "nemotron-super-test")


def _valid_review_json() -> str:
    return '{"approved": true, "objections": [], "risk_notes": []}'


@pytest.mark.asyncio
async def test_retries_on_429_then_succeeds() -> None:
    transport = StubTransport(
        [
            llm.RetryableTransportError("rate limited", retry_after=0),
            llm.RetryableTransportError("rate limited", retry_after=0),
            llm.CompletionResult(content=_valid_review_json(), prompt_tokens=10, completion_tokens=5),
        ]
    )

    result = await llm.chat(
        "patch_review",
        {"root_cause": "order_dependent", "patch": "--- a/x\n+++ b/x\n"},
        transport=transport,
        sleep=_no_delay,
    )

    assert result.ok is True
    assert result.data == {"approved": True, "objections": [], "risk_notes": []}
    # 2 failed attempts (retried) + 1 successful call to the transport...
    assert len(transport.calls) == 3
    # ...but only the successful one is logged as an `llm_calls` attempt.
    assert len(result.attempts) == 1
    assert result.attempts[0].ok is True
    assert result.attempts[0].prompt_tokens == 10
    assert result.attempts[0].completion_tokens == 5


@pytest.mark.asyncio
async def test_exhausting_retries_returns_failed_result_not_an_exception() -> None:
    transport = StubTransport([llm.RetryableTransportError("still limited", retry_after=0) for _ in range(10)])

    result = await llm.chat("patch_review", {"root_cause": "x", "patch": "diff"}, transport=transport, sleep=_no_delay)

    assert result.ok is False
    assert result.error is not None
    # 1 initial + 4 retries = 5 attempts, per docs/04-API.md B1 ("max 4" retries).
    assert len(transport.calls) == 5
    assert len(result.attempts) == 1
    assert result.attempts[0].ok is False


@pytest.mark.asyncio
async def test_fenced_json_fallback_when_response_is_not_raw_json() -> None:
    prose_wrapped = 'Sure, here you go:\n```json\n{"approved": false, "objections": ["uses sleep()"], "risk_notes": []}\n```\nLet me know if you need anything else.'
    transport = StubTransport([llm.CompletionResult(content=prose_wrapped, prompt_tokens=20, completion_tokens=8)])

    result = await llm.chat("patch_review", {"root_cause": "x", "patch": "diff"}, transport=transport, sleep=_no_delay)

    assert result.ok is True
    assert result.data == {"approved": False, "objections": ["uses sleep()"], "risk_notes": []}
    # Extracted from the fenced block without needing a re-ask.
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_reasks_once_on_invalid_json_then_succeeds() -> None:
    transport = StubTransport(
        [
            llm.CompletionResult(content="Sorry, I can't help with that request.", prompt_tokens=5, completion_tokens=5),
            llm.CompletionResult(content=_valid_review_json(), prompt_tokens=12, completion_tokens=6),
        ]
    )

    result = await llm.chat("patch_review", {"root_cause": "x", "patch": "diff"}, transport=transport, sleep=_no_delay)

    assert result.ok is True
    assert result.data == {"approved": True, "objections": [], "risk_notes": []}
    assert len(transport.calls) == 2
    # The re-ask carries the model's own bad output plus the strict-JSON instruction.
    reask_user = transport.calls[1]["user"]
    assert "Return ONLY valid JSON" in reask_user
    assert "Sorry, I can't help" in reask_user
    # Both calls got a real HTTP response (attempt.ok is transport-level success, not
    # "content parsed as JSON") — both are logged.
    assert [a.ok for a in result.attempts] == [True, True]


@pytest.mark.asyncio
async def test_reasks_once_then_gives_up_on_invalid_json() -> None:
    transport = StubTransport(
        [
            llm.CompletionResult(content="still not JSON", prompt_tokens=5, completion_tokens=5),
            llm.CompletionResult(content="also still not JSON", prompt_tokens=5, completion_tokens=5),
        ]
    )

    result = await llm.chat("patch_review", {"root_cause": "x", "patch": "diff"}, transport=transport, sleep=_no_delay)

    assert result.ok is False
    assert result.data is None
    assert result.error is not None
    # Exactly one re-ask — not a retry loop.
    assert len(transport.calls) == 2
    # Both calls succeeded at the transport level; ChatResult.ok is False because
    # neither response was parsable JSON, not because the calls themselves failed.
    assert [a.ok for a in result.attempts] == [True, True]


@pytest.mark.asyncio
async def test_markdown_purpose_is_returned_verbatim_without_json_parsing() -> None:
    transport = StubTransport([llm.CompletionResult(content="# Report\n\nAll clear.", prompt_tokens=1, completion_tokens=1)])

    result = await llm.chat(
        "report",
        {
            "owner": "octocat",
            "repo": "demo",
            "sha7": "abc1234",
            "tests_collected": 10,
            "detect_runs": 20,
            "flaky_list_with_rates": "none",
            "broken_list": "none",
            "cause_summary_list": "none",
            "verified_list_with_before_after": "none",
            "unfixed_list_with_reasons": "none",
        },
        transport=transport,
        sleep=_no_delay,
    )

    assert result.ok is True
    assert result.content == "# Report\n\nAll clear."
    assert result.data is None
    # P6 shouldn't request JSON mode.
    assert transport.calls[0]["json_mode"] is False


def test_all_seven_prompt_templates_load_and_render() -> None:
    for purpose in llm.PURPOSE_TO_PROMPT_ID:
        system, user = llm.render_prompt(
            purpose,
            owner="o", repo="r", relevant_manifest_list="pyproject.toml", failed_command="pip install .", exit_code=1, stderr_tail_120_lines="boom", numbered_list_of_previous_commands_and_results="1. none", n=3, failure_blocks_with_indices="...", test_id="tests/test_x.py::test_y", k=1, rate=0.5, evidence_matrix_table="...", normalized_failures_json="[]", file_path="tests/test_x.py", test_source="...", fixtures_source="...", tavily_known_reports="[]", root_cause="unknown", confidence=0.5, diagnosis_md="...", evidence_matrix_compact="...", numbered_test_file="...", conftest_source="...", failure_log_tail="...", patch="...", sha7="abc1234", tests_collected=1, detect_runs=20, flaky_list_with_rates="...", broken_list="...", cause_summary_list="...", verified_list_with_before_after="...", unfixed_list_with_reasons="...", results_json="[]",
        )
        assert system.strip()
        assert user.strip()
        # A literal JSON schema example in the doc text (e.g. P1's `{"reasoning": ...}`)
        # must survive rendering untouched, not be swallowed by placeholder substitution.
        assert "{" in user or "reasoning" not in user
