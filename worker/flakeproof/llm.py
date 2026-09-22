"""Nemotron client via the OpenAI-compatible Token Factory API (docs/04-API.md B1,
docs/05-LLM-PROMPTS.md).

Routes each call by `purpose` to the fast model (Nemotron Nano — parsing, triage,
review, prose) or the smart model (Nemotron Super/Ultra — root-cause classification,
patch generation), per the "Model routing recap" in docs/05-LLM-PROMPTS.md. Prompt
templates live in `worker/flakeproof/prompts/*.md` and are rendered with
`{placeholder}` substitution.

Everything that actually talks to a model goes through the `LlmTransport` protocol —
mirrors `SandboxExecutor` in executors/base.py. `FakeLLM` is the `EXECUTOR=mock`
implementation (scripted, network-free); `OpenAICompatibleTransport` is the real one,
backed by `openai.AsyncOpenAI` pointed at `TOKEN_FACTORY_BASE_URL`.

Call `chat()` for the model interaction only (no DB access — easy to unit test with a
stubbed transport); call `run()` to also log the result to `llm_calls`.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Protocol

from dotenv import load_dotenv
from openai import (
    AsyncOpenAI,
    InternalServerError,
    OpenAIError,
    RateLimitError,
)
from supabase import Client

from flakeproof import db
from flakeproof.db import LlmCallPurpose

PROMPTS_DIR = Path(__file__).parent / "prompts"

ModelTier = str  # "fast" | "smart"

REQUEST_TIMEOUT_S = 120.0
MAX_TRANSPORT_RETRIES = 4  # up to 4 retries (5 attempts total) on 429/5xx
BASE_BACKOFF_S = 1.0

DEFAULT_TEMPERATURE = 0.2

# ============ routing (docs/05-LLM-PROMPTS.md "Model routing recap") ============

PURPOSE_TO_TIER: dict[LlmCallPurpose, ModelTier] = {
    "install_fix": "fast",  # P1
    "failure_parse": "fast",  # P2
    "root_cause": "smart",  # P3
    "patch_gen": "smart",  # P4
    "patch_review": "fast",  # P5
    "report": "fast",  # P6
    "tavily_summarize": "fast",  # P7
}

PURPOSE_TO_PROMPT_ID: dict[LlmCallPurpose, str] = {
    "install_fix": "P1_install_fixer",
    "failure_parse": "P2_failure_normalizer",
    "root_cause": "P3_root_cause_classifier",
    "patch_gen": "P4_patch_generator",
    "patch_review": "P5_patch_reviewer",
    "report": "P6_report_writer",
    "tavily_summarize": "P7_tavily_summarizer",
}

# P6 (report) returns markdown prose; every other purpose returns strict JSON.
JSON_OUTPUT_PURPOSES: frozenset[LlmCallPurpose] = frozenset(PURPOSE_TO_TIER) - {"report"}

# "temperature=0.2 (0.0 for P5 review)" (docs/05-LLM-PROMPTS.md).
PURPOSE_TEMPERATURE: dict[LlmCallPurpose, float] = {"patch_review": 0.0}


def route_model(purpose: LlmCallPurpose) -> str:
    """Which model id (env-configured) handles this purpose."""
    tier = PURPOSE_TO_TIER[purpose]
    env_var = "NEMOTRON_FAST_MODEL" if tier == "fast" else "NEMOTRON_SMART_MODEL"
    model = os.environ.get(env_var)
    if not model:
        raise RuntimeError(f"{env_var} must be set (see worker/.env.example)")
    return model


# ============ prompt templates ============


@dataclass(frozen=True)
class PromptTemplate:
    prompt_id: str
    system: str
    user_template: str


_SECTION_RE_TEMPLATE = r"^## {name}\s*\n(.*?)(?=\n## |\Z)"


def _parse_prompt_markdown(text: str, *, prompt_id: str) -> PromptTemplate:
    system_match = re.search(_SECTION_RE_TEMPLATE.format(name="System"), text, re.DOTALL | re.MULTILINE)
    user_match = re.search(_SECTION_RE_TEMPLATE.format(name="User"), text, re.DOTALL | re.MULTILINE)
    if not system_match or not user_match:
        raise ValueError(f"Prompt template {prompt_id!r} is missing a '## System' or '## User' section")
    return PromptTemplate(
        prompt_id=prompt_id,
        system=system_match.group(1).strip(),
        user_template=user_match.group(1).strip(),
    )


@cache
def load_prompt(prompt_id: str) -> PromptTemplate:
    """Load and parse `worker/flakeproof/prompts/{prompt_id}.md`. Cached: templates are static."""
    path = PROMPTS_DIR / f"{prompt_id}.md"
    text = path.read_text(encoding="utf-8")
    return _parse_prompt_markdown(text, prompt_id=prompt_id)


# Only bare `{identifier}` placeholders are substituted — every prompt's JSON output
# schema example (e.g. `{"reasoning": "...", "command": "..."}`) starts with `{"`, so
# it never matches this and is left untouched in the rendered prompt.
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def render_template(template: str, **values: Any) -> str:
    def _sub(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(f"Missing template placeholder: {{{key}}}")
        return str(values[key])

    return _PLACEHOLDER_RE.sub(_sub, template)


def render_prompt(purpose: LlmCallPurpose, **values: Any) -> tuple[str, str]:
    """Return (system, user) for `purpose` with `{placeholders}` filled from `values`."""
    template = load_prompt(PURPOSE_TO_PROMPT_ID[purpose])
    return template.system, render_template(template.user_template, **values)


# ============ transport (swappable: real Nemotron vs FakeLLM for EXECUTOR=mock) ============


@dataclass(frozen=True)
class CompletionResult:
    content: str
    prompt_tokens: int | None
    completion_tokens: int | None


class TransportError(Exception):
    """Non-retryable transport failure (bad request, auth, unknown error, ...)."""


class RetryableTransportError(TransportError):
    """A 429 or 5xx — worth retrying with backoff."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LlmTransport(Protocol):
    """Whatever actually talks to a model. `FakeLLM` implements this for EXECUTOR=mock."""

    async def complete(
        self,
        *,
        purpose: LlmCallPurpose,
        model: str,
        system: str,
        user: str,
        temperature: float,
        json_mode: bool,
    ) -> CompletionResult: ...


