"""Stage-3 paired latency regression gate for the restricted scheduler AST.

Timing is experimental evidence, not a deterministic fitness score. Baseline
source comes from the coordinator's accepted archive, never from a candidate or
remote worker. No arbitrary Python execution or caller-provided timing values.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import threading
import time

ROUNDS = 3
PASSES = 2
MAX_ATTEMPTS = 1024
_LOCK = threading.Lock()
_METRICS = ('p50_ns', 'p95_ns', 'p99_ns')


def _finite(v):
    return type(v) in (int, float) and math.isfinite(v)


@dataclass(frozen=True)
class Policy:
    threshold: float = .05
    min_correctness_gain: float = .02
    gain_per_slowdown: float = .4
    hard_cap: float = .25

    def __post_init__(self):
        if not all(_finite(x) for x in asdict(self).values()) or not (
            0 <= self.threshold < self.hard_cap <= 1 and
            0 < self.min_correctness_gain <= 1 and
            0 < self.gain_per_slowdown <= 1
        ):
            raise ValueError('invalid performance policy')


@dataclass(frozen=True)
class Latency:
    p50_ns: float
    p95_ns: float
    p99_ns: float
    samples: int

    def __post_init__(self):
        if not all(_finite(x) for x in (self.p50_ns,self.p95_ns,self.p99_ns)) or not (
            0 < self.p50_ns <= self.p95_ns <= self.p99_ns and
            type(self.samples) is int and 100 <= self.samples <= 4096
        ):
            raise ValueError('invalid latency profile')

    @property
    def latency_ms(self):
        return self.p50_ns / 1e6


@dataclass(frozen=True)
class Comparison:
    role: str
    baseline_id: str
    baseline_quality: float
    candidate_quality: float
    baseline: tuple[Latency, ...]
    candidate: tuple[Latency, ...]

    def __post_init__(self):
        if self.role not in ('parent','cell','champion') or not isinstance(self.baseline_id,str) or not self.baseline_id:
            raise ValueError('invalid baseline identity')
        if not all(_finite(x) and 0<=x<=1 for x in (self.baseline_quality,self.candidate_quality)):
            raise ValueError('invalid correctness')
        if any(type(p) is not tuple or len(p)!=ROUNDS or any(not isinstance(x,Latency) for x in p) for p in (self.baseline,self.candidate)):
            raise ValueError('invalid paired rounds')
        if len({x.samples for x in (*self.candidate,*self.baseline)})!=1:
            raise ValueError('incompatible sample counts')


@dataclass(frozen=True)
class Decision:
    accepted: bool
    reason: str
    relative_slowdown: dict[str, float]
    correctness_gain: float
    required_gain: float


def decide(c: Comparison, policy: Policy) -> Decision:
    if not isinstance(c,Comparison) or not isinstance(policy,Policy):
        raise ValueError('invalid performance comparison')
    # Median of three paired ratios: one transient outlier cannot decide a gate.
    ratios={key:statistics.median(getattr(b,key)/getattr(a,key)-1
                                  for a,b in zip(c.baseline,c.candidate)) for key in _METRICS}
    if not all(math.isfinite(v) for v in ratios.values()):
        raise ValueError('nonfinite latency ratio')
    slowdown=max(ratios.values())
    gain=c.candidate_quality-c.baseline_quality
    required=max(policy.min_correctness_gain,policy.gain_per_slowdown*max(0.,slowdown))
    if slowdown>policy.hard_cap+1e-12:
        return Decision(False,'hard latency cap',ratios,gain,required)
    if slowdown<=policy.threshold+1e-12:
        return Decision(True,'within tolerance',ratios,gain,0.)
    if gain+1e-12>=required:
        return Decision(True,'correctness tradeoff',ratios,gain,required)
    return Decision(False,'performance regression',ratios,gain,required)


def _profile(samples):
    s=sorted(samples)
    def nearest(q): return s[math.ceil(q*len(s))-1]
    return Latency(float(statistics.median(s)),float(nearest(.95)),float(nearest(.99)),len(s))


def measure(baseline: str, candidate: str, grid):
    """Warm up both interpreters; 3 x 192 per-call wall-clock readings each.

    Paired ordering alternates AB/BA, with identical fixed inputs. Oracle,
    parsing, archive and network latency are deliberately outside timed calls.
    """
    from .engine import Expression
    if type(grid) is not tuple or len(grid)!=96:
        raise ValueError('unexpected benchmark grid')
    a,b=Expression(baseline),Expression(candidate)
    profiles=[[],[]]
    with _LOCK:
        for x,y in grid:
            a.evaluate(x,y); b.evaluate(x,y)
        for r in range(ROUNDS):
            samples=[[],[]]
            for i,(x,y) in enumerate(grid*PASSES):
                order=(0,1) if (i+r)%2==0 else (1,0)
                for j in order:
                    fn=(a,b)[j].evaluate
                    t=time.perf_counter_ns(); fn(x,y); elapsed=time.perf_counter_ns()-t
                    if elapsed<=0: raise ValueError('clock resolution inadequate')
                    samples[j].append(elapsed)
            for j in (0,1): profiles[j].append(_profile(samples[j]))
    return tuple(profiles[0]),tuple(profiles[1])


def context(grid, policy):
    """Bind workload, timing policy and interpreter/host description to history."""
    cpu=platform.processor()
    if not cpu:
        try:
            with open('/proc/cpuinfo',encoding='utf-8') as f:
                cpu=next((l.split(':',1)[1].strip() for l in f if l.startswith('model name')), '')
        except OSError: pass
    return {'schema':'omega-stage3-latency-v1','policy':asdict(policy),
            'workload_sha256':hashlib.sha256(json.dumps(grid,separators=(',',':'),allow_nan=False).encode()).hexdigest(),
            'implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'engine_sha256':hashlib.sha256(Path(__file__).with_name('engine.py').read_bytes()).hexdigest(),
            'rounds':ROUNDS,'passes':PASSES,'python':list(sys.version_info[:3]),
            'platform':platform.system(),'machine':platform.machine(),'cpu':cpu,
            'affinity':sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None,
            'clock_resolution_ns':time.get_clock_info('perf_counter').resolution*1e9}


def check_candidate(ident, code, quality, proxy, parent, archive, grid, policy):
    """Parent + current best occupied cell (or global champion if empty).

    Both references are historical accepted artifacts re-profiled now; stored
    measurements are evidence and never compared across different hosts/runs.
    """
    from .engine import Expression, score
    cell=archive.cells[parent.island].get(Expression(code).descriptor,[])
    role,elite=('cell',max(cell,key=lambda a:(score(a.metrics),a.id))) if cell else ('champion',archive.best())
    references=[('parent',parent)]
    if elite.code!=parent.code: references.append((role,elite))
    record={'candidate_id':ident,'candidate_sha256':hashlib.sha256(code.encode()).hexdigest(),
            'correctness':quality,'performance_proxy':proxy,'comparisons':[], 'accepted':False}
    for role,ref in references:
        try:
            a,b=measure(ref.code,code,grid)
            c=Comparison(role,ref.id,ref.metrics[0],quality,a,b)
            decision=decide(c,policy)
            row={**asdict(c),'baseline_sha256':hashlib.sha256(ref.code.encode()).hexdigest(),
                 'parent_performance':ref.metrics[1],
                 'parent_latency_ms':statistics.median(x.latency_ms for x in a),
                 'candidate_latency_ms':statistics.median(x.latency_ms for x in b),
                 'decision':asdict(decision)}
            record['comparisons'].append(row)
        except (ArithmeticError,ValueError,RuntimeError,OSError) as exc:
            record['error']='profiling failed: '+type(exc).__name__
            return json.loads(json.dumps(record,allow_nan=False))
    record['accepted']=all(c['decision']['accepted'] for c in record['comparisons'])
    # Canonical JSON converts profile tuples for exact checkpoint recovery.
    return json.loads(json.dumps(record,allow_nan=False))
