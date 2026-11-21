"""Bounded finite hypertrace self-composition and interleaving conflict audit.

Trace events describe modeled observations and read/write sets. They are not
observations captured from a native process, nor a universal HyperLTL proof.
Overflow is UNKNOWN, never PASS. No real code execution or runtime mutation.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import comb
import re

_NAME = re.compile(r'[A-Za-z0-9_-]{1,32}\Z')
_RESOURCE = re.compile(r'(?:global|[A-Za-z0-9_-]{1,32}):[A-Za-z0-9_-]{1,32}\Z')


@dataclass(frozen=True, slots=True)
class Event:
    tenant: str
    ident: str
    low_input: str
    secret: str
    low_output: str
    reads: tuple[str, ...]
    writes: tuple[str, ...]

    def __post_init__(self) -> None:
        if (any(type(v) is not str or _NAME.fullmatch(v) is None
                for v in (self.tenant, self.ident, self.low_input,
                          self.secret, self.low_output))
                or any(type(keys) is not tuple or len(keys) > 16
                       or len(set(keys))!=len(keys)
                       for keys in (self.reads, self.writes))):
            raise ValueError('bounded trace event')
        for key in self.reads + self.writes:
            if (type(key) is not str or _RESOURCE.fullmatch(key) is None
                    or key.split(':', 1)[0] not in ('global', self.tenant)):
                raise ValueError('cross-tenant or invalid resource access')


def _validate_trace(trace: tuple[Event, ...]) -> None:
    if (type(trace) is not tuple or not 1 <= len(trace) <= 8
            or any(type(e) is not Event for e in trace)):
        raise ValueError('bounded trace required')
    for e in trace:
        e.__post_init__()
    if len({e.ident for e in trace}) != len(trace):
        raise ValueError('trace event identities must be unique')
    if len({e.tenant for e in trace}) != 1:
        raise ValueError('one tenant per trace')


def check_pairwise(traces: tuple[tuple[Event, ...], ...], *, max_pairs: int) -> dict:
    """Finite forall-pair low-output equality for a given set of observed traces."""
    if (type(traces) is not tuple or not 2 <= len(traces) <= 16
            or type(max_pairs) is not int or not 0 <= max_pairs <= 120):
        raise ValueError('trace collection/budget bounds')
    for trace in traces:
        _validate_trace(trace)
    checked = 0
    for i,j in combinations(range(len(traces)), 2):
        a,b=traces[i],traces[j]
        if len(a)!=len(b) or a[0].tenant!=b[0].tenant:
            continue
        if tuple(e.low_input for e in a)!=tuple(e.low_input for e in b):
            continue
        if tuple(e.secret for e in a)==tuple(e.secret for e in b):
            continue
        if checked == max_pairs:
            return {'status':'UNKNOWN_BOUND','compared_pairs':checked,
                    'counterexample':None,'proved_unbounded_hyperltl':False}
        checked+=1
        for t,(ea,eb) in enumerate(zip(a,b)):
            if ea.low_output!=eb.low_output:
                return {'status':'FAIL_NONINTERFERENCE','compared_pairs':checked,
                        'counterexample':(i,j,t,ea.low_output,eb.low_output),
                        'proved_unbounded_hyperltl':False}
    return {'status':'PASS_FINITE' if checked else 'UNKNOWN_NO_COMPARABLE',
            'compared_pairs':checked,'counterexample':None,
            'proved_unbounded_hyperltl':False}


def _schedules(left: int, right: int):
    """All order-preserving 0/1 strings, small bounded domain."""
    for indices in combinations(range(left+right),left):
        chosen=set(indices)
        yield tuple('a' if i in chosen else 'b' for i in range(left+right))


def _types(before: Event, after: Event):
    a_read=set(before.reads);a_write=set(before.writes)
    b_read=set(after.reads);b_write=set(after.writes)
    return tuple((kind,res) for kind,keys in (
        ('RAW',a_write & b_read), ('WAR',a_read & b_write),
        ('WAW',a_write & b_write)) for res in sorted(keys))


def check_interleavings(a: tuple[Event, ...], b: tuple[Event, ...],
                        *, max_schedules: int) -> dict:
    """Bounded schedule exploration; conflicts from modeled read/write sets."""
    _validate_trace(a);_validate_trace(b)
    if type(max_schedules) is not int or not 0 <= max_schedules <= 10_000:
        raise ValueError('schedule budget')
    schedule_count=comb(len(a)+len(b),len(a))
    base={'schedules':schedule_count,'verified_native_smt':False,
          'evidence_class':'MODELLED_READ_WRITE_SETS'}
    if schedule_count>max_schedules:
        return {**base,'status':'UNKNOWN_BOUND','conflicts':(),
                'conflict_kinds':(),'counterexample':None}
    found=set()
    counterexample=None
    for labels in _schedules(len(a),len(b)):
        ai=bi=0
        sequence=[]
        for kind in labels:
            if kind=='a':
                sequence.append(('a',a[ai]));ai+=1
            else:
                sequence.append(('b',b[bi]));bi+=1
        for i,(origin,earlier) in enumerate(sequence):
            for other,later in sequence[i+1:]:
                if origin==other:continue
                for kind,resource in _types(earlier,later):
                    found.add((kind,resource,earlier.ident,later.ident))
                    if counterexample is None:
                        counterexample={'schedule':labels,'earlier':earlier.ident,
                                        'later':later.ident,'kind':kind,'resource':resource}
    return {**base,'status':'FAIL_CONFLICT' if found else 'PASS_FINITE',
            'conflicts':tuple(sorted(found)),
            'conflict_kinds':tuple(sorted({x[0] for x in found})),
            'counterexample':counterexample}
