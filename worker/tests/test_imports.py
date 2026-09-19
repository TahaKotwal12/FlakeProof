"""Smoke test: every flakeproof module should be importable."""

from __future__ import annotations

import importlib

MODULES = [
    "flakeproof.config",
    "flakeproof.db",
    "flakeproof.llm",
    "flakeproof.main",
    "flakeproof.perturbations",
    "flakeproof.pytest_parse",
    "flakeproof.seed_demo",
    "flakeproof.tavily_enrich",
    "flakeproof.executors.base",
    "flakeproof.executors.contree",
    "flakeproof.executors.docker_local",
    "flakeproof.executors.mock",
    "flakeproof.stages.s0_intake",
    "flakeproof.stages.s1_provision",
    "flakeproof.stages.s2_detect",
    "flakeproof.stages.s3_diagnose",
    "flakeproof.stages.s4_fix",
    "flakeproof.stages.s5_verify",
    "flakeproof.stages.s6_report",
]


def test_all_modules_import() -> None:
    for module_name in MODULES:
        importlib.import_module(module_name)
