"""Immutable finite grid fault/recovery scenario, calling the existing v41 repair.

Data-only resilience experiment. No process restart, autonomous code patching,
network actions, capability grant, hardware fault handling or live recovery.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
import hashlib
import json
import math
import re
import numpy as np
from .ontos_repair import RepairState, inject, repair

_ID=re.compile(r'[A-Za-z0-9_-]{1,64}\Z')


def _finite(x,a,b):
    return type(x) in (int,float) and math.isfinite(x) and a<=x<=b


@dataclass(frozen=True,slots=True)
class FaultReceipt:
    ident:str
    kind:str
    cells:tuple[int,...]
    amount:float
    requested_spend:int
    spent:int
    error_before:float
    error_after:float


@dataclass(frozen=True,slots=True)
class GridCheckpoint:
    side:int
    state:RepairState
    applied_ids:tuple[str,...]=()
    audit:tuple[FaultReceipt,...]=()

    def __post_init__(self):
        if (type(self.side) is not int or not 2<=self.side<=6
            or type(self.state) is not RepairState or type(self.applied_ids) is not tuple
            or type(self.audit) is not tuple or len(self.audit)>128
            or len(self.applied_ids)!=len(self.audit)
            or len(set(self.applied_ids))!=len(self.applied_ids)
            or self.applied_ids != tuple(row.ident for row in self.audit)
            or any(type(row) is not FaultReceipt for row in self.audit)
            or len(self.state.error)!=self.side**2):
            raise ValueError('grid checkpoint contract')
        self.state.__post_init__()


def apply_event(checkpoint:GridCheckpoint,ident:str,kind:str,cells:tuple[int,...],amount:float,spend:int)->GridCheckpoint:
    if type(checkpoint) is not GridCheckpoint:
        raise ValueError('checkpoint required')
    checkpoint.__post_init__()
    if (type(ident) is not str or _ID.fullmatch(ident) is None
        or kind not in ('inject','repair') or type(kind) is not str
        or type(cells) is not tuple or type(spend) is not int or type(amount) not in (int,float)
        or not _finite(amount,0.,1.) or spend < 0 or spend > 10**9):
        raise ValueError('bounded event contract')
    if kind == 'inject':
        if not cells or len(cells)>checkpoint.side**2 or len(set(cells))!=len(cells) or any(type(i) is not int or not 0<=i<checkpoint.side**2 for i in cells) or amount<=0 or spend!=0:
            raise ValueError('fault injection contract')
    elif cells or amount!=0 or spend<=0:
        raise ValueError('repair event contract')
    if ident in checkpoint.applied_ids:
        old=checkpoint.audit[checkpoint.applied_ids.index(ident)]
        if (old.kind,old.cells,old.amount,old.requested_spend)!=(kind,cells,float(amount),spend):
            raise ValueError('idempotency key reused with different payload')
        return checkpoint
    if len(checkpoint.audit)>=128:
        raise ValueError('audit capacity exceeded')
    before=math.hypot(*checkpoint.state.error)
    if kind=='inject':
        noise=tuple(float(amount) if i in cells else 0. for i in range(checkpoint.side**2))
        new_state=inject(checkpoint.state,noise)
        paid=0
    else:
        new_state,receipt=repair(checkpoint.state,spend)
        paid=int(receipt['spent'])
    after=math.hypot(*new_state.error)
    row=FaultReceipt(ident,kind,cells,float(amount),spend,paid,before,after)
    return replace(checkpoint,state=new_state,applied_ids=checkpoint.applied_ids+(ident,),audit=checkpoint.audit+(row,))


def fault_campaign(seeds:tuple[int,...])->dict:
    if (type(seeds) is not tuple or not 1<=len(seeds)<=30
        or any(type(s) is not int or not 0<=s<2**32 for s in seeds)
        or len(set(seeds))!=len(seeds)):
        raise ValueError('unique finite seed campaign')
    rows=[]
    for seed in seeds:
        rng=np.random.default_rng(seed)
        positions=tuple(sorted(map(int,rng.choice(9,size=2,replace=False))))
        amount=float(rng.uniform(.4,.8))
        state=GridCheckpoint(3,RepairState((0.,)*9,1.,1000,1000))
        state=apply_event(state,'fault','inject',positions,amount,0)
        before=math.hypot(*state.state.error)
        for i,spend in enumerate((100,200,250)):
            state=apply_event(state,f'repair-{i}','repair',(),0.,spend)
        after=math.hypot(*state.state.error)
        rows.append({'seed':seed,'positions':positions,'before_error':before,'after_error':after,
                     'spent':sum(t.spent for t in state.audit),
                     'remaining':state.state.remaining,'repaired_error_fraction':1-after/before,
                     'audit_sha256':hashlib.sha256(json.dumps([
                         [a.ident,a.kind,a.cells,a.amount,a.spent,a.error_after]
                         for a in state.audit],separators=(',',':')).encode()).hexdigest()})
    return {'simulation_only':True,'measured_physical_recovery':False,
            'number_of_seeds':len(seeds),'runs':rows,'hardware_recovery':'NOT_APPLICABLE'}
