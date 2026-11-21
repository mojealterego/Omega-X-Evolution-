"""ONTOS L11 v69: bounded physical-unit scenarios, including RAMXEED FeRAM.

This is NOT a calibrated power meter or a hardware controller. All substrate
powers must be supplied explicitly; UNKNOWN is never converted to zero.
Data-sheet constants describe MB85RQ8MX in its specified operating modes.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

SUBSTRATES = frozenset({
    'H100_FP8', 'RRAM_PCM', 'SOT_MRAM', 'PBIT_SMTJ',
    'SILICON_PHOTONICS', 'QPU_QLDPC',
})
MAX_COMPONENT_W = 1e8
MAX_DURATION_S = 1e9
CAPACITY_BYTES = 1_048_576
QUAD_THROUGHPUT_BYTES_S = 54_000_000  # vendor advertised bandwidth, not measured
# Specified maximum supply currents at the indicated RAMXEED device modes.
MAX_CURRENTS_A = {
    'quad_active_108mhz': 18e-3,
    'standby': 180e-6,
    'deep_power_down': 10e-6,
    'hibernation': 5e-6,
}


def _real(x: object, lo: float, hi: float) -> bool:
    return type(x) in (float, int) and lo <= x <= hi and math.isfinite(x)


@dataclass(frozen=True, slots=True)
class PowerComponents:
    """Disjoint instantaneous component powers [W], or None (UNKNOWN).

    PSU losses apply to core, memory, ADC, DAC, network and host;
    cooling and auxiliary rails are separately counted after PSU efficiency.
    """
    core_w: float | None = None
    memory_w: float | None = None
    adc_w: float | None = None
    dac_w: float | None = None
    network_w: float | None = None
    host_w: float | None = None
    cooling_w: float | None = None
    auxiliary_w: float | None = None

    def __post_init__(self) -> None:
        if any(value is not None and not _real(value, 0, MAX_COMPONENT_W)
               for value in self.as_tuple()):
            raise ValueError('power components must be finite, nonnegative or UNKNOWN')

    def as_tuple(self) -> tuple[float | None, ...]:
        return (self.core_w, self.memory_w, self.adc_w, self.dac_w,
                self.network_w, self.host_w, self.cooling_w, self.auxiliary_w)


@dataclass(frozen=True, slots=True)
class SubstrateScenario:
    """Operator-supplied full-system wall-plug power scenario [W].

    The six substrate families do not have inferred wattages. A complete,
    disjoint component vector is required for the wall-plug calculation.
    Relative uncertainty is a sensitivity assumption, NOT a statistical CI.
    """
    substrate: str
    duration_s: float
    components: PowerComponents
    psu_efficiency: float | None = None
    uncertainty_rel: float | None = None

    def __post_init__(self) -> None:
        if type(self.substrate) is not str or self.substrate not in SUBSTRATES:
            raise ValueError('unsupported substrate family')
        if not _real(self.duration_s, 0., MAX_DURATION_S):
            raise ValueError('invalid duration')
        if type(self.components) is not PowerComponents:
            raise ValueError('typed components required')
        self.components.__post_init__()
        if self.psu_efficiency is not None and not _real(self.psu_efficiency, 0.01, 1.):
            raise ValueError('PSU efficiency outside bounded physical scenario')
        if self.uncertainty_rel is not None and not _real(self.uncertainty_rel, 0., 1.):
            raise ValueError('invalid sensitivity bound')

    def report(self) -> dict:
        self.__post_init__()
        p = self.components.as_tuple()
        power_core = p[0]
        wall_power = None
        if None not in p and self.psu_efficiency is not None:
            wall_power = math.fsum((math.fsum(p[:6]) / self.psu_efficiency, *p[6:]))
        energy_wall = None if wall_power is None else wall_power * self.duration_s
        energy_core = None if power_core is None else power_core * self.duration_s
        if any(v is not None and not math.isfinite(v) for v in (wall_power, energy_wall, energy_core)):
            raise ValueError('scenario energy overflow')
        interval = None
        if energy_wall is not None and self.uncertainty_rel is not None:
            interval = (energy_wall * (1 - self.uncertainty_rel),
                        energy_wall * (1 + self.uncertainty_rel))
            if not all(math.isfinite(v) for v in interval):
                raise ValueError('scenario interval overflow')
        return {
            'substrate': self.substrate,
            'duration_s': self.duration_s,
            'power_core_w': power_core,
            'power_wall_w': wall_power,
            'energy_core_j': energy_core,
            'energy_wall_j': energy_wall,
            'uncertainty_interval_wall_j': interval,
            'uncertainty_type': 'operator_sensitivity_not_calibrated_CI',
            'source': 'OPERATOR_ASSUMED_SCENARIO',
            'physical_measurement_verified': False,
        }


@dataclass(frozen=True, slots=True)
class FeRAMSegment:
    """A dwell in one MB85RQ8MX power state.

    54 MB/s is an advertised maximum serial payload rate; SPI command/address,
    dummy cycles and host overhead are NOT modeled here. The 18 mA max value
    applies specifically to Quad I/O at 108 MHz.
    """
    mode: str
    duration_s: float
    bytes_transferred: int = 0

    def __post_init__(self) -> None:
        if type(self.mode) is not str or self.mode not in MAX_CURRENTS_A:
            raise ValueError('unsupported FeRAM mode')
        if not _real(self.duration_s, 0., MAX_DURATION_S):
            raise ValueError('invalid segment duration')
        if type(self.bytes_transferred) is not int or not 0 <= self.bytes_transferred <= CAPACITY_BYTES:
            raise ValueError('invalid transfer byte count')
        if self.mode != 'quad_active_108mhz' and self.bytes_transferred != 0:
            raise ValueError('data transfer only in active mode')
        if self.bytes_transferred > self.duration_s * QUAD_THROUGHPUT_BYTES_S:
            raise ValueError('payload exceeds documented theoretical bus rate')


@dataclass(frozen=True, slots=True)
class FeRAMSupplyScenario:
    """Chip VDD upper-current envelope, not system wall-plug energy."""
    voltage_v: float
    segments: tuple[FeRAMSegment, ...]

    def __post_init__(self) -> None:
        if not _real(self.voltage_v, 2.7, 3.6):
            raise ValueError('MB85RQ8MX supply must be 2.7..3.6 V')
        if type(self.segments) is not tuple or not 1 <= len(self.segments) <= 64:
            raise ValueError('bounded FeRAM segments required')
        if any(type(s) is not FeRAMSegment for s in self.segments):
            raise ValueError('invalid FeRAM segment')
        for segment in self.segments:
            segment.__post_init__()

    def report(self) -> dict:
        self.__post_init__()
        upper_j = math.fsum(
            self.voltage_v * MAX_CURRENTS_A[s.mode] * s.duration_s for s in self.segments
        )
        if not math.isfinite(upper_j):
            raise ValueError('supply energy overflow')
        return {
            'part': 'MB85RQ8MX',
            'capacity_bytes': CAPACITY_BYTES,
            'voltage_v': self.voltage_v,
            'duration_s': math.fsum(s.duration_s for s in self.segments),
            'bytes_transferred': sum(s.bytes_transferred for s in self.segments),
            'throughput_claim_mb_s': 54.,
            'supply_energy_upper_j': upper_j,
            'wall_energy_j': None,
            'cpu_adc_dac_psu_cooling_j': None,
            'transfer_overhead_modeled': False,
            'physical_measurement_verified': False,
            'source': 'RAMXEED_MB85RQ8MX_DATASHEET_CONDITIONAL_MAX_CURRENT',
        }
