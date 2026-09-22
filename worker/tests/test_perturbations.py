"""Unit tests for flakeproof.perturbations: command construction and the
usable/skipped feature-availability split (no sandbox needed).
"""

from __future__ import annotations

from flakeproof import perturbations as pert


def test_build_commands_alone_targets_single_test() -> None:
    commands = pert.build_commands("alone", "tests/test_api.py::test_retry", k=3, per_test_timeout_s=30)
    assert len(commands) == 3
    for cmd in commands:
        assert 'pytest "tests/test_api.py::test_retry"' in cmd.command
        assert "--junitxml=/tmp/report.xml" in cmd.command
        assert cmd.env_vars is None


def test_build_commands_order_runs_full_suite_with_varying_seed() -> None:
    commands = pert.build_commands("order", "tests/test_api.py::test_retry", k=3, per_test_timeout_s=30)
    seeds = [cmd.command for cmd in commands]
    assert "--random-order-seed=0" in seeds[0]
    assert "--random-order-seed=1" in seeds[1]
    assert "--random-order-seed=2" in seeds[2]
    # Full suite: the target test id is not pinned as a pytest argument.
    assert '"tests/test_api.py::test_retry"' not in seeds[0]


def test_build_commands_cpu_stress_backgrounds_stress_ng() -> None:
    commands = pert.build_commands("cpu_stress", "tests/test_api.py::test_retry", k=1, per_test_timeout_s=30)
    assert "stress-ng --cpu 2 --timeout 30s &" in commands[0].command
    assert 'pytest "tests/test_api.py::test_retry"' in commands[0].command


def test_build_commands_time_shift_alternates_variants() -> None:
    commands = pert.build_commands("time_shift", "tests/test_api.py::test_retry", k=4, per_test_timeout_s=30)
    assert "faketime '2026-12-31 23:59:55'" in commands[0].command
    assert "faketime '+37h'" in commands[1].command
    assert "faketime '2026-12-31 23:59:55'" in commands[2].command
    assert "faketime '+37h'" in commands[3].command


def test_build_commands_net_off_sets_blackhole_env_vars() -> None:
    commands = pert.build_commands("net_off", "tests/test_api.py::test_retry", k=1, per_test_timeout_s=30)
    assert commands[0].env_vars == {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}


def test_build_commands_seed_varies_pythonhashseed() -> None:
    commands = pert.build_commands("seed", "tests/test_api.py::test_retry", k=2, per_test_timeout_s=30)
    assert "PYTHONHASHSEED=0" in commands[0].command
    assert "PYTHONHASHSEED=1" in commands[1].command
    assert "--random-order-seed=0" in commands[0].command


def test_build_commands_unknown_name_raises() -> None:
    import pytest

    with pytest.raises(ValueError, match="Unknown perturbation"):
        pert.build_commands("nonexistent", "tests/test_api.py::test_x", k=1, per_test_timeout_s=30)


def test_usable_perturbations_skips_missing_features() -> None:
    requested = ["alone", "order", "cpu_stress", "time_shift", "net_off", "seed"]
    usable, skipped = pert.usable_perturbations(requested, available_features=set())
    assert set(skipped) == {"cpu_stress", "time_shift"}
    assert set(usable) == {"alone", "order", "net_off", "seed"}


def test_usable_perturbations_allows_all_when_features_present() -> None:
    requested = list(pert.PERTURBATION_NAMES)
    usable, skipped = pert.usable_perturbations(requested, available_features={"faketime", "stress-ng"})
    assert skipped == []
    assert set(usable) == set(requested)


def test_usable_perturbations_drops_unknown_names() -> None:
    usable, skipped = pert.usable_perturbations(["alone", "bogus"], available_features=set())
    assert usable == ["alone"]
    assert skipped == []
