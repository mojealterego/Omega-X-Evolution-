"""Bounded L7 CfC/CTM-inspired sampled numerical reference; no policy execution."""
from dataclasses import dataclass
import math
import numpy as np
from .ontos_metabolism import number


@dataclass(frozen=True)
class Sample:
    state: tuple[float, ...]
    sync: tuple[tuple[float, ...], ...]
    ticks: int


def tick_count(surprise, energy_ratio):
    if not number(surprise,0,100) or not number(energy_ratio,0,1):
        raise ValueError('tick inputs')
    return 1 if energy_ratio<.25 else (4 if surprise>1.2 and energy_ratio>.45 else (2 if surprise>.5 else 1))


def advance(state, sensory, dt, surprise, energy_ratio, *, seed=7):
    """Pure state transition; fixed seeded weights, symmetric history average."""
    if (type(state) is not tuple or not 1<=len(state)<=64 or not all(number(x,-1,1) for x in state)
            or type(sensory) is not tuple or not 1<=len(sensory)<=64 or not all(number(x,-100,100) for x in sensory)
            or not number(dt,1e-9,1.) or type(seed) is not int or not 0<=seed<2**32):
        raise ValueError('continuous input contract')
    ticks=tick_count(surprise,energy_ratio)
    d,n=len(state),len(state)+len(sensory)
    rng=np.random.default_rng(seed)
    f,g,h=(rng.normal(0,1/math.sqrt(n),(d,n)) for _ in range(3))
    raw=np.abs(rng.normal(.35,.08,(d,d))); decay=(raw+raw.T)/2
    z=np.array(state,dtype=float); hist=[]
    for _ in range(ticks):
        x=np.concatenate((z,sensory))
        gate=1/(1+np.exp(np.clip((f@x)*dt/ticks,-20,20)))
        z=gate*np.tanh(g@x)+(1-gate)*np.tanh(h@x)
        hist.append(z)
    num=np.zeros((d,d)); den=np.zeros((d,d))
    for k,v in enumerate(hist):
        w=np.exp(-decay*(ticks-1-k)); num+=w*np.outer(v,v); den+=w
    sync=num/den
    if not np.all(np.isfinite(z)) or not np.all(np.isfinite(sync)):
        raise ArithmeticError('nonfinite reference output')
    return Sample(tuple(map(float,z)),tuple(tuple(map(float,row)) for row in sync),ticks)
