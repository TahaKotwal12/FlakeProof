"""The perturbation matrix used during root-cause diagnosis.

Each perturbation modifies one condition of the test run (order, CPU
pressure, clock, network, random seed) so that the diagnose stage can
identify which condition triggers a given flaky failure.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Perturbation:
    """One controlled experimental condition applied to a sandbox fork."""

    name: str
    description: str
    command_prefix: str


def all_perturbations() -> list[Perturbation]:
    """Return the fixed set of perturbations: order shuffle, CPU stress, clock shift,
    network cut, and seed change.
    """
    raise NotImplementedError
