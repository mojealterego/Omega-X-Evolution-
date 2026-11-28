"""Deterministic, source-fenced memory proposals for the scheduler AST engine.

Trusted local supervisor supplies current independent memory fence and clock.
Only bounded numerical hints are interpreted; no retrieved code or instruction.
Research only: no release authority or live lease over returned reports.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import sys

import cryptography

from .ontos_epoch_journal_core import IntegrityError
from .ontos_hyperrag import HyperRAGJournal, Search
from .ontos_managed_journal import Fence
from .ontos_otce import Read, _int, _time
from .ontos_v72_jcs import canonical_json

DOMAIN=b'OMEGA-X/engine-memory/v1\x00'
_HINT=re.compile(r'scheduler (abs|square|ratio) ([0-9]{1,5}) ([0-9]{1,4}) ([0-9]{1,5})\Z',re.ASCII)


def _hash(value): return sha256(DOMAIN+canonical_json(value)).hexdigest()


def _runtime():
    names=('engine_memory.py','engine.py','ontos_hyperrag.py','ontos_sealed_otce.py',
           'ontos_otce.py','ontos_rcc.py','ontos_reversible_ops.py','ontos_managed_journal.py',
           'ontos_epoch_journal_core.py','ontos_v72_jcs.py','ontos_v72_receipts.py')
    return _hash({'files':{n:sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in names},
                  'python':list(sys.version_info[:3]),'sqlite':sqlite3.sqlite_version,
                  'cryptography':cryptography.__version__})


def _pool(texts,weights):
    if (type(weights) is not tuple or len(weights)!=2 or any(type(w) is not Fraction for w in weights)):
        raise ValueError('two exact R1 coordinates required')
    pool=set()
    for text in texts:
        match=_HINT.fullmatch(text)
        if match:
            family,a,b,c=match.groups(); a,b,c=map(int,(a,b,c))
            if 1<=a<=10000 and 1<=b<=1000 and 0<=c<=10000:
                pool.add((family,a,b,c))
    if any(weights):
        pool.add(('square',max(1,min(10000,int(1000+1000*weights[0]))),10,
                  max(0,min(10000,int(1000+1000*weights[1])))))
    return tuple(sorted(pool))


def _capture(source,db,r,w,s,retained,now):
    if (type(source) is not HyperRAGJournal or source._scope.dimension!=2
            or type(r) is not Read or type(w) is not Read or type(s) is not Search
            or type(retained) is not Fence or not _time(now) or r.query!=w.query
            or r.query.branch!='actual' or w.operation!='weights' or w.key!=s.shard):
        raise ValueError('exact signed actual-view retrieval and R1 queries required')
    hits=source._search_locked(db,r,s,retained=retained,now=now)
    nodes,_=source._selection(w,retained=retained,now=now)
    weights=source._weights_locked(db,nodes)
    pool=_pool(tuple(h.text for h in hits),weights)
    f=retained
    commitment=_hash([source._state_pin(),[f.generation,f.cursor.sequence,f.cursor.digest.hex(),f.lineage.hex()],
                      asdict(s),asdict(r.query),r.epoch,w.epoch,[asdict(h.citation) for h in hits],
                      [n['output'] for n in nodes if n['kind']=='R1'],
                      [[str(x.numerator),str(x.denominator)] for x in weights],[list(x) for x in pool]])
    return pool,commitment


@dataclass(frozen=True,slots=True)
class Selector:
    stride: int
    fast: int
    deep: int

    def __post_init__(self):
        if not _int(self.stride,0,3) or not all(_int(x,0,16) for x in (self.fast,self.deep)):
            raise ValueError('bounded selector IR')

    def seed(self,role,seed):
        self.__post_init__()
        if role not in ('fast','deep') or not _int(seed,0,2**32-1): raise ValueError('proposal input')
        return (self.stride*seed+(self.fast if role=='fast' else self.deep))%(2**32)

    def wire(self): return [self.stride,self.fast,self.deep]



@dataclass(frozen=True,slots=True)
class MemoryProposal:
    source: HyperRAGJournal
    retrieval: Read
    weights: Read
    search: Search
    retained: Fence
    clock: object
    pool: tuple[tuple[str,int,int,int],...]
    commitment: str
    runtime: str
    selector: Selector=Selector(1,0,0)

    @classmethod
    def bind(cls,source,r,w,s,*,retained,clock):
        if type(source) is not HyperRAGJournal or not callable(clock):
            raise ValueError('typed memory source and trusted clock required')
        with source._vault() as db:
            pool,pin=_capture(source,db,r,w,s,retained,clock())
        return cls(source,r,w,s,retained,clock,pool,pin,_runtime())

    def contract(self):
        if type(self.selector) is not Selector: raise ValueError('typed selector required')
        self.selector.__post_init__()
        return {'schema':'memory-proposal-v2','input':self.commitment,'runtime':self.runtime,'selector':self.selector.wire()}

    @contextmanager
    def guard(self):
        """Revalidate under cooperating source lock; no lock across async work."""
        self.contract()
        if type(self.source) is not HyperRAGJournal or not callable(self.clock):
            raise IntegrityError('invalid memory adapter')
        with self.source._vault() as db:
            try:
                pool,pin=_capture(self.source,db,self.retrieval,self.weights,self.search,self.retained,self.clock())
                if pool!=self.pool or pin!=self.commitment or _runtime()!=self.runtime:
                    raise IntegrityError('memory proposal commitment changed')
            except (ValueError,sqlite3.Error,OSError) as exc:
                raise IntegrityError('memory proposal no longer authorized') from exc
            yield

    async def __call__(self,model,prompt,seed):
        from .engine import Expression, simulated_proposal
        if model not in ('fast','deep') or not _int(seed,0,2**32-1) or type(prompt) is not str or len(prompt)>8192:
            raise ValueError('invalid proposal request')
        parent=json.loads(prompt)['parent']; Expression(parent)
        self.contract(); seed=self.selector.seed(model,seed)
        if not self.pool:
            return await simulated_proposal(model,prompt,seed)
        # Stable integer selection; neither clock nor external provider affects replay.
        family,a,b,c=self.pool[seed%len(self.pool)]
        if family not in ('abs','square','ratio') or not _int(a,1,10000) or not _int(b,1,1000) or not _int(c,0,10000):
            raise ValueError('invalid numeric hint')
        aa,bb,cc=(f'{n//1000}.{n%1000:03d}' for n in (a,b,c))
        term={'abs':f'{aa}*abs(x-y)','square':f'{aa}*(x-y)*(x-y)',
              'ratio':f'{aa}*(x-y)*(x-y)/({bb}+min(x,y))'}[family]
        candidate=f'-(x+y+{term}+{cc})'
        Expression(candidate)
        return f'<<<<<<< SEARCH\n{parent}\n=======\n{candidate}\n>>>>>>> REPLACE'