def get_client() -> AsyncOpenAI:
    """Return an AsyncOpenAI client configured with TOKEN_FACTORY_BASE_URL and NEBIUS_API_KEY.

    `max_retries=0`: chat()/`_complete_with_backoff` implement the retry/backoff policy
    from docs/04-API.md explicitly, so the SDK's own retrying is disabled to avoid
    stacking two uncoordinated retry loops.
    """
    load_dotenv()
    base_url = os.environ.get("TOKEN_FACTORY_BASE_URL")
    api_key = os.environ.get("NEBIUS_API_KEY")
    if not base_url or not api_key:
        raise RuntimeError("TOKEN_FACTORY_BASE_URL and NEBIUS_API_KEY must be set (see worker/.env.example)")
    return AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=REQUEST_TIMEOUT_S, max_retries=0)


def _retryable_from_openai(exc: RateLimitError | InternalServerError) -> RetryableTransportError:
    retry_after: float | None = None
    header_val = exc.response.headers.get("retry-after") if exc.response is not None else None
    if header_val:
        try:
            retry_after = float(header_val)
        except ValueError:
            retry_after = None
    return RetryableTransportError(str(exc), retry_after=retry_after)


class OpenAICompatibleTransport:
    """Talks to Nebius Token Factory's OpenAI-compatible Chat Completions endpoint."""

    def __init__(self, client: AsyncOpenAI) -> None:
        self._client = client

    async def complete(
        self,
        *,
        purpose: LlmCallPurpose,
        model: str,
        system: str,
        user: str,
        temperature: float,
        json_mode: bool,
    ) -> CompletionResult:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
        if json_mode:
            # If a model doesn't support this, well-behaved OpenAI-compatible gateways
            # ignore it rather than erroring — the parser's fenced-```json fallback
            # (try_parse_json) handles that case (docs/04-API.md B1).
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except (RateLimitError, InternalServerError) as exc:
            raise _retryable_from_openai(exc) from exc
        except OpenAIError as exc:
            raise TransportError(str(exc)) from exc

        choice = response.choices[0] if response.choices else None
        content = (choice.message.content if choice and choice.message else None) or ""
        usage = response.usage
        return CompletionResult(
            content=content,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
        )


