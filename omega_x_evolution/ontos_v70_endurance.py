"""ONTOS L11 v70: bounded endurance and torn-access simulator for RAMXEED FeRAM.

MB85RQ8MX data sheet: read/write cycles at +85C=1e14, +105C=1e13.
No temperature interpolation, hardware observation, exact read-disturb physics,
or atomic-power-fail claim. Incomplete serial writes can affect a prefix.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

CAPACITY_BYTES = 1_048_576
MAX_ACCESS_BYTES = 4_096
MAX_TRACKED_CELLS = 16_384
MAX_CYCLES = 10**14
YEAR_SECONDS = 365.25 * 24 * 60 * 60  # defined simulation convention


class EnduranceExceeded(ValueError):
    """A declared qualification or model counter is exceeded (fail-closed)."""


def _temperature(value: object) -> bool:
    return type(value) in (int, float) and -40 <= value <= 105 and math.isfinite(value)


def rated_cycle_budget(temperature_c: float) -> int | None:
    """Only the vendor's *explicit* temperature-qualification points are known.

    85C -> 1e14 and 105C -> 1e13 read/write cycles. Missing temperatures
    remain UNKNOWN; never interpolate or reinterpret qualification as measured.
    """
    if not _temperature(temperature_c):
        raise ValueError('device temperature outside source specification')
    if temperature_c == 85:
        return 10**14
    if temperature_c == 105:
        return 10**13
    return None


@dataclass(frozen=True, slots=True)
class Access:
    kind: str
    address: int
    length: int
    repetitions: int = 1

    def __post_init__(self) -> None:
        if type(self.kind) is not str or self.kind not in ('read', 'write'):
            raise ValueError('only read/write operations can be accounted')
        if (type(self.address) is not int or type(self.length) is not int or
            type(self.repetitions) is not int or
            not 0 <= self.address < CAPACITY_BYTES or
            not 1 <= self.length <= MAX_ACCESS_BYTES or
            self.address + self.length > CAPACITY_BYTES or
            not 1 <= self.repetitions <= MAX_CYCLES):
            raise ValueError('access bounds / wraparound violation')


@dataclass(frozen=True, slots=True)
class FeRAMWear:
    temperature_c: float
    counters: tuple[tuple[int, int], ...] = ()
    revision: int = 0

    def __post_init__(self) -> None:
        if not _temperature(self.temperature_c):
            raise ValueError('device temperature outside source specification')
        if type(self.revision) is not int or not 0 <= self.revision <= 1_000_000:
            raise ValueError('revision bounds')
        if type(self.counters) is not tuple or len(self.counters) > MAX_TRACKED_CELLS:
            raise ValueError('bounded counter registry required')
        limit = rated_cycle_budget(self.temperature_c)
        previous = -1
        for cell in self.counters:
            if (type(cell) is not tuple or len(cell) != 2 or
                type(cell[0]) is not int or type(cell[1]) is not int or
                not previous < cell[0] < CAPACITY_BYTES or
                not 1 <= cell[1] <= MAX_CYCLES or
                (limit is not None and cell[1] > limit)):
                raise ValueError('invalid wear registry')
            previous = cell[0]

    def count_for(self, address: int) -> int:
        self.__post_init__()
        if type(address) is not int or not 0 <= address < CAPACITY_BYTES:
            raise ValueError('invalid address')
        return dict(self.counters).get(address, 0)

    def apply(self, access: Access, *, interrupted_after_bytes: int | None = None) -> tuple['FeRAMWear', dict]:
        """Apply an access; injected interruption accounts only a byte prefix.

        No physical atomicity is implied; a prefix can be written before power
        failure. This is an endurance counter, not a device-data emulator.
        """
        self.__post_init__()
        if type(access) is not Access:
            raise ValueError('typed access required')
        access.__post_init__()
        if interrupted_after_bytes is not None:
            if (type(interrupted_after_bytes) is not int or
                not 0 <= interrupted_after_bytes <= access.length or
                access.repetitions != 1):
                raise ValueError('interruption requires one bounded serial access')
        n = access.length if interrupted_after_bytes is None else interrupted_after_bytes
        old = dict(self.counters)
        limit = rated_cycle_budget(self.temperature_c)
        for address in range(access.address, access.address + n):
            new = old.get(address, 0) + access.repetitions
            if new > MAX_CYCLES or (limit is not None and new > limit):
                raise EnduranceExceeded('modeled per-cell endurance budget exhausted')
            old[address] = new
        if len(old) > MAX_TRACKED_CELLS:
            raise ValueError('sparse wear registry capacity exceeded')
        state = FeRAMWear(self.temperature_c, tuple(sorted(old.items())), self.revision + 1)
        complete = interrupted_after_bytes is None
        return state, {
            'kind': access.kind,
            'complete': complete,
            'bytes_accounted': n,
            'torn_write_possible': access.kind == 'write' and not complete and 0 < n < access.length,
            'qualification_at_temperature_known': limit is not None,
            'hardware_write_verified': False,
        }

    def report(self) -> dict:
        self.__post_init__()
        highest = max((n for _, n in self.counters), default=0)
        qualified = rated_cycle_budget(self.temperature_c)
        return {
            'temperature_c': self.temperature_c,
            'used_cells': len(self.counters),
            'total_accounted_cell_cycles': sum(n for _, n in self.counters),
            'max_cell_cycles': highest,
            'qualified_endurance_cycles': qualified,
            'remaining_worst_cell_cycles': qualified - highest if qualified is not None else None,
            'retention_years_at_temperature': 10 if self.temperature_c == 105 else (
                95 if self.temperature_c == 55 else None),
            'physical_lifetime_verified': False,
            'revision': self.revision,
        }


def predict_hotspot(*, temperature_c: float, events_hz: float, years: float) -> dict:
    """Worst-case single-address access concentration over a specified horizon.

    An event is one modeled *read or write* to the same logical byte. Assumes
    continuous activity and perfect coverage; ignores real device failures,
    temperature variation, shared wear and retention qualification.
    """
    rated = rated_cycle_budget(temperature_c)
    if (type(events_hz) not in (float, int) or
        not 0 <= events_hz <= 1e8 or not math.isfinite(events_hz) or
        type(years) not in (float, int) or
        not 0 <= years <= 1000 or not math.isfinite(years)):
        raise ValueError('hotspot workload bounds')
    cycles = math.ceil(events_hz * years * YEAR_SECONDS)
    return {
        'temperature_c': temperature_c,
        'events_per_second': events_hz,
        'simulated_years': years,
        'projected_cycles': cycles,
        'endurance_budget_cycles': rated,
        'within_rated_cycles_model': (cycles <= rated) if rated is not None else None,
        'retention_requirement_verified': False,
        'physical_lifetime_verified': False,
        'model': 'SINGLE_BYTE_HOTSPOT_CONTINUOUS_365_25_DAYS_PER_YEAR',
    }
