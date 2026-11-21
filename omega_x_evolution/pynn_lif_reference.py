"""Small deterministic LIF stimulus fixture inspired by PyNN 0.14.0 API.

This is an independently defined analytic constant-current neuron; it is NOT
PyNN, NEURON, NEST, or a validated simulator backend. It is suitable as an
optional fixed-oracle workload for constrained neuroevolution experiments.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


def _finite(x: object, low: float, high: float, *, open_lower: bool = False) -> bool:
    return (type(x) in (int,float) and low <= x <= high and
            (not open_lower or x > low) and math.isfinite(x))


@dataclass(frozen=True,slots=True)
class DCPulse:
    start_ms: float
    stop_ms: float
    amplitude_na: float

    def __post_init__(self) -> None:
        if (not _finite(self.start_ms,0,200_000) or
            not _finite(self.stop_ms,0,200_000) or self.stop_ms<=self.start_ms or
            not _finite(self.amplitude_na,-10,10)):
            raise ValueError('invalid bounded current pulse')


@dataclass(frozen=True,slots=True)
class LIFPlan:
    dt_ms: float = 1.0
    duration_ms: float = 100.0
    current_na: float = 0.0
    tau_m_ms: float = 20.0
    resistance_mohm: float = 20.0
    v_rest_mv: float = -65.0
    v_reset_mv: float = -65.0
    v_threshold_mv: float = -50.0
    refractory_ms: float = 2.0
    pulses: tuple[DCPulse,...] = ()

    def __post_init__(self) -> None:
        if (not _finite(self.dt_ms,0,10,open_lower=True) or
            not _finite(self.duration_ms,0,200_000,open_lower=True) or
            not _finite(self.current_na,-10,10) or
            not _finite(self.tau_m_ms,0,10000,open_lower=True) or
            not _finite(self.resistance_mohm,0,1000,open_lower=True) or
            not _finite(self.v_rest_mv,-200,100) or
            not _finite(self.v_reset_mv,-200,100) or
            not _finite(self.v_threshold_mv,-200,100) or
            not self.v_reset_mv<self.v_threshold_mv or
            not self.v_rest_mv<self.v_threshold_mv or
            not _finite(self.refractory_ms,0,1000) or
            type(self.pulses) is not tuple or len(self.pulses)>32):
            raise ValueError('invalid LIF parameters')
        if (not _whole_steps(self.duration_ms,self.dt_ms) or
            self.duration_ms/self.dt_ms>20_000 or
            not _whole_steps(self.refractory_ms,self.dt_ms)):
            raise ValueError('invalid time grid or work budget')
        for p in self.pulses:
            if type(p) is not DCPulse:
                raise ValueError('invalid pulse')
            p.__post_init__()
            if (p.stop_ms>self.duration_ms or not _whole_steps(p.start_ms,self.dt_ms) or
                not _whole_steps(p.stop_ms,self.dt_ms)):
                raise ValueError('pulse not aligned with stimulus grid')


def _whole_steps(t: float, dt: float) -> bool:
    q=t/dt
    return math.isfinite(q) and abs(q-round(q))<1e-8


@dataclass(frozen=True,slots=True)
class LIFTrace:
    spikes_ms: tuple[float,...]
    final_v_mv: float
    backend: str = 'OFFLINE_LIF_ANALYTIC'
    pynn_native_verified: bool = False


def simulate_lif(plan: LIFPlan, *, segments_ms: tuple[float,...] | None = None) -> LIFTrace:
    """Exact linear sub-threshold flow per bin for piecewise-constant current.

    Spikes are detected at bin ends (grid quantized), then membrane resets.
    Time discretization is part of this oracle, not an assumed PyNN kernel.
    """
    if type(plan) is not LIFPlan:
        raise ValueError('typed LIF plan required')
    plan.__post_init__()
    steps=round(plan.duration_ms/plan.dt_ms)
    if segments_ms is None:
        counts = (steps,)
    else:
        if type(segments_ms) is not tuple or not 1<=len(segments_ms)<=128:
            raise ValueError('bounded run segments required')
        if any(not _finite(x,0,plan.duration_ms,open_lower=True) or
               not _whole_steps(x,plan.dt_ms) for x in segments_ms):
            raise ValueError('invalid run segment duration')
        counts = tuple(round(x/plan.dt_ms) for x in segments_ms)
        if sum(counts) != steps:
            raise ValueError('segments must cover entire runtime')
    dt=plan.dt_ms
    membrane=float(plan.v_rest_mv)
    refractory_until=-math.inf
    spikes=[]
    leak=math.exp(-dt/plan.tau_m_ms)
    cursor=0
    # Execute each segment with persistent state, as in PyNN run()/run_to().
    for count in counts:
        for index in range(cursor, cursor+count):
            start=index*dt
            end=(index+1)*dt
            if start<refractory_until-1e-10:
                membrane=float(plan.v_reset_mv)
                continue
            current=plan.current_na+math.fsum(p.amplitude_na for p in plan.pulses
                                               if p.start_ms<=start<p.stop_ms)
            equilibrium=plan.v_rest_mv+plan.resistance_mohm*current
            membrane=equilibrium+(membrane-equilibrium)*leak
            if not math.isfinite(membrane):
                raise ArithmeticError('nonfinite neuron state')
            if membrane>=plan.v_threshold_mv:
                spikes.append(round(end,10))
                membrane=float(plan.v_reset_mv)
                refractory_until=end+plan.refractory_ms
        cursor+=count
    return LIFTrace(tuple(spikes),float(membrane))

def compare_spikes(expected: tuple[float,...], observed: tuple[float,...], *, tolerance_ms: float=0.0) -> bool:
    """Strict event-count/time comparator for a future independently run PyNN backend."""
    if (type(expected) is not tuple or type(observed) is not tuple or
            not _finite(tolerance_ms,0,1000) or
            any(not _finite(t,0,200_000) for t in (*expected,*observed)) or
            any(a>=b for seq in (expected,observed) for a,b in zip(seq,seq[1:]))):
        raise ValueError('invalid spike trace')
    return len(expected)==len(observed) and all(abs(a-b)<=tolerance_ms for a,b in zip(expected,observed))
