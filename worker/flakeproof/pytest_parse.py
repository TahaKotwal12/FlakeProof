"""JUnit XML / pytest output parsing into structured test results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TestResult:
    """One test's outcome from a single pytest run."""

    nodeid: str
    outcome: str
    duration_s: float
    message: str | None


def parse_junit_xml(xml_text: str) -> list[TestResult]:
    """Parse a JUnit XML report produced by `pytest --junitxml` into TestResult rows."""
    raise NotImplementedError


def parse_pytest_stdout(stdout: str) -> list[TestResult]:
    """Fallback parser for plain pytest stdout when JUnit XML isn't available."""
    raise NotImplementedError
