"""ONTOS L11 v68: finite SI energy accounting, NOT hardware measurements.

Logical erasures, model operations, information and physical energy are independent
quantities. Missing measurements and missing erasure counts remain UNKNOWN.

This module performs no hardware I/O, authorizations or policy promotion.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

BOLTZMANN_J_PER_K = 1.380649e-23  # exact SI definition
_LN2 = math.log(2.0)
_MAX_COUNT = 10**15
_MAX_TEMPERATURE_K = 10**6
_MAX_ENERGY_J = 10**15


def _count(value: object) -> bool:
    return type(value) is int and 0 <= value <= _MAX_COUNT


def _nonnegative(value: object, maximum: float = _MAX_ENERGY_J) -> bool:
    return type(value) in (int, float) and 0 <= value <= maximum and math.isfinite(value)


def _temperature(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and 0 < value <= _MAX_TEMPERATURE_K


def bits_to_nats(bits: float) -> float:
    """Convert an explicit nonnegative information quantity, not compute ops."""
    if not _nonnegative(bits):
        raise ValueError('information bits must be finite and nonnegative')
    return bits * _LN2


def nats_to_bits(nats: float) -> float:
    if not _nonnegative(nats):
        raise ValueError('information nats must be finite and nonnegative')
    return nats / _LN2


def landauer_min_j(erased_bits: int, temperature_k: float) -> float:
    """k_B T ln(2) per declared irreversible bit erasure; NOT per FLOP.

    This is a thermodynamic *lower bound* conditional on the erasure claim,
    not the actual dissipation or a guaranteed device energy consumption.
    """
    if not _count(erased_bits) or not _temperature(temperature_k):
        raise ValueError('invalid erasure count or absolute temperature')
    return float(erased_bits) * BOLTZMANN_J_PER_K * temperature_k * _LN2


@dataclass(frozen=True, slots=True)
class ThermodynamicEpisode:
    """Separate operation count, logical erasure, information and energy scenario.

    The caller-provided core/wall joules are *unverified scenario inputs*.
    A calibrated measurement must be proved by an external metrology pipeline.
    """

    operations: int
    temperature_k: float
    erased_bits: int | None = None
    information_gain_bits: float = 0.0
    core_energy_j: float | None = None
    wall_energy_j: float | None = None

    def __post_init__(self) -> None:
        if not _count(self.operations) or not _temperature(self.temperature_k):
            raise ValueError('invalid operation count or temperature')
        if self.erased_bits is not None and not _count(self.erased_bits):
            raise ValueError('erased bits must be a bounded exact integer')
        if not _nonnegative(self.information_gain_bits):
            raise ValueError('information gain must be finite and nonnegative')
        if any(x is not None and not _nonnegative(x) for x in (self.core_energy_j, self.wall_energy_j)):
            raise ValueError('scenario energy must be finite and nonnegative')
        if (self.core_energy_j is not None and self.wall_energy_j is not None
                and self.core_energy_j > self.wall_energy_j):
            raise ValueError('core energy exceeds total system boundary')

    def report(self) -> dict[str, float | int | bool | None]:
        self.__post_init__()
        return {
            'operations': self.operations,
            'irreversibly_erased_bits': self.erased_bits,
            'temperature_k': self.temperature_k,
            'information_gain_bits': self.information_gain_bits,
            'information_gain_nats': bits_to_nats(self.information_gain_bits),
            'landauer_lower_bound_j': (
                None if self.erased_bits is None
                else landauer_min_j(self.erased_bits, self.temperature_k)
            ),
            'core_energy_j': self.core_energy_j,
            'wall_energy_j': self.wall_energy_j,
            'joules_per_operation': (
                self.wall_energy_j / self.operations
                if self.wall_energy_j is not None and self.operations > 0 else None
            ),
            'wall_power_w': None,  # no measured time window
            'physical_measurement_verified': False,
        }


@dataclass(frozen=True, slots=True)
class EnergyAggregate:
    """Unknown component values propagate, never silently become zero."""

    episodes: tuple[ThermodynamicEpisode, ...]

    def __post_init__(self) -> None:
        if type(self.episodes) is not tuple or len(self.episodes) > 100_000:
            raise ValueError('bounded episodes tuple required')
        if any(type(e) is not ThermodynamicEpisode for e in self.episodes):
            raise ValueError('episode type')
        for episode in self.episodes:
            episode.__post_init__()
        if sum(e.operations for e in self.episodes) > _MAX_COUNT:
            raise ValueError('aggregate operations exceed safe bounds')
        if sum(e.erased_bits or 0 for e in self.episodes) > _MAX_COUNT:
            raise ValueError('aggregate erasures exceed safe bounds')

    def report(self) -> dict[str, float | int | bool | None]:
        self.__post_init__()
        count = len(self.episodes)
        ops = sum(e.operations for e in self.episodes)
        known_erasures = sum(e.erased_bits is not None for e in self.episodes)
        known_wall = sum(e.wall_energy_j is not None for e in self.episodes)
        known_core = sum(e.core_energy_j is not None for e in self.episodes)
        erased = sum(e.erased_bits or 0 for e in self.episodes) if count and known_erasures == count else None
        landauer = (math.fsum(landauer_min_j(e.erased_bits, e.temperature_k)
                              for e in self.episodes) if erased is not None else None)
        wall = (math.fsum(e.wall_energy_j for e in self.episodes)
                if count and known_wall == count else None)
        core = (math.fsum(e.core_energy_j for e in self.episodes)
                if count and known_core == count else None)
        bits = math.fsum(e.information_gain_bits for e in self.episodes)
        if (not _nonnegative(bits) or
                any(v is not None and not _nonnegative(v)
                    for v in (landauer, wall, core))):
            raise ValueError('aggregate numeric overflow')
        return {
            'episodes': count,
            'operations': ops,
            'irreversibly_erased_bits': erased,
            'erasure_known_episodes': known_erasures,
            'information_gain_bits': bits,
            'information_gain_nats': bits_to_nats(bits),
            'landauer_lower_bound_j': landauer,
            'core_energy_j': core,
            'wall_energy_j': wall,
            'wall_energy_known_episodes': known_wall,
            'joules_per_operation': (wall / ops if wall is not None and ops > 0 else None),
            'wall_power_w': None,
            'physical_measurement_verified': False,
        }