# Scripted, schema-shaped responses per purpose — EXECUTOR=mock never touches the
# network (mirrors executors/mock.py's MockExecutor for sandboxes).
_FAKE_JSON_BY_PURPOSE: dict[LlmCallPurpose, dict[str, Any]] = {
    "install_fix": {"reasoning": "FakeLLM (EXECUTOR=mock): nothing to install.", "command": "true", "give_up": False},
    "failure_parse": {"failures": []},
    "root_cause": {
        "root_cause": "unknown",
        "confidence": 0.5,
        "key_evidence": ["FakeLLM (EXECUTOR=mock): no real evidence was gathered."],
        "diagnosis_md": "### Mock diagnosis\n\nThis is a scripted response from FakeLLM (EXECUTOR=mock).",
    },
    "patch_gen": {"files": [], "patch": "", "rationale_md": "FakeLLM (EXECUTOR=mock): no patch generated."},
    "patch_review": {"approved": False, "objections": ["FakeLLM (EXECUTOR=mock): nothing to review."], "risk_notes": []},
    "tavily_summarize": {"known_reports": []},
}
_FAKE_MARKDOWN = "### Mock report\n\nThis run used `EXECUTOR=mock`; no real Nemotron calls were made."


class FakeLLM:
    """The `EXECUTOR=mock` LLM transport: deterministic, network-free, zero credentials needed."""

    async def complete(
        self,
        *,
        purpose: LlmCallPurpose,
        model: str,
        system: str,
        user: str,
        temperature: float,
        json_mode: bool,
    ) -> CompletionResult:
        await asyncio.sleep(0)  # stay a real coroutine without a fake delay
        if not json_mode:
            content = _FAKE_MARKDOWN
        else:
            content = json.dumps(_FAKE_JSON_BY_PURPOSE.get(purpose, {}))
        return CompletionResult(content=content, prompt_tokens=0, completion_tokens=0)


def get_transport() -> LlmTransport:
    """FakeLLM for EXECUTOR=mock (matches SandboxExecutor selection); real transport otherwise."""
    load_dotenv()
    if os.environ.get("EXECUTOR", "mock").strip().lower() == "mock":
        return FakeLLM()
    return OpenAICompatibleTransport(get_client())


# ============ retry/backoff (429/5xx, max 4 retries) ============


async def _complete_with_backoff(
    transport: LlmTransport,
    *,
    purpose: LlmCallPurpose,
    model: str,
    system: str,
    user: str,
    temperature: float,
    json_mode: bool,
    sleep: Callable[[float], Awaitable[None]],
) -> CompletionResult:
    last_error: RetryableTransportError | None = None
    for attempt in range(MAX_TRANSPORT_RETRIES + 1):
        try:
            return await transport.complete(
                purpose=purpose, model=model, system=system, user=user, temperature=temperature, json_mode=json_mode
            )
        except RetryableTransportError as exc:
            last_error = exc
            if attempt == MAX_TRANSPORT_RETRIES:
                break
            delay = exc.retry_after if exc.retry_after is not None else BASE_BACKOFF_S * (2**attempt)
            await sleep(delay)
    assert last_error is not None
    raise last_error


# ============ JSON parsing (direct, then fenced-block fallback) ============

_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def try_parse_json(text: str) -> dict[str, Any] | None:
    """Try `text` as raw JSON, then fall back to the first fenced ```json block."""
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    match = _FENCED_JSON_RE.search(text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(1))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


# ============ chat() — the model interaction, no DB access ============


@dataclass(frozen=True)
class LlmAttempt:
    """One HTTP call that returned a response (429/5xx retries that never got one aren't attempts)."""

    model: str
    ok: bool
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int


@dataclass(frozen=True)
class ChatResult:
    ok: bool
    purpose: LlmCallPurpose
    content: str | None
    data: dict[str, Any] | None
    attempts: tuple[LlmAttempt, ...] = field(default_factory=tuple)
    error: str | None = None


_REASK_INSTRUCTION = "Return ONLY valid JSON. No prose, no markdown code fences."


