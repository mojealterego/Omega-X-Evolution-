"""Bounded recursive mutation of memory proposal selection, not executable code.

Research state only. Trusted evaluator, source authorization, independent fences
and immutable runtime are prerequisites; no deployment or permission grants.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
import math
from pathlib import Path
import random
import sqlite3

from .engine import Config, run
from .engine_memory import MemoryProposal, Selector
from .ontos_epoch_journal_core import IntegrityError
from .ontos_managed_journal import Fence, ManagedJournal
from .ontos_v72_jcs import canonical_json, parse_json

DOMAIN=b'OMEGA-X/DGM-selector/v1\x00'


def _int(x,lo,hi): return type(x) is int and lo<=x<=hi


def _hash(x): return sha256(DOMAIN+canonical_json(x)).hexdigest()


BASE=Selector(1,0,0)


def mutations(parent,population,seed):
    if type(parent) is not Selector or not _int(population,2,8) or not _int(seed,0,2**64-1):
        raise ValueError('mutation budget')
    parent.__post_init__()
    neighbors=[]
    for field,limit in (('stride',3),('fast',16),('deep',16)):
        neighbors.extend(replace(parent,**{field:i}) for i in range(limit+1) if i!=getattr(parent,field))
    # Always examine a change between constant and seed-driven dispatch.
    toggle=replace(parent,stride=0 if parent.stride else 1)
    neighbors.remove(toggle)
    return (parent,toggle,*random.Random(seed).sample(neighbors,population-2))


@dataclass(frozen=True,slots=True)
class Plan:
    config: Config
    rounds: int
    population: int
    seed: int

    def __post_init__(self):
        if (type(self.config) is not Config or not _int(self.rounds,1,8) or not _int(self.population,2,8)
                or not _int(self.seed,0,2**32-1)):
            raise ValueError('bounded DGM plan')
        if any(type(getattr(self.config,k)) is not int for k in ('seed','generations','islands','workers','budget','concurrency')):
            raise ValueError('integer engine configuration required')
        self.config.__post_init__()
        if self.config.generations*self.config.islands*self.config.workers*self.rounds*(2*self.population+4)>10000:
            raise ValueError('total proposal bound')

    def pin(self,memory):
        self.__post_init__()
        if type(memory) is not MemoryProposal or memory.selector!=BASE: raise ValueError('base memory adapter required')
        files=('engine_dgm.py','engine.py','engine_memory.py','checkpoint.py','workers.py','modal.py','interval_checker.py','safety_synthesis.py','ontos_managed_journal.py','ontos_epoch_journal_core.py')
        return _hash({'plan':asdict(self),'memory':memory.contract(),
                      'runtime':{n:sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in files},
                      'gate':'per-seed nonregression objective/holdout/cost/rejections; strict objective gain'})

    def schedule(self,i):
        return random.Random(self.seed).sample(range(2**32),4*self.rounds)[4*i:4*i+4]


def _report_hash(report):
    return sha256(json.dumps(report,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _metric(report):
    return [report['champion_score'],report['holdout_quality'],report['spent'],report['rejections'],_report_hash(report)]


def _valid_metrics(rows,budget):
    return (type(rows) is list and len(rows)==2 and all(type(r) is list and len(r)==5
            and all(type(x) in (int,float) and math.isfinite(x) and 0<=x<=1 for x in r[:2])
            and all(_int(x,0,budget) for x in r[2:4]) and type(r[4]) is str and len(r[4])==64
            and all(c in '0123456789abcdef' for c in r[4]) for r in rows))


def _same_ints(value,expected):
    return type(value) is list and all(type(x) is int for x in value) and value==expected


def _rank(rows): return (sum(r[0] for r in rows),sum(r[1] for r in rows),-sum(r[2] for r in rows),-sum(r[3] for r in rows))


def _promote(before,after):
    return (all(b[0]<=a[0] and b[1]<=a[1] and b[2]>=a[2] and b[3]>=a[3] for b,a in zip(before,after,strict=True))
            and any(a[0]>b[0] for b,a in zip(before,after,strict=True)))


@dataclass(frozen=True,slots=True)
class Outcome:
    status: str
    fence: Fence | None
    active: Selector | None
    record: dict | None=None


class DGMJournal:
    def __init__(self,anchor,segments,memory,plan,pin):
        if type(plan) is not Plan or type(memory) is not MemoryProposal or plan.pin(memory)!=pin:
            raise ValueError('independent plan pin required')
        source=memory.source
        dirs=[Path(anchor).parent.resolve(),Path(segments).resolve(),source._vault_path.parent.resolve(),source._journal.anchor.parent.resolve(),source._journal.segments]
        if any(a==b or a in b.parents or b in a.parents for i,a in enumerate(dirs) for b in dirs[i+1:]):
            raise ValueError('separate trust directories required')
        self.memory=memory; self.plan=plan; self.pin=pin
        self._journal=ManagedJournal(anchor,segments,self._digest,self._replay,self._encode,self._decode)

    def _guard(self,source_fence):
        if type(source_fence) is not Fence or source_fence!=self.memory.retained:
            raise IntegrityError('independently retained source fence changed')
        if self.plan.pin(self.memory)!=self.pin: raise IntegrityError('DGM runtime changed')
        return self.memory.guard()

    def _validate(self,rows):
        if type(rows) is not tuple or len(rows)>self.plan.rounds: raise ValueError('round bound')
        parent=BASE
        for i,r in enumerate(rows):
            candidates=mutations(parent,self.plan.population,(self.plan.seed<<8)+i)
            if (type(r) is not dict or set(r)!={'round','parent','seeds','training','challenger','before','after','promoted','active','release_authorized'}
                    or not _int(r['round'],i+1,i+1) or not _same_ints(r['parent'],parent.wire()) or not _same_ints(r['seeds'],self.plan.schedule(i))
                    or r['release_authorized'] is not False or type(r['training']) is not list
                    or len(r['training'])!=len(candidates)):
                raise ValueError('round lineage')
            for c,entry in zip(candidates,r['training'],strict=True):
                if (type(entry) is not dict or set(entry)!={'selector','metrics'} or not _same_ints(entry['selector'],c.wire())
                        or not _valid_metrics(entry['metrics'],self.plan.config.budget)):
                    raise ValueError('invalid training evidence')
            winner=max(range(len(candidates)),key=lambda k:(_rank(r['training'][k]['metrics']),-k))
            challenger=candidates[winner]
            if (not _same_ints(r['challenger'],challenger.wire()) or not _valid_metrics(r['before'],self.plan.config.budget)
                    or not _valid_metrics(r['after'],self.plan.config.budget)):
                raise ValueError('invalid validation evidence')
            passed=challenger!=parent and _promote(r['before'],r['after'])
            if r['promoted'] is not passed: raise ValueError('invalid promotion decision')
            if passed: parent=challenger
            if not _same_ints(r['active'],parent.wire()): raise ValueError('invalid inherited selector')
        return parent

    def _encode(self,rows):
        self._validate(rows)
        return canonical_json([self.pin,list(rows)])

    def _digest(self,rows): return sha256(DOMAIN+self._encode(rows)).digest()

    def _decode(self,raw):
        pin,rows=parse_json(raw)
        if pin!=self.pin or type(rows) is not list: raise ValueError('plan mismatch')
        rows=tuple(rows)
        if self._encode(rows)!=raw: raise ValueError('noncanonical state')
        return rows

    def _replay(self,rows,raw):
        try:
            row=parse_json(raw)
            if canonical_json(row)!=raw: return None
            out=rows+(row,); self._validate(out); return out
        except (ValueError,TypeError,KeyError,OverflowError): return None

    def initialize(self,*,source_fence):
        with self._guard(source_fence): return self._journal.initialize(()).fence

    def recover_from_anchor(self,*,source_fence):
        """Operator recovery, not independent freshness evidence."""
        with self._guard(source_fence): return self._journal.read().fence

    def active(self,retained,*,source_fence):
        if type(retained) is not Fence: raise ValueError('independent DGM fence required')
        rows=self._journal.read(retained).state
        try:
            with self._guard(source_fence): return self._validate(rows)
        except (IntegrityError,ValueError,OSError,sqlite3.Error): return None

    async def step(self,retained,*,source_fence,evaluation_processes=1):
        if type(retained) is not Fence or not _int(evaluation_processes,1,2): raise ValueError('fence or worker count')
        with self._guard(source_fence): rows=self._journal.read(retained).state
        parent=self._validate(rows); i=len(rows)
        if i>=self.plan.rounds: return Outcome('EXHAUSTED',retained,parent)
        seeds=self.plan.schedule(i); candidates=mutations(parent,self.plan.population,(self.plan.seed<<8)+i)
        async def measure(selector,group):
            proposal=replace(self.memory,selector=selector)
            values=[]
            for seed in group:
                with self._guard(source_fence): pass
                report=await run(replace(self.plan.config,seed=seed),proposal,evaluation_processes=evaluation_processes)
                values.append(_metric(report))
            if not _valid_metrics(values,self.plan.config.budget): raise IntegrityError('invalid evaluator metrics')
            return values
        training=[{'selector':c.wire(),'metrics':await measure(c,seeds[:2])} for c in candidates]
        k=max(range(len(candidates)),key=lambda k:(_rank(training[k]['metrics']),-k))
        challenger=candidates[k]
        before=await measure(parent,seeds[2:]); after=await measure(challenger,seeds[2:])
        passed=challenger!=parent and _promote(before,after)
        active=challenger if passed else parent
        record={'round':i+1,'parent':parent.wire(),'seeds':seeds,'training':training,'challenger':challenger.wire(),
                'before':before,'after':after,'promoted':passed,'active':active.wire(),'release_authorized':False}
        with self._guard(source_fence): u=self._journal.append(retained,canonical_json(record))
        if u.status!='COMMITTED': return Outcome(u.status,None,None)
        return Outcome(u.status,u.snapshot.fence,active,record)
