"""Environment configuration and run defaults, loaded from worker/.env."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Typed view of the environment variables listed in docs/01-ARCHITECTURE.md."""

    supabase_url: str
    supabase_service_role_key: str
    executor: str
    nebius_api_key: str | None
    nebius_project_id: str | None
    token_factory_base_url: str
    contree_base_url: str | None
    nemotron_fast_model: str
    nemotron_smart_model: str
    tavily_api_key: str | None
    github_token: str | None
    max_concurrent_sandboxes: int
    max_active_runs: int


def load_settings() -> Settings:
    """Load, validate, and return Settings from the process environment (.env in dev)."""
    raise NotImplementedError
