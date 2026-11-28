"""Finite receding-horizon robust controller, executed only on the APEX model.

Replays the committed prefix for every scenario; an infeasible recommendation
cannot bypass the shield. This is not a device driver or a learned RL policy.
"""
from dataclasses import dataclass
from itertools import product
from .apex_planner import Event, Plan, Release, Scenario, evaluate, _work
from .apex_twin import Parameters, Snapshot, Twin, integer


@dataclass(frozen=True, slots=True)
class Run:
    status: str
    events: tuple[Event, ...]
    final: Snapshot
    replans: int
    evaluations: int
    advice_rejections: int


def run_mpc(work, scenarios, actual, delays, deadline_ms, *, horizon=3, advisory=None) -> Run:
    _work(work)
    if (len(work) > 16 or type(scenarios) is not tuple or not 1 <= len(scenarios) <= 8
            or type(actual) is not Scenario or actual not in scenarios
            or type(delays) is not tuple or not 1 <= len(delays) <= 4
            or any(not integer(d, 0, 1000000) for d in delays)
            or len(set(delays)) != len(delays)
            or not integer(deadline_ms, 0, 1000000) or not integer(horizon, 1, 3)):
        raise ValueError('MPC budget or scenario')
    for s in scenarios:
        if (type(s) is not Scenario or type(s.parameters) is not Parameters
                or not integer(s.parameters.max_tracked_rows, 1, 256)):
            raise ValueError('MPC scenario row budget')
        Twin(s.limits, s.parameters)
    if advisory is not None and (type(advisory) is not tuple or len(advisory) != len(work)
                                 or any(type(d) is not int or d not in delays for d in advisory)):
        raise ValueError('advisory schedule')
    twin = Twin(actual.limits, actual.parameters)
    committed = ()
    replans = evaluations = rejected = 0
    while len(committed) < len(work):
        i = len(committed)
        n = min(horizon, len(work)-i)
        replans += 1

        def predict(sequence):
            nonlocal evaluations
            now = committed[-1].at_ms if committed else 0
            events = list(committed)
            for j, delay in enumerate(sequence):
                now += delay
                if now > deadline_ms:
                    return None
                events.append(Event(now, work[i+j]))
            events = tuple(events)
            plan = Plan('mpc', events)
            results = []
            for s in scenarios:
                evaluations += 1
                r = evaluate(work[:i+n], plan, s, deadline_ms)
                if r is None:
                    return None
                results.append(r)
            return (now, max(r.peak_mc for r in results), sequence, events[i])

        best = predict(advisory[i:i+n]) if advisory is not None else None
        if advisory is not None and best is None:
            rejected += 1
        if best is None:
            feasible = (p for seq in product(sorted(delays), repeat=n)
                        if (p := predict(seq)) is not None)
            best = min(feasible, default=None)
        if best is None:
            return Run('STOP', committed, twin.snapshot, replans, evaluations, rejected)
        e = best[-1]
        revision = twin.snapshot.revision
        decision = (twin.advance(revision, e.at_ms, release_bytes=e.action.size_bytes)
                    if type(e.action) is Release else twin.step(revision, e.at_ms, e.action))
        if not decision.allowed:
            return Run('STOP', committed, twin.snapshot, replans, evaluations, rejected)
        committed += (e,)
    return Run('COMPLETE', committed, twin.snapshot, replans, evaluations, rejected)
