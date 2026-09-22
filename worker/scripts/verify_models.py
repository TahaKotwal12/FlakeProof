#!/usr/bin/env python
"""Pre-flight check: confirm NEMOTRON_FAST_MODEL and NEMOTRON_SMART_MODEL are real
model IDs in the Token Factory catalog (`GET {base}/models`), per docs/04-API.md B1
and the "First actions checklist" in docs/00-MASTER-PLAN.md ("Do NOT hardcode model
IDs" — verify against the live catalog instead).

Usage: run from worker/ (needs worker/.env, or the vars already in the environment):

    python scripts/verify_models.py
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

REQUIRED_ENV_VARS = ("TOKEN_FACTORY_BASE_URL", "NEBIUS_API_KEY", "NEMOTRON_FAST_MODEL", "NEMOTRON_SMART_MODEL")


def main() -> int:
    load_dotenv()

    env = {name: os.environ.get(name) for name in REQUIRED_ENV_VARS}
    missing = [name for name, value in env.items() if not value]
    if missing:
        print(f"[FAIL] Missing env var(s): {', '.join(missing)} (see worker/.env.example)", file=sys.stderr)
        return 1

    base_url = env["TOKEN_FACTORY_BASE_URL"]
    models_url = base_url if base_url.endswith("/") else f"{base_url}/"
    client = OpenAI(base_url=base_url, api_key=env["NEBIUS_API_KEY"], timeout=30.0)

    try:
        catalog = list(client.models.list())
    except OpenAIError as exc:
        print(f"[FAIL] Could not list models from {models_url}models: {exc}", file=sys.stderr)
        return 1

    catalog_ids = {model.id for model in catalog}
    print(f"Fetched {len(catalog_ids)} model(s) from {models_url}models")

    ok = True
    for env_var in ("NEMOTRON_FAST_MODEL", "NEMOTRON_SMART_MODEL"):
        model_id = env[env_var]
        if model_id in catalog_ids:
            print(f"[OK]   {env_var}={model_id!r} found in the catalog")
            continue

        ok = False
        print(f"[FAIL] {env_var}={model_id!r} NOT found in the catalog.", file=sys.stderr)
        needle = model_id.rsplit("/", maxsplit=1)[-1].lower()
        close_matches = sorted(m for m in catalog_ids if needle in m.lower())
        if close_matches:
            print(f"       Did you mean one of: {', '.join(close_matches[:5])}?", file=sys.stderr)

    if not ok:
        print("\nSet the exact catalog IDs in worker/.env - see docs/01-ARCHITECTURE.md.", file=sys.stderr)
        return 1

    print("\nAll configured model IDs are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
