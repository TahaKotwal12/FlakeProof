"""The perturbation matrix used during root-cause diagnosis (docs/03-PIPELINE.md
Stage 3): six controlled experimental conditions, each run as K forks of the
same checkpoint, to find which condition triggers a given flaky failure.

`cpu_stress`/`time_shift` need `stress-ng`/`libfaketime` (installed by S1's
toolchain step); `detect_available_features` re-probes for them at diagnose
time rather than trusting that install succeeded, since the worker can
restart between stages and a degraded S1 install may be missing one.
"""

from __future__ import annotations

from dataclasses import dataclass

from flakeproof.executors.base import EnvHandle, SandboxCommand, SandboxExecutor

REPORT_PATH = "/tmp/report.xml"

PERTURBATION_NAMES = ("alone", "order", "cpu_stress", "time_shift", "net_off", "seed")

# docs/03-PIPELINE.md matrix: "pytest ... with HTTP_PROXY=http://127.0.0.1:9
# HTTPS_PROXY=http://127.0.0.1:9 NO_PROXY=" (blackhole -- nothing listens on
# 127.0.0.1:9, so any real outbound call fails fast with connection refused).
_NET_OFF_ENV = {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}

# Two clock-shift variants from the matrix table, alternated across the K forks
# to cover both a near-midnight boundary and a large forward offset.
_TIME_SHIFT_VARIANTS = ("faketime '2026-12-31 23:59:55'", "faketime '+37h'")

_CPU_STRESS_DURATION_S = 30
_FEATURE_PROBE_TIMEOUT_S = 30


@dataclass(frozen=True)
class Perturbation:
    """One controlled experimental condition applied to a sandbox fork."""

    name: str
    description: str
    requires_feature: str | None  # 'faketime' | 'stress-ng' | None (always available)


ALL_PERTURBATIONS: dict[str, Perturbation] = {
    "alone": Perturbation(
        "alone", "test run in isolation -- never fails alone but fails in the suite implicates order/shared state", None
    ),
    "order": Perturbation("order", "full suite under random ordering -- order-dependent shared state", None),
    "cpu_stress": Perturbation(
        "cpu_stress", "CPU pressure during the test -- async race / timing assumptions", "stress-ng"
    ),
    "time_shift": Perturbation("time_shift", "clock shifted near a boundary -- time/date dependence", "faketime"),
    "net_off": Perturbation("net_off", "network blackholed -- hidden external network dependency", None),
    "seed": Perturbation("seed", "hash seed + random order varied -- randomness / hash-order dependence", None),
}


def all_perturbations() -> list[Perturbation]:
    """Return the fixed set of perturbations: order shuffle, CPU stress, clock shift,
    network cut, and seed change (plus the `alone` baseline).
    """
    return list(ALL_PERTURBATIONS.values())


def _report_suffix(per_test_timeout_s: int) -> str:
    return f"-q --junitxml={REPORT_PATH} -p no:cacheprovider --timeout={per_test_timeout_s}"


def build_commands(name: str, test_id: str, *, k: int, per_test_timeout_s: int) -> list[SandboxCommand]:
    """Build the K per-fork `SandboxCommand`s for perturbation `name`, per the
    exact command mutations in docs/03-PIPELINE.md's matrix table. Every
    variant writes a JUnit report to `REPORT_PATH` so the diagnose stage can
    parse outcomes uniformly regardless of whether the fork ran the single
    target test or the full suite.
    """
    if name not in ALL_PERTURBATIONS:
        raise ValueError(f"Unknown perturbation: {name!r}")

    suffix = _report_suffix(per_test_timeout_s)

    if name == "alone":
        cmd = f'cd /app && pytest "{test_id}" {suffix}'
        return [SandboxCommand(command=cmd) for _ in range(k)]

    if name == "order":
        return [
            SandboxCommand(command=f"cd /app && pytest -p random_order --random-order-seed={i} {suffix}")
            for i in range(k)
        ]

    if name == "cpu_stress":
        cmd = f'cd /app && stress-ng --cpu 2 --timeout {_CPU_STRESS_DURATION_S}s & pytest "{test_id}" {suffix}'
        return [SandboxCommand(command=cmd) for _ in range(k)]

    if name == "time_shift":
        return [
            SandboxCommand(command=f'cd /app && {_TIME_SHIFT_VARIANTS[i % 2]} pytest "{test_id}" {suffix}')
            for i in range(k)
        ]

    if name == "net_off":
        cmd = f'cd /app && pytest "{test_id}" {suffix}'
        return [SandboxCommand(command=cmd, env_vars=dict(_NET_OFF_ENV)) for _ in range(k)]

    # seed
    return [
        SandboxCommand(command=f"cd /app && PYTHONHASHSEED={i} pytest -p random_order --random-order-seed=0 {suffix}")
        for i in range(k)
    ]


async def detect_available_features(executor: SandboxExecutor, env: EnvHandle) -> set[str]:
    """Probe once whether `faketime`/`stress-ng` are on PATH. S1 installs both,
    but a degraded install (or a worker restart mid-run against an
    externally-provisioned checkpoint) shouldn't be trusted blindly --
    perturbations needing a missing binary are skipped with a warn event
    rather than failing the whole diagnose stage.
    """
    result = await executor.run(
        env, "command -v faketime >/dev/null 2>&1 && echo faketime; command -v stress-ng >/dev/null 2>&1 && echo stress-ng",
        timeout_s=_FEATURE_PROBE_TIMEOUT_S,
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip() in ("faketime", "stress-ng")}


def usable_perturbations(requested: list[str], available_features: set[str]) -> tuple[list[str], list[str]]:
    """Split `requested` perturbation names into (usable, skipped) given which
    optional features are available. Unknown names are dropped silently
    (config validation is the API layer's job, not this one's).
    """
    usable: list[str] = []
    skipped: list[str] = []
    for name in requested:
        perturbation = ALL_PERTURBATIONS.get(name)
        if perturbation is None:
            continue
        if perturbation.requires_feature and perturbation.requires_feature not in available_features:
            skipped.append(name)
        else:
            usable.append(name)
    return usable, skipped