async def chat(
    purpose: LlmCallPurpose,
    template_vars: dict[str, Any] | None = None,
    *,
    transport: LlmTransport | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> ChatResult:
    """Render the purpose's prompt, call the routed model (retrying 429/5xx with
    backoff), and for JSON-output purposes parse the response — falling back to a
    fenced ```json block, then to one strict-JSON re-ask, before giving up.

    Pure LLM interaction: no DB access, so it's directly unit-testable with a stubbed
    `transport`. Pair with `log_call()` (or use `run()`) to record it in `llm_calls`.
    """
    transport = transport or get_transport()
    model = route_model(purpose)
    system, user = render_prompt(purpose, **(template_vars or {}))
    temperature = PURPOSE_TEMPERATURE.get(purpose, DEFAULT_TEMPERATURE)
    json_mode = purpose in JSON_OUTPUT_PURPOSES

    attempts: list[LlmAttempt] = []

    async def _attempt(sys_msg: str, user_msg: str) -> str:
        start = time.monotonic()
        try:
            result = await _complete_with_backoff(
                transport,
                purpose=purpose,
                model=model,
                system=sys_msg,
                user=user_msg,
                temperature=temperature,
                json_mode=json_mode,
                sleep=sleep,
            )
        except TransportError:
            latency_ms = int((time.monotonic() - start) * 1000)
            attempts.append(LlmAttempt(model=model, ok=False, prompt_tokens=None, completion_tokens=None, latency_ms=latency_ms))
            raise
        latency_ms = int((time.monotonic() - start) * 1000)
        attempts.append(
            LlmAttempt(
                model=model,
                ok=True,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                latency_ms=latency_ms,
            )
        )
        return result.content

    try:
        content = await _attempt(system, user)
    except TransportError as exc:
        return ChatResult(ok=False, purpose=purpose, content=None, data=None, attempts=tuple(attempts), error=str(exc))

    if not json_mode:
        return ChatResult(ok=True, purpose=purpose, content=content, data=None, attempts=tuple(attempts))

    data = try_parse_json(content)
    if data is not None:
        return ChatResult(ok=True, purpose=purpose, content=content, data=data, attempts=tuple(attempts))

    # One strict-JSON re-ask, giving the model its own unparsable output as context.
    reask_user = f"{user}\n\nYour previous response could not be parsed as JSON:\n{content}\n\n{_REASK_INSTRUCTION}"
    try:
        content = await _attempt(system, reask_user)
    except TransportError as exc:
        return ChatResult(ok=False, purpose=purpose, content=None, data=None, attempts=tuple(attempts), error=str(exc))

    data = try_parse_json(content)
    if data is not None:
        return ChatResult(ok=True, purpose=purpose, content=content, data=data, attempts=tuple(attempts))

    return ChatResult(
        ok=False,
        purpose=purpose,
        content=content,
        data=None,
        attempts=tuple(attempts),
        error="Model did not return valid JSON, even after a strict-JSON re-ask.",
    )


# ============ DB logging ============


async def log_call(
    db_client: Client,
    *,
    run_id: str | None,
    stage: str,
    result: ChatResult,
) -> None:
    """Log every attempt in `result` to `llm_calls` (docs/05-LLM-PROMPTS.md: "Every call
    logged to llm_calls with purpose") — powers the "How we used Nemotron" UI panel.
    """
    if not result.attempts:
        return
    rows: list[db.LlmCallInsert] = [
        {
            "run_id": run_id,
            "stage": stage,
            "purpose": result.purpose,
            "model": attempt.model,
            "prompt_tokens": attempt.prompt_tokens,
            "completion_tokens": attempt.completion_tokens,
            "latency_ms": attempt.latency_ms,
            "ok": attempt.ok,
        }
        for attempt in result.attempts
    ]
    await db.insert_llm_calls(db_client, rows)


async def run(
    db_client: Client,
    purpose: LlmCallPurpose,
    template_vars: dict[str, Any] | None = None,
    *,
    run_id: str | None,
    stage: str,
    transport: LlmTransport | None = None,
) -> ChatResult:
    """`chat()` + `log_call()` — the entry point stages should use."""
    result = await chat(purpose, template_vars, transport=transport)
    await log_call(db_client, run_id=run_id, stage=stage, result=result)
    return result
