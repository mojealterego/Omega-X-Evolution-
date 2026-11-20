"""Finite read-only temporal contract; no persistence or source authentication.

A source digest and group tag are assertions, not authenticated provenance
nor a proof that samples from two groups are statistically independent.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import re

NAME = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')
CLOCKS = (1, 6, 24)


def _id(v: object) -> bool:
    return type(v) is str and NAME.fullmatch(v) is not None


def _stamp(v: object) -> bool:
    return type(v) is int and 0 <= v < 2**63


@dataclass(frozen=True, slots=True)
class TemporalEvent:
    tenant: str
    ident: str
    group: str
    value: str
    source_sha256: str
    valid_from: int
    valid_until: int
    recorded_at: int
    clock: int

    def __post_init__(self):
        if (not all(_id(x) for x in (self.tenant, self.ident, self.group))
            or type(self.value) is not str or not 1 <= len(self.value) <= 256
            or any(ord(x) < 32 or ord(x) == 127 for x in self.value)
            or type(self.source_sha256) is not str or SHA.fullmatch(self.source_sha256) is None
            or not all(_stamp(x) for x in (self.valid_from,self.valid_until,self.recorded_at))
            or self.valid_from >= self.valid_until
            or type(self.clock) is not int or self.clock not in CLOCKS):
            raise ValueError('temporal event contract')


@dataclass(frozen=True, slots=True)
class TemporalSnapshot:
    visible: tuple[TemporalEvent, ...]
    trace_sha256: str
    provenance_authenticated: bool = False
    independence_verified: bool = False


def clock_windows(now: int, clock: int, *, horizon: int = 4) -> tuple[int, ...]:
    """Four bounded historic ticks, inclusive of latest tick <= now."""
    if not _stamp(now) or type(clock) is not int or clock not in CLOCKS or type(horizon) is not int or not 1 <= horizon <= 4:
        raise ValueError('clock or horizon')
    latest = now // clock
    return tuple(k*clock for k in range(max(0,latest-horizon+1),latest+1))


def temporal_view(events: tuple[TemporalEvent,...], *, tenant: str,
                  valid_at: int, known_at: int) -> TemporalSnapshot:
    if (type(events) is not tuple or len(events) > 256 or not _id(tenant)
        or not _stamp(valid_at) or not _stamp(known_at)
        or any(type(e) is not TemporalEvent for e in events)):
        raise ValueError('bounded temporal view')
    latest: dict[str, TemporalEvent] = {}
    for e in events:
        # A frozen dataclass can still be tampered with using object.__setattr__.
        verified=TemporalEvent(e.tenant,e.ident,e.group,e.value,e.source_sha256,
                               e.valid_from,e.valid_until,e.recorded_at,e.clock)
        if verified.tenant != tenant or verified.recorded_at > known_at:
            continue
        old = latest.get(verified.ident)
        if old is None or verified.recorded_at > old.recorded_at:
            latest[verified.ident] = verified
        elif verified.recorded_at == old.recorded_at and verified != old:
            raise ValueError('ambiguous same-transaction temporal evidence')
    visible=tuple(sorted((e for e in latest.values()
                          if e.valid_from <= valid_at < e.valid_until),
                         key=lambda e:(e.clock,e.ident)))
    if len({e.group for e in visible}) != len(visible):
        raise ValueError('independence group collision')
    canonical=json.dumps([[e.tenant,e.ident,e.group,e.value,e.source_sha256,
                           e.valid_from,e.valid_until,e.recorded_at,e.clock]
                          for e in visible],separators=(',',':'),ensure_ascii=True).encode('ascii')
    return TemporalSnapshot(visible,hashlib.sha256(canonical).hexdigest())


def temporal_consistency(events: tuple[TemporalEvent,...], *, tenant: str,
                         valid_at: int, known_at: int) -> dict:
    view=temporal_view(events,tenant=tenant,valid_at=valid_at,known_at=known_at)
    return {'selected':len(view.visible), 'trace_sha256':view.trace_sha256,
            'provenance_authenticated':False,'independence_verified':False,
            'clock_windows':{str(c):clock_windows(valid_at,c) for c in CLOCKS}}
