"""Pure integer resource accounting: work estimates are NOT measured FLOPs.

Units here are declared *model operation units* and serialized byte budgets.
Actual hardware energy, memory traffic and algorithmic work are UNKNOWN until
instrumented outside this module. Never report an estimate as a measurement.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
import re

_KINDS=frozenset(('inference','update','qr','svd','lp','io'))
_ID=re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
_CAP=10**12


def _quantity(v: object,limit: int=_CAP) -> bool:
    return type(v) is int and 0 <= v <= limit


@dataclass(frozen=True,slots=True)
class WorkEstimate:
    kind: str
    compute_units: int
    io_bytes: int

    def __post_init__(self):
        if (type(self.kind) is not str or self.kind not in _KINDS
            or not _quantity(self.compute_units) or not _quantity(self.io_bytes)):
            raise ValueError('work estimate bounds')


def estimate_kernel(kind: str, *, rows: int, cols: int) -> WorkEstimate:
    """Fixed reference formulas, NOT exact algorithm or physical FLOP counts.

    Integer op units: matvec 2mn, update 4mn, QR 2mn², SVD 4mn²,
    toy LP 3mn, I/O 0; memory traffic budget 2 * 8mn (I/O 8mn).
    """
    if (type(kind) is not str or kind not in _KINDS
        or type(rows) is not int or not 1 <= rows <= 512
        or type(cols) is not int or not 1 <= cols <= 512
        or kind in ('qr','svd') and rows < cols):
        raise ValueError('kernel estimate domain')
    pair=rows*cols
    op={'inference':2*pair,'update':4*pair,'qr':2*pair*cols,
        'svd':4*pair*cols,'lp':3*pair,'io':0}[kind]
    io=(1 if kind=='io' else 2)*8*pair
    return WorkEstimate(kind,op,io)


@dataclass(frozen=True,slots=True)
class WorkLedger:
    max_compute_units: int
    max_io_bytes: int
    used_compute_units: int = 0
    used_io_bytes: int = 0
    open_tickets: tuple[tuple[str,WorkEstimate], ...] = ()
    settled_ids: tuple[str,...] = ()
    unknown_tickets: tuple[str,...] = ()

    def __post_init__(self):
        if (not _quantity(self.max_compute_units) or not _quantity(self.max_io_bytes)
            or not _quantity(self.used_compute_units,self.max_compute_units)
            or not _quantity(self.used_io_bytes,self.max_io_bytes)
            or type(self.open_tickets) is not tuple or len(self.open_tickets)>32
            or type(self.settled_ids) is not tuple or len(self.settled_ids)>1024
            or type(self.unknown_tickets) is not tuple or len(self.unknown_tickets)>1024):
            raise ValueError('ledger bounds')
        if any(type(x) is not tuple or len(x)!=2 or type(x[0]) is not str
               or _ID.fullmatch(x[0]) is None or type(x[1]) is not WorkEstimate
               for x in self.open_tickets):
            raise ValueError('ticket type')
        for _, plan in self.open_tickets:
            WorkEstimate(plan.kind,plan.compute_units,plan.io_bytes)
        ids=[x[0] for x in self.open_tickets]
        if (len(set(ids))!=len(ids) or any(type(i) is not str or _ID.fullmatch(i) is None
            for i in self.settled_ids+self.unknown_tickets) or
            len(set(self.settled_ids)) != len(self.settled_ids) or
            set(ids)&set(self.settled_ids) or
            not set(self.unknown_tickets) <= set(self.settled_ids)):
            raise ValueError('ticket identity')
        if (self.used_compute_units+self.reserved_compute_units>self.max_compute_units
            or self.used_io_bytes+self.reserved_io_bytes>self.max_io_bytes):
            raise ValueError('ledger capacity')

    @property
    def reserved_compute_units(self) -> int:
        return sum(plan.compute_units for _,plan in self.open_tickets)

    @property
    def reserved_io_bytes(self) -> int:
        return sum(plan.io_bytes for _,plan in self.open_tickets)

    @property
    def complete(self) -> bool:
        return not self.open_tickets and not self.unknown_tickets

    def reserve(self,ident: str,plan: WorkEstimate) -> 'WorkLedger':
        self.__post_init__()
        if (type(ident) is not str or _ID.fullmatch(ident) is None
            or type(plan) is not WorkEstimate or len(self.open_tickets)>=32
            or ident in self.settled_ids or any(i==ident for i,_ in self.open_tickets)):
            raise ValueError('invalid or repeated work ticket')
        WorkEstimate(plan.kind,plan.compute_units,plan.io_bytes)
        return replace(self,open_tickets=self.open_tickets+((ident,plan),))

    def settle(self,ident: str,*,actual_compute_units: int|None,
               actual_io_bytes: int|None) -> 'WorkLedger':
        self.__post_init__()
        if type(ident) is not str:
            raise ValueError('ticket identity')
        matching=[plan for i,plan in self.open_tickets if i==ident]
        if len(matching)!=1:
            raise ValueError('ticket not reserved')
        plan=matching[0]
        if ((actual_compute_units is not None and not _quantity(actual_compute_units,plan.compute_units))
            or (actual_io_bytes is not None and not _quantity(actual_io_bytes,plan.io_bytes))):
            raise ValueError('actual work exceeds reserved budget')
        unknown = actual_compute_units is None or actual_io_bytes is None
        used_compute=plan.compute_units if actual_compute_units is None else actual_compute_units
        used_io=plan.io_bytes if actual_io_bytes is None else actual_io_bytes
        return replace(self, used_compute_units=self.used_compute_units+used_compute,
                       used_io_bytes=self.used_io_bytes+used_io,
                       open_tickets=tuple((i,p) for i,p in self.open_tickets if i!=ident),
                       settled_ids=self.settled_ids+(ident,),
                       unknown_tickets=self.unknown_tickets+((ident,) if unknown else ()))

    def report(self) -> dict:
        self.__post_init__()
        return {'used_compute_units':self.used_compute_units,'used_io_bytes':self.used_io_bytes,
                'reserved_compute_units':self.reserved_compute_units,
                'reserved_io_bytes':self.reserved_io_bytes,
                'unknown_tickets':self.unknown_tickets,
                'verification':('UNKNOWN_ACTUAL_WORK' if self.unknown_tickets else
                                'PENDING_RESERVATIONS' if self.open_tickets else 'CALLER_REPORTED_ONLY'),
                'physical_joules':'UNKNOWN'}
