"""Unit tests for the pure verdict-math helpers: S2's flaky/always-failing
classification (docs/03-PIPELINE.md Stage 2 step 4) and S5's triggering-
condition pick + verified/failed decision (Stage 5 steps 1 and 6).
"""

from __future__ import annotations

from flakeproof.stages import s2_detect, s5_verify

# ============ S2: classify() ============


def test_classify_stable_passing_test() -> None:
    is_flaky, is_always_failing = s2_detect.classify(pass_count=20, fail_count=0, error_count=0, timeout_count=0)
    assert not is_flaky
    assert not is_always_failing


def test_classify_flaky_test() -> None:
    is_flaky, is_always_failing = s2_detect.classify(pass_count=13, fail_count=7, error_count=0, timeout_count=0)
    assert is_flaky
    assert not is_always_failing


def test_classify_always_failing_test() -> None:
    is_flaky, is_always_failing = s2_detect.classify(pass_count=0, fail_count=20, error_count=0, timeout_count=0)
    assert not is_flaky
    assert is_always_failing


def test_classify_errors_and_timeouts_count_as_bad() -> None:
    is_flaky, is_always_failing = s2_detect.classify(pass_count=15, fail_count=0, error_count=3, timeout_count=2)
    assert is_flaky
    assert not is_always_failing


def test_classify_no_observed_runs_is_neither() -> None:
    # A test that never appeared in any readable report (every fork crashed).
    is_flaky, is_always_failing = s2_detect.classify(pass_count=0, fail_count=0, error_count=0, timeout_count=0)
    assert not is_flaky
    assert not is_always_failing


def test_classify_single_failure_among_many_is_flaky_not_always_failing() -> None:
    is_flaky, is_always_failing = s2_detect.classify(pass_count=19, fail_count=1, error_count=0, timeout_count=0)
    assert is_flaky
    assert not is_always_failing


# ============ S5: _pick_triggering_condition() ============


def test_pick_triggering_condition_highest_failure_rate_wins() -> None:
    evidence = {
        "matrix": {
            "alone": {"runs": 6, "failures": 0},
            "order": {"runs": 6, "failures": 5},
            "cpu_stress": {"runs": 6, "failures": 1},
            "time_shift": {"runs": 6, "failures": 0},
            "net_off": {"runs": 6, "failures": 0},
            "seed": {"runs": 6, "failures": 4},
        }
    }
    assert s5_verify._pick_triggering_condition(evidence) == "order"


def test_pick_triggering_condition_ignores_zero_run_entries() -> None:
    evidence = {
        "matrix": {
            "alone": {"runs": 0, "failures": 0},
            "cpu_stress": {"runs": 0, "failures": 0},  # skipped perturbation (feature unavailable)
            "time_shift": {"runs": 6, "failures": 3},
        }
    }
    assert s5_verify._pick_triggering_condition(evidence) == "time_shift"


def test_pick_triggering_condition_falls_back_to_none_when_nothing_failed() -> None:
    evidence = {"matrix": {"alone": {"runs": 6, "failures": 0}, "order": {"runs": 6, "failures": 0}}}
    assert s5_verify._pick_triggering_condition(evidence) == "none"


def test_pick_triggering_condition_empty_evidence_falls_back_to_none() -> None:
    assert s5_verify._pick_triggering_condition({}) == "none"
