"""Bounded robust schedule search and offline empirical advice on real Twin.

Not CQL/MOPO or a physical controller. A missing feasible plan means STOP.
"""
from dataclasses import dataclass, fields
from hashlib import sha256
import json
from .apex_shield import Limits, HTP, FeRAM, ReRAM, MTJ
from .apex_twin import Parameters, Snapshot, Twin, integer


@dataclass(frozen=True, slots=True)
class Release:
    size_bytes: int


Action = HTP | FeRAM | ReRAM | MTJ | Release


@dataclass(frozen=True, slots=True)
class Scenario:
    limits: Limits
    parameters: Parameters


@dataclass(frozen=True, slots=True)
class Event:
    at_ms: int
    action: Action


@dataclass(frozen=True, slots=True)
class Plan:
    name: str
    events: tuple[Event, ...]


@dataclass(frozen=True, slots=True)
class Result:
    finish_ms: int
    peak_mc: int
    final: Snapshot


@dataclass(frozen=True, slots=True)
class Choice:
    plan: Plan
    worst_finish_ms: int
    worst_peak_mc: int


@dataclass(frozen=True, slots=True)
class Table:
    workload: str
    entries: tuple[tuple[str, int], ...]


def _wire(action):
    if type(action) not in (HTP, FeRAM, ReRAM, MTJ, Release):
        raise ValueError('unknown action')
    values = [getattr(action, f.name) for f in fields(action)]
    if any(type(v) not in (str, int) for v in values):
        raise ValueError('invalid action values')
    return [type(action).__name__, values]


def _digest(value):
    return sha256(json.dumps(value, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def _work(work):
    if type(work) is not tuple or not 1 <= len(work) <= 64:
        raise ValueError('workload bound')
    return [_wire(a) for a in work]


def _plan(plan):
    if (type(plan) is not Plan or type(plan.name) is not str or not 1 <= len(plan.name) <= 64
            or type(plan.events) is not tuple or not 1 <= len(plan.events) <= 64):
        raise ValueError('plan bound')
    prev = 0
    rows = []
    for e in plan.events:
        if type(e) is not Event or not integer(e.at_ms, prev, 1000000):
            raise ValueError('event time')
        rows.append([e.at_ms, _wire(e.action)])
        prev = e.at_ms
    return [plan.name, rows]


def evaluate(work, plan, scenario, deadline_ms) -> Result | None:
    try:
        expected, wire = _work(work), _plan(plan)
        if (not integer(deadline_ms, 0, 1000000) or type(scenario) is not Scenario
                or [a for _, a in wire[1]] != expected or plan.events[-1].at_ms > deadline_ms):
            return None
        twin = Twin(scenario.limits, scenario.parameters)
        peak = twin.snapshot.temp_mc
        for event in plan.events:
            rev = twin.snapshot.revision
            a = event.action
            decision = (twin.advance(rev, event.at_ms, release_bytes=a.size_bytes)
                        if type(a) is Release else twin.step(rev, event.at_ms, a))
            if not decision.allowed:
                return None
            peak = max(peak, twin.snapshot.temp_mc)
        return Result(twin.snapshot.now_ms, peak, twin.snapshot)
    except (TypeError, ValueError):
        return None


def _choices(work, plans, scenarios, deadline_ms):
    _work(work)
    if (type(plans) is not tuple or not 1 <= len(plans) <= 32
            or type(scenarios) is not tuple or not 1 <= len(scenarios) <= 16
            or not integer(deadline_ms, 0, 1000000)):
        raise ValueError('search budget')
    names = set()
    for plan in plans:
        _plan(plan)
        if plan.name in names:
            raise ValueError('duplicate plan name')
        names.add(plan.name)
        results = [evaluate(work, plan, s, deadline_ms) for s in scenarios]
        if all(r is not None for r in results):
            yield Choice(plan, max(r.finish_ms for r in results), max(r.peak_mc for r in results))


def choose(work, plans, scenarios, deadline_ms) -> Choice | None:
    """Minimize worst modeled completion time, then worst peak temperature."""
    return min(_choices(work, plans, scenarios, deadline_ms),
               key=lambda c: (c.worst_finish_ms, c.worst_peak_mc, c.plan.name), default=None)


def train(work, plans, scenarios, deadline_ms) -> Table:
    """Offline conservative empirical table: only unanimously feasible plans."""
    entries = tuple(sorted((_digest(_plan(c.plan)), c.worst_finish_ms)
                           for c in _choices(work, plans, scenarios, deadline_ms)))
    return Table(_digest(_work(work)), entries)


def recommend(work, plans, scenarios, deadline_ms, table) -> Choice | None:
    """Offline ranking cannot override fresh robust replay or admit unknown work."""
    if type(table) is not Table or table.workload != _digest(_work(work)):
        return None
    if type(table.entries) is not tuple or len(table.entries) > 32:
        return None
    scores = {}
    for row in table.entries:
        if (type(row) is not tuple or len(row) != 2 or type(row[0]) is not str
                or len(row[0]) != 64 or any(c not in '0123456789abcdef' for c in row[0])
                or row[0] in scores or not integer(row[1], 0, 1000000)):
            return None
        scores[row[0]] = row[1]
    candidates = ((max(c.worst_finish_ms, scores[k]), c.worst_peak_mc, c.plan.name, c)
                  for c in _choices(work, plans, scenarios, deadline_ms)
                  if (k := _digest(_plan(c.plan))) in scores)
    best = min(candidates, default=None)
    return best[-1] if best is not None else None
