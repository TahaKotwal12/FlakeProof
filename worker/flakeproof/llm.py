"""Nemotron client via the OpenAI-compatible Token Factory API.

Routes calls to the fast model (Nemotron Nano — parsing, triage, prose) or
the smart model (Nemotron Super/Ultra — root-cause classification, patch
generation), and logs every call to the `llm_calls` table.
"""

from __future__ import annotations

from typing import Any, Literal

from openai import OpenAI

ModelPurpose = Literal["fast", "smart"]


def get_client() -> OpenAI:
    """Return an OpenAI-compatible client configured with TOKEN_FACTORY_BASE_URL and NEBIUS_API_KEY."""
    raise NotImplementedError


async def chat(purpose: ModelPurpose, messages: list[dict[str, str]], **kwargs: Any) -> str:
    """Route a chat completion to the model for `purpose`, logging model/tokens/latency."""
    raise NotImplementedError
