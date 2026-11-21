"""ONTOS: scoped, read-only metric exports for existing finite research reports.

No status promotion, metrology, user labels, host resources, or executable code.
Unknown values stay UNKNOWN (null in JSONL; absent in Prometheus gauges).
The writer performs serialized off-loop stream I/O; it is NOT CPU parallelism.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import math
import re
from typing import Any, Mapping, TextIO

_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z", re.ASCII)
_MAX = 10**15
_METRIC_HELP = {
    'omega_ontos_substrate_core_energy_j': 'Operator-scenario core energy in joules.',
    'omega_ontos_substrate_wall_energy_j': 'Operator-scenario wall energy in joules.',
    'omega_ontos_episode_wall_energy_j': 'Caller-reported episode wall energy in joules.',
    'omega_ontos_landauer_lower_bound_j': 'Conditional Landauer lower bound, not observed dissipation.',
    'omega_ontos_work_compute_units': 'Modeled work units; not measured hardware FLOPs.',
    'omega_ontos_work_io_bytes': 'Modeled read/write bytes, not device traffic.',
    'omega_ontos_pareto_front_size': 'Robust scenario Pareto frontier size.',
    'omega_ontos_pareto_unresolved': 'Unresolved scenario candidates in Pareto comparison.',
    'omega_ontos_free_energy_error_nats': 'Caller-reported finite free energy error in nats.',
    'omega_ontos_generation': 'Caller-reported finite generation index.',
}
_COUNT_NAMES = frozenset({
    'omega_ontos_work_compute_units', 'omega_ontos_work_io_bytes',
    'omega_ontos_pareto_front_size', 'omega_ontos_pareto_unresolved',
    'omega_ontos_generation',
})


def _number(value: object, *, integer: bool = False) -> bool:
    if integer:
        return type(value) is int and 0 <= value <= _MAX
    return type(value) in (int, float) and 0 <= value <= _MAX and math.isfinite(value)


def _require_report(report: object) -> Mapping[str, Any]:
    if not isinstance(report, dict) or len(report) > 64:
        raise ValueError('expected bounded report dict')
    return report


def _metric(record: Mapping[str, Any], key: str, *, integer: bool = False) -> int | float | None:
    result = record.get(key)
    if result is not None and not _number(result, integer=integer):
        raise ValueError(f'invalid reported metric {key}')
    return result


@dataclass(frozen=True, slots=True)
class TelemetrySnapshot:
    """Fixed schema: no arbitrary labels or payloads may leave the process."""
    run_id: str
    sequence: int
    metrics: tuple[tuple[str, int | float | None], ...]
    physical_measurement_verified: bool = False
    release_authorized: bool = False

    def __post_init__(self) -> None:
        if (type(self.run_id) is not str or _RUN.fullmatch(self.run_id) is None
            or type(self.sequence) is not int or not 0 <= self.sequence <= _MAX
            or type(self.metrics) is not tuple or len(self.metrics) != len(_METRIC_HELP)
            or self.physical_measurement_verified is not False
            or self.release_authorized is not False):
            raise ValueError('invalid telemetry envelope')
        if tuple(k for k, _ in self.metrics) != tuple(_METRIC_HELP):
            raise ValueError('metric schema must be fixed and ordered')
        for key, value in self.metrics:
            if value is not None and not _number(value, integer=key in _COUNT_NAMES):
                raise ValueError('invalid metric sample')


def make_snapshot(run_id: str, sequence: int, *,
                  substrate_report: dict | None = None,
                  episode_report: dict | None = None,
                  work_report: dict | None = None,
                  pareto_report: dict | None = None,
                  free_energy_error_nats: float | None = None,
                  generation: int | None = None) -> TelemetrySnapshot:
    """Project only allowlisted signals from existing ONTOS reports.

    Caller supplies output of real .report() / compare(...), not full artifacts.
    The exporter is intentionally incapable of granting release or claiming a
    device-calibrated reading. Validation does not authenticate the caller.
    """
    values: dict[str, int | float | None] = dict.fromkeys(_METRIC_HELP)
    if substrate_report is not None:
        r = _require_report(substrate_report)
        if r.get('source') != 'OPERATOR_ASSUMED_SCENARIO' or r.get('physical_measurement_verified') is not False:
            raise ValueError('not an unverified v69 scenario')
        values['omega_ontos_substrate_core_energy_j'] = _metric(r, 'energy_core_j')
        values['omega_ontos_substrate_wall_energy_j'] = _metric(r, 'energy_wall_j')
        a, b = values['omega_ontos_substrate_core_energy_j'], values['omega_ontos_substrate_wall_energy_j']
        if a is not None and b is not None and a > b:
            raise ValueError('core energy exceeds wall energy')
    if episode_report is not None:
        r = _require_report(episode_report)
        if r.get('physical_measurement_verified') is not False:
            raise ValueError('episode physical verification not supported')
        values['omega_ontos_episode_wall_energy_j'] = _metric(r, 'wall_energy_j')
        values['omega_ontos_landauer_lower_bound_j'] = _metric(r, 'landauer_lower_bound_j')
    if work_report is not None:
        r = _require_report(work_report)
        if (r.get('physical_joules') != 'UNKNOWN' or
            r.get('verification') not in ('UNKNOWN_ACTUAL_WORK', 'PENDING_RESERVATIONS', 'CALLER_REPORTED_ONLY')):
            raise ValueError('not a bounded v53 estimate')
        values['omega_ontos_work_compute_units'] = _metric(r, 'used_compute_units', integer=True)
        values['omega_ontos_work_io_bytes'] = _metric(r, 'used_io_bytes', integer=True)
    if pareto_report is not None:
        r = _require_report(pareto_report)
        if (r.get('schema') != 'omega-ontos-v71-scenario-pareto-v1'
                or r.get('physical_measurement_verified') is not False
                or r.get('release_authorized') is not False):
            raise ValueError('not a non-authorizing v71 report')
        frontier, unresolved = r.get('robust_frontier'), r.get('unresolved')
        if (type(frontier) is not list or type(unresolved) is not list
                or len(frontier) > 64 or len(unresolved) > 64
                or any(type(v) is not str or _RUN.fullmatch(v) is None for v in frontier + unresolved)):
            raise ValueError('invalid bounded Pareto identifiers')
        values['omega_ontos_pareto_front_size'] = len(frontier)
        values['omega_ontos_pareto_unresolved'] = len(unresolved)
    if free_energy_error_nats is not None:
        if not _number(free_energy_error_nats):
            raise ValueError('invalid free energy error in nats')
        values['omega_ontos_free_energy_error_nats'] = free_energy_error_nats
    if generation is not None:
        if not _number(generation, integer=True):
            raise ValueError('invalid generation count')
        values['omega_ontos_generation'] = generation
    return TelemetrySnapshot(run_id, sequence, tuple(values.items()))


def render_jsonl(snapshot: TelemetrySnapshot) -> str:
    if type(snapshot) is not TelemetrySnapshot:
        raise ValueError('typed snapshot required')
    snapshot.__post_init__()
    values = dict(snapshot.metrics)
    event = {
        'schema': 'omega-ontos-telemetry-v1',
        'run_id': snapshot.run_id,
        'sequence': snapshot.sequence,
        'metrics': values,
        'known': {k: v is not None for k, v in snapshot.metrics},
        'origin': 'CALLER_REPORTED_MODEL_OR_SCENARIO',
        'physical_measurement_verified': False,
        'release_authorized': False,
    }
    return json.dumps(event, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False) + '\n'


def render_prometheus(snapshot: TelemetrySnapshot) -> str:
    """Prometheus text exposition without attacker-controlled labels/cardinality.

    One snapshot per scrape; present UNKNOWN as ``_known 0`` and omit gauge.
    Do not concatenate multiple snapshots into one scrape (duplicate families).
    """
    if type(snapshot) is not TelemetrySnapshot:
        raise ValueError('typed snapshot required')
    snapshot.__post_init__()
    lines: list[str] = []
    for name, value in snapshot.metrics:
        lines.extend((f'# HELP {name} {_METRIC_HELP[name]}', f'# TYPE {name} gauge'))
        if value is not None:
            lines.append(f'{name} {value}')
        lines.extend((f'# HELP {name}_known 1 when value is supplied, 0 when unknown.',
                      f'# TYPE {name}_known gauge', f'{name}_known {int(value is not None)}'))
    lines.extend(('# HELP omega_ontos_physical_measurement_verified Fixed 0: model telemetry only.',
                  '# TYPE omega_ontos_physical_measurement_verified gauge',
                  'omega_ontos_physical_measurement_verified 0'))
    return '\n'.join(lines) + '\n'


class AsyncJsonlExporter:
    """Serialize JSONL writes off the asyncio loop, with an explicit error latch.

    Stream is owned by the caller, and must already point to a trusted destination.
    A partially written line after storage failure requires operator repair:
    retries are forbidden on this poisoned sink. No fsync/transaction guarantee.
    """
    def __init__(self, stream: TextIO):
        if stream is None or not callable(getattr(stream, 'write', None)):
            raise ValueError('writable text stream required')
        self._stream = stream
        self._lock = asyncio.Lock()
        self._failed: BaseException | None = None
        self._last_sequence: int = -1

    def _write(self, line: str) -> None:
        count = self._stream.write(line)
        if count != len(line):
            raise OSError('partial JSONL telemetry write')
        flush = getattr(self._stream, 'flush', None)
        if callable(flush):
            flush()

    async def emit(self, snapshot: TelemetrySnapshot) -> None:
        line = render_jsonl(snapshot)
        async with self._lock:
            if self._failed is not None:
                raise OSError('telemetry stream previously failed; reopen and repair') from self._failed
            if snapshot.sequence <= self._last_sequence:
                raise ValueError('nonmonotonic telemetry sequence')
            try:
                await asyncio.to_thread(self._write, line)
            except BaseException as exc:
                self._failed = exc
                raise
            self._last_sequence = snapshot.sequence

    async def flush(self) -> None:
        async with self._lock:
            if self._failed is not None:
                raise OSError('telemetry stream previously failed') from self._failed
            flush = getattr(self._stream, 'flush', None)
            if callable(flush):
                await asyncio.to_thread(flush)
