"""Opt-in Green Computing ledger for authenticated MAP-Elites cluster commits.

The clocks measure one worker thread, not the full node. Watt ranges and carbon
intensity are OPERATOR SCENARIOS; energy/carbon outputs are estimates, not
power-meter readings. No admission, checkpoint, or resource-policy authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
import time
from typing import Callable, Any

_NS = 1_000_000_000
_MAX_NS = 86_400 * _NS
_MAX_COUNT = 10**12
_SOURCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,63}\Z", re.ASCII)


def _finite(value: object, lower: float, upper: float) -> bool:
    return type(value) in (int, float) and lower <= value <= upper and math.isfinite(value)


def _count(value: object) -> bool:
    return type(value) is int and 0 <= value <= _MAX_COUNT


@dataclass(frozen=True, slots=True)
class WorkerPowerScenario:
    """Operator-assumed watts per active worker-thread CPU-second.

    Actual host energy and attribution to GPU, DRAM, idle, interconnect and
    cooling remain UNKNOWN. Power source is a safe reference identifier only.
    """

    low_w: float
    central_w: float
    high_w: float
    intensity_g_per_kwh: float
    power_source: str
    intensity_source: str

    def __post_init__(self) -> None:
        if not (all(_finite(v, 0, 10_000) for v in (self.low_w, self.central_w, self.high_w))
                and self.low_w <= self.central_w <= self.high_w
                and self.high_w > 0
                and _finite(self.intensity_g_per_kwh, 0, 10_000)):
            raise ValueError('worker CPU power and grid-intensity bounds')
        if any(type(x) is not str or _SOURCE.fullmatch(x) is None
               for x in (self.power_source, self.intensity_source)):
            raise ValueError('invalid calibration provenance identifier')


@dataclass(frozen=True, slots=True)
class Reading:
    """Untrusted worker report of perf_counter_ns and thread_time_ns deltas."""
    wall_ns: int
    cpu_ns: int | None

    def __post_init__(self) -> None:
        if type(self.wall_ns) is not int or not 0 < self.wall_ns <= _MAX_NS:
            raise ValueError('invalid worker wall-clock delta')
        if self.cpu_ns is not None and (type(self.cpu_ns) is not int or
                                        not 0 <= self.cpu_ns <= 1024 * self.wall_ns):
            raise ValueError('invalid worker thread CPU delta')


def make_reading(wall_ns: int, cpu_ns: int | None) -> Reading:
    return Reading(wall_ns, cpu_ns)


def sample_worker_step(fn: Callable[..., dict[str, Any]], *args: Any) -> dict[str, Any]:
    """Instrument the ACTUAL synchronous actor call without touching its state.

    A failing worker propagates the error. Missing per-thread clock becomes
    UNKNOWN, never an invented CPU measurement or a zero-energy receipt.
    """
    start_wall = time.perf_counter_ns()
    clock = getattr(time, 'thread_time_ns', None)
    start_cpu = clock() if callable(clock) else None
    result = fn(*args)
    delta_wall = time.perf_counter_ns() - start_wall
    delta_cpu = clock() - start_cpu if start_cpu is not None else None
    try:
        reading = Reading(delta_wall, delta_cpu)
        signal = {'wall_ns': reading.wall_ns, 'cpu_ns': reading.cpu_ns}
    except ValueError:
        signal = {'wall_ns': None, 'cpu_ns': None}
    if type(result) is not dict or 'state' not in result or 'green_reading' in result:
        raise ValueError('invalid actor response for observation')
    return {**result, 'green_reading': signal}


class GreenLedger:
    """In-memory, post-CAS, no-authority per-island resource audit.

    Only a successfully committed transition may be recorded. Ledger snapshots
    are *not* part of the signed checkpoint. On resume, previous revisions are
    explicitly flagged as UNKNOWN. A failure must never promote/reject a code
    candidate or authorize cloud provisioning.
    """

    def __init__(self, profile: WorkerPowerScenario, *, islands: int,
                 initial_revisions: tuple[int, ...]):
        if type(profile) is not WorkerPowerScenario:
            raise ValueError('typed worker scenario required')
        profile.__post_init__()
        if (type(islands) is not int or not 1 <= islands <= 512
                or type(initial_revisions) is not tuple or len(initial_revisions) != islands
                or any(not _count(rev) for rev in initial_revisions)):
            raise ValueError('invalid island count or checkpoint revisions')
        self.profile = profile
        self.islands = islands
        self.initial_revisions = initial_revisions
        self._next_revision = list(initial_revisions)
        self._rows: list[list[dict[str, int | None]]] = [[] for _ in range(islands)]

    def commit(self, island: int, revision: int, reading: Reading | None, *, attempts: int,
               rejections: int, profiled: int, perf_rejected: int) -> None:
        if (type(island) is not int or not 0 <= island < self.islands
                or type(revision) is not int or revision != self._next_revision[island] + 1):
            raise ValueError('noncontiguous or duplicate cluster revision')
        if reading is not None and type(reading) is not Reading:
            raise ValueError('typed reading or missing reading required')
        if reading is not None:
            reading.__post_init__()
        if (any(not _count(n) for n in (attempts, rejections, profiled, perf_rejected))
                or rejections > attempts or profiled > attempts
                or perf_rejected > profiled or perf_rejected > rejections):
            raise ValueError('invalid committed transition counters')
        if len(self._rows[island]) >= 101:
            raise ValueError('bounded committed steps exceeded')
        new = {'revision':revision, 'wall_ns':None if reading is None else reading.wall_ns,
               'cpu_ns':None if reading is None else reading.cpu_ns,
               'attempts':attempts, 'rejections':rejections,
               'profiled':profiled, 'perf_rejected':perf_rejected}
        self._rows[island].append(new)
        self._next_revision[island] = revision

    def _summary(self, records: list[dict[str, int | None]]) -> dict:
        count = len(records)
        complete = all(x['cpu_ns'] is not None for x in records)
        known_cpu = sum(int(x['cpu_ns']) for x in records if x['cpu_ns'] is not None)
        energy = (self._energy(known_cpu) if complete else None)
        return {
            'new_commits': count,
            'measured_commits': sum(x['cpu_ns'] is not None for x in records),
            'unknown_commits': sum(x['cpu_ns'] is None for x in records),
            'worker_wall_s': (sum(int(x['wall_ns']) for x in records) / _NS
                              if all(x['wall_ns'] is not None for x in records) else None),
            'worker_cpu_s': known_cpu / _NS if complete else None,
            'energy_cpu_wh': energy,
            'carbon_cpu_g': self._carbon(energy) if energy is not None else None,
            'measured_cpu_energy_partial_wh': self._energy(known_cpu),
            'attempts': sum(int(x['attempts']) for x in records),
            'rejections': sum(int(x['rejections']) for x in records),
            'performance_profiled': sum(int(x['profiled']) for x in records),
            'performance_regression_rejections': sum(int(x['perf_rejected']) for x in records),
        }

    def _energy(self, cpu_ns: int) -> dict[str, float]:
        hours = (cpu_ns / _NS) / 3600
        return {k: hours * getattr(self.profile, k + '_w') for k in ('low','central','high')}

    def _carbon(self, energy: dict[str, float]) -> dict[str, float]:
        return {key: val * self.profile.intensity_g_per_kwh / 1000
                for key, val in energy.items()}

    def report(self, *, expected_commits: int | None = None) -> dict:
        flat = [rec for island in self._rows for rec in island]
        summary = self._summary(flat)
        initial = sum(self.initial_revisions)
        observed = summary['new_commits']
        if expected_commits is not None and (not _count(expected_commits) or expected_commits < observed):
            raise ValueError('invalid expected commit count')
        missing = (expected_commits - observed) if expected_commits is not None else 0
        if missing:
            summary['energy_cpu_wh'] = None
            summary['carbon_cpu_g'] = None
            summary['worker_cpu_s'] = None
            summary['worker_wall_s'] = None
        return {
            'schema':'omega-cluster-green-v1',
            'source':'OPERATOR_SCENARIO_THREAD_CPU',
            'energy_basis':'worker thread CPU seconds; operator watts, not node wall-plug',
            'carbon_basis':'operator grid gCO2e/kWh; location and hour not verified',
            'excluded':'idle; GPU; DRAM; network; cooling; PSU; embedded emissions; external services',
            'power_source':self.profile.power_source,
            'intensity_source':self.profile.intensity_source,
            'previous_commits_unknown':initial,
            'whole_history_complete': initial == 0 and summary['unknown_commits'] == 0 and missing == 0,
            'unobserved_commits':missing,
            **summary,
            'islands': [self._summary(rows) for rows in self._rows],
            'physical_measurement_verified':False,
            'release_authorized':False,
        }


def render_jsonl(report: dict) -> str:
    if type(report) is not dict or report.get('schema') != 'omega-cluster-green-v1':
        raise ValueError('typed cluster green report required')
    return json.dumps(report, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False) + '\n'


def render_prometheus(report: dict) -> str:
    """Aggregate fixed-cardinality gauges only. No island or arbitrary labels."""
    if type(report) is not dict or report.get('schema') != 'omega-cluster-green-v1':
        raise ValueError('typed cluster green report required')
    gauges = {
        'omega_cluster_new_commits':report['new_commits'],
        'omega_cluster_unknown_commits':report['unknown_commits'],
        'omega_cluster_worker_wall_seconds':report['worker_wall_s'],
        'omega_cluster_worker_cpu_seconds':report['worker_cpu_s'],
        'omega_cluster_attempts':report['attempts'],
        'omega_cluster_rejections':report['rejections'],
        'omega_cluster_performance_profiled':report['performance_profiled'],
        'omega_cluster_performance_regression_rejections':report['performance_regression_rejections'],
        'omega_cluster_cpu_energy_wh': (None if report['energy_cpu_wh'] is None
                                        else report['energy_cpu_wh']['central']),
        'omega_cluster_cpu_energy_low_wh': (None if report['energy_cpu_wh'] is None
                                            else report['energy_cpu_wh']['low']),
        'omega_cluster_cpu_energy_high_wh': (None if report['energy_cpu_wh'] is None
                                             else report['energy_cpu_wh']['high']),
        'omega_cluster_cpu_carbon_g': (None if report['carbon_cpu_g'] is None
                                       else report['carbon_cpu_g']['central']),
    }
    lines = []
    for key, val in gauges.items():
        lines.extend((f'# HELP {key} Bounded cluster thread-CPU scenario metric.',
                      f'# TYPE {key} gauge',
                      f'{key}_known {int(val is not None)}'))
        if val is not None:
            if type(val) not in (int, float) or not math.isfinite(val):
                raise ValueError('invalid gauge')
            lines.append(f'{key} {val}')
    return '\n'.join(lines) + '\n'
