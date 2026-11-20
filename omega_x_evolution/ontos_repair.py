"""Simulated (M,R) contraction and TAME proxies on bounded numeric data only."""
from dataclasses import dataclass, replace
import math
from .ontos_metabolism import number


@dataclass(frozen=True)
class RepairState:
    error: tuple[float, ...]
    integrity: float
    budget: int
    remaining: int

    def __post_init__(self):
        if (type(self.error) is not tuple or not 1<=len(self.error)<=64 or not all(number(x,-100,100) for x in self.error)
                or not number(self.integrity,.1,1) or type(self.budget) is not int or not 1<=self.budget<=10**9
                or type(self.remaining) is not int or not 0<=self.remaining<=self.budget):
            raise ValueError('repair state contract')


def inject(state, noise):
    if type(state) is not RepairState or type(noise) is not tuple or len(noise)!=len(state.error) or not all(number(x,-100,100) for x in noise):
        raise ValueError('fault contract')
    return replace(state,error=tuple(float(x+y) for x,y in zip(state.error,noise)))


def repair(state, spend):
    if type(state) is not RepairState or type(spend) is not int or not 1<=spend<=10**9:
        raise ValueError('repair debit contract')
    ratio=state.remaining/state.budget
    before=math.hypot(*state.error)
    paid=spend if ratio>.15 and (state.remaining-spend)*100>=15*state.budget and before>0 else 0
    nxt=state
    if paid:
        dose=paid/state.budget
        rate=.65*dose*state.integrity
        nxt=replace(state,error=tuple((1-rate)*x for x in state.error),integrity=min(1.,state.integrity+.05*dose),remaining=state.remaining-paid)
    after=math.hypot(*nxt.error); closure=math.exp(-after)*nxt.integrity
    remaining_ratio=nxt.remaining/nxt.budget
    return nxt,{'spent':paid,'damage_before':before,'damage_after':after,'closure':closure,'tame_spatial_proxy':1+4*closure*remaining_ratio,'tame_temporal_proxy':1+9*closure*remaining_ratio}
