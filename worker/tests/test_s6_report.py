"""Unit tests for the pure formatting helpers in flakeproof.stages.s6_report
(P6 prompt-data assembly and the run_events headline) -- no DB or LLM needed.
"""

from __future__ import annotations

from datetime import UTC, datetime

from flakeproof.stages import s6_report as s6

_FLAKY_A = {"test_id": "tests/test_a.py::test_retry", "failure_rate": 0.35, "status": "fix_verified", "root_cause": "order_dependent", "verify_before_failures": 7, "verify_after_failures": 0, "verify_total": 20}
_FLAKY_B = {"test_id": "tests/test_b.py::test_flaky", "failure_rate": 0.2, "status": "fix_failed", "root_cause": "time_dependent", "verify_before_failures": 4, "verify_after_failures": 2, "verify_total": 20}
_FLAKY_UNDIAGNOSED = {"test_id": "tests/test_c.py::test_x", "failure_rate": 0.1, "status": "detected", "root_cause": None}


def test_flaky_list_with_rates_formats_percentages() -> None:
    assert s6._flaky_list_with_rates([_FLAKY_A, _FLAKY_B]) == "test_retry (35%), test_flaky (20%)"


def test_flaky_list_with_rates_empty() -> None:
    assert s6._flaky_list_with_rates([]) == "(none)"


def test_broken_list_filters_is_always_failing() -> None:
    test_stats = [
        {"test_id": "tests/test_a.py::test_ok", "is_always_failing": False},
        {"test_id": "tests/test_a.py::test_broken", "is_always_failing": True},
    ]
    assert s6._broken_list(test_stats) == "test_broken"


def test_broken_list_empty() -> None:
    assert s6._broken_list([{"test_id": "x", "is_always_failing": False}]) == "(none)"


def test_cause_summary_list_only_includes_diagnosed() -> None:
    assert s6._cause_summary_list([_FLAKY_A, _FLAKY_UNDIAGNOSED]) == "test_retry: order_dependent"


def test_cause_summary_list_empty() -> None:
    assert s6._cause_summary_list([_FLAKY_UNDIAGNOSED]) == "(none diagnosed)"


def test_verified_list_with_before_after() -> None:
    assert s6._verified_list_with_before_after([_FLAKY_A, _FLAKY_B]) == "test_retry (7/20 -> 0/20)"


def test_verified_list_with_before_after_empty() -> None:
    assert s6._verified_list_with_before_after([_FLAKY_B]) == "(none)"


def test_unfixed_list_with_reasons() -> None:
    assert s6._unfixed_list_with_reasons([_FLAKY_A, _FLAKY_B]) == "test_flaky (fix_failed)"


def test_headline_no_flakes() -> None:
    assert s6._headline([], 20) == "No flakiness detected in 20 identical runs"


def test_headline_flaky_no_fixes_verified() -> None:
    assert s6._headline([_FLAKY_B], 20) == "1 flaky test caught"


def test_headline_plural_and_verified() -> None:
    assert s6._headline([_FLAKY_A, _FLAKY_B], 20) == "2 flaky tests caught and 1 fixed with proof"


def test_parse_iso_with_offset() -> None:
    dt = s6._parse_iso("2026-09-22T10:00:00+00:00")
    assert dt.tzinfo is not None
    assert dt == datetime(2026, 9, 22, 10, 0, 0, tzinfo=UTC)
