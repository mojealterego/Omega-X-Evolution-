"""Low-rank Kuramoto flow over bounded, nonnegative symmetric coupling.

Pure numerical model. Nonnegative factors ensure symmetric nonnegative W=F Fᵀ.
O(nr) coupling; potential-energy diagnostic is O(n²). Euler step is deliberately
bounded; monotonic energy is NOT guaranteed for arbitrary forced trajectories.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
import math
import numpy as np


def finite(x,low,high):
    return type(x) in (int,float) and math.isfinite(x) and low<=x<=high


@dataclass(frozen=True,slots=True)
class KuramotoState:
    phase: tuple[float,...]
    frequency: tuple[float,...]
    factors: tuple[tuple[float,...],...]

    def __post_init__(self):
        n=len(self.phase) if type(self.phase) is tuple else 0
        if not 1<=n<=32 or type(self.frequency) is not tuple or len(self.frequency)!=n or type(self.factors) is not tuple or len(self.factors)!=n:
            raise ValueError('bounded oscillator state')
        if not all(finite(x,-1e4,1e4) for x in self.phase) or not all(finite(x,-100.,100.) for x in self.frequency):
            raise ValueError('phase/frequency finite bound')
        r=len(self.factors[0]) if type(self.factors[0]) is tuple else 0
        if not 1<=r<=min(8,n) or any(type(row) is not tuple or len(row)!=r or not all(finite(v,0.,1.) for v in row) for row in self.factors):
            raise ValueError('low-rank positive factors required')


def coupling_force(state: KuramotoState) -> tuple[float,...]:
    if type(state) is not KuramotoState:
        raise ValueError('state type')
    state.__post_init__()
    p=np.asarray(state.phase,dtype=np.float64)
    f=np.asarray(state.factors,dtype=np.float64)
    cos=np.cos(p); sin=np.sin(p)
    # sum_j Wij sin(theta_j-theta_i) = cos_i sum_k Fik sum_j Fjk sin_j - sin_i sum_k Fik sum_j Fjk cos_j
    force=(cos*(f@(f.T@sin))-sin*(f@(f.T@cos)))/len(p)
    if not np.all(np.isfinite(force)):
        raise ArithmeticError('nonfinite Kuramoto force')
    return tuple(map(float,force))


def advance(state: KuramotoState,dt: float,*,steps: int=1) -> KuramotoState:
    if type(state) is not KuramotoState or not finite(dt,1e-9,.05) or type(steps) is not int or not 1<=steps<=256:
        raise ValueError('bounded Euler step')
    state.__post_init__()
    result=state
    for _ in range(steps):
        force=coupling_force(result)
        # Avoid modulo wrap here to maintain phase continuity in time.
        next_phase=tuple(x+dt*(w+f) for x,w,f in zip(result.phase,result.frequency,force))
        result=replace(result,phase=next_phase)
        result.__post_init__()
    return result


def potential_energy(state: KuramotoState) -> float:
    if type(state) is not KuramotoState:
        raise ValueError('state type')
    state.__post_init__()
    p=state.phase; f=state.factors; n=len(p)
    e=math.fsum(math.fsum(f[i][k]*f[j][k] for k in range(len(f[0]))) * (1-math.cos(p[i]-p[j]))
                for i in range(n) for j in range(i+1,n)) / n
    return float(e)


def order_parameter(state: KuramotoState) -> float:
    if type(state) is not KuramotoState: raise ValueError('state type')
    state.__post_init__()
    return math.hypot(math.fsum(math.cos(t) for t in state.phase),math.fsum(math.sin(t) for t in state.phase))/len(state.phase)
