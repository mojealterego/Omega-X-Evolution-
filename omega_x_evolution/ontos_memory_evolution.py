"""Bounded memory-guided ONTOS policy evolution; research checkpoints only.

The trusted evaluator runs the actual paired simulator. Retrieved text is data,
not code. The generic expression engine and production release are untouched.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
import re
import sqlite3
import sys

import numpy as np
import cryptography

from .ontos_ablation import BASE, _evaluate, _validate
from .ontos_epoch_journal_core import IntegrityError
from .ontos_hyperrag import HyperRAGJournal, Search
from .ontos_managed_journal import Fence, ManagedJournal
from .ontos_observation_policy import PolicyConfig
from .ontos_otce import Query, Read, _int, _pin, _time
from .ontos_v72_jcs import canonical_json, parse_json

DOMAIN=b'OMEGA-X/memory-evolution/v1\x00'
MAX_REVIEWS=8
BASE_PAIR=(4000,30)
_HINT=re.compile(r'floor ([0-9]{1,5}) hazard ([0-9]{1,4})\Z',re.ASCII)


def _hash(value): return sha256(DOMAIN+canonical_json(value)).hexdigest()


def _runtime_pin():
    names=('ontos_memory_evolution.py','ontos_ablation.py','ontos_observation_policy.py',
           'ontos_testbed.py','ontos_paired_interventions.py','ontos_v50_belief.py',
           'ontos_hyperrag.py','ontos_sealed_otce.py','ontos_otce.py','ontos_rcc.py',
           'ontos_reversible_ops.py','ontos_managed_journal.py','ontos_epoch_journal_core.py',
           'ontos_v72_jcs.py','ontos_v72_receipts.py')
    return {'sources':{name:sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in names},
            'python':list(sys.version_info[:3]),'numpy':np.__version__,'sqlite':sqlite3.sqlite_version,
            'cryptography':cryptography.__version__}


def _pair(pair):
    return type(pair) in (tuple,list) and len(pair)==2 and _int(pair[0],1,80000) and _int(pair[1],0,1000)


def _config(pair):
    if not _pair(pair): raise ValueError('bounded candidate')
    return replace(BASE,floor=pair[0]/1_000_000,hazard=pair[1]/1000)


def candidates(texts,weights):
    """Finite numeric grammar and two R1 coordinates, never executable code."""
    if (type(texts) is not tuple or len(texts)>16 or any(type(t) is not str or len(t)>512 for t in texts)
            or type(weights) is not tuple or len(weights)!=2 or any(type(w) is not Fraction for w in weights)):
        raise ValueError('bounded memory candidates')
    pool={BASE_PAIR}
    for text in texts:
        match=_HINT.fullmatch(text)
        if match:
            p=tuple(map(int,match.groups()))
            if _pair(p): pool.add(p)
    if any(weights):
        pool.add((max(1,min(80000,int(4000+4000*weights[0]))),
                  max(0,min(1000,int(30+70*weights[1])))))
    return (BASE_PAIR,*sorted(pool-{BASE_PAIR}))


@dataclass(frozen=True,slots=True)
class Plan:
    source: str
    search: Search
    development: tuple[int,...]
    validation: tuple[int,...]
    horizon: int
    query: Query

    def __post_init__(self):
        if not _pin(self.source) or type(self.search) is not Search or type(self.query) is not Query or self.query.branch!='actual':
            raise ValueError('typed plan source and actual view')
        self.search.__post_init__(); self.query.__post_init__()
        _validate(self.development,self.horizon); _validate(self.validation,self.horizon)
        if set(self.development)&set(self.validation): raise ValueError('overlapping evaluation seeds')

    @property
    def pin(self):
        self.__post_init__()
        return _hash({'plan':{**asdict(self),'development':list(self.development),'validation':list(self.validation)},'objective':'strict correct gain; no extra wrong/harm or fewer OOD abstentions',
                      'candidate':'floor-millionths hazard-thousandths; R1 two-coordinate v1','simulator':'paired-v1',
                      'runtime':_runtime_pin()})


def _fence(f):
    if type(f) is not Fence: raise ValueError('independent source fence required')
    f.__post_init__()
    return [f.generation,f.cursor.sequence,f.cursor.digest.hex(),f.lineage.hex()]


def _safe(a,b):
    return (a['correct']>b['correct'] and a['wrong']<=b['wrong'] and a['harm']==b['harm']==0
            and a['ood']==b['ood'] and a['ood_abstentions']>=b['ood_abstentions'])


@dataclass(frozen=True,slots=True)
class Outcome:
    status: str
    fence: Fence | None
    config: PolicyConfig
    report: dict | None=None


class EvolutionJournal:
    """Trusted local evaluation and fenced research state; no release authority."""
    def __init__(self,anchor,segments,source,plan: Plan,pin: str):
        if (type(source) is not HyperRAGJournal or type(plan) is not Plan or plan.pin!=pin
                or plan.source!=source._state_pin() or source._scope.dimension!=2):
            raise ValueError('independently pinned two-dimensional memory plan required')
        dirs=[Path(anchor).parent.resolve(),Path(segments).resolve(),source._vault_path.parent.resolve(),
              source._journal.anchor.parent.resolve(),source._journal.segments]
        if any(a==b or a in b.parents or b in a.parents for i,a in enumerate(dirs) for b in dirs[i+1:]):
            raise ValueError('separate memory and evolution directories')
        self._source=source; self._plan=plan
        self._journal=ManagedJournal(anchor,segments,self._digest,self._replay,self._encode,self._decode)

    def _record(self,row):
        if (type(row) is not dict or set(row)!={'source','input','report','pair'} or not _pin(row['input'])
                or not _pin(row['report']) or not _pair(row['pair']) or type(row['source']) is not list
                or len(row['source'])!=4 or not _int(row['source'][0],0,1024)
                or not _int(row['source'][1],0,256) or not all(_pin(x) for x in row['source'][2:])):
            raise ValueError('invalid research checkpoint')
        return row

    def _encode(self,rows):
        if type(rows) is not tuple or len(rows)>MAX_REVIEWS: raise ValueError('review capacity')
        return canonical_json([self._plan.pin,[self._record(r) for r in rows]])

    def _digest(self,rows): return sha256(DOMAIN+self._encode(rows)).digest()

    def _decode(self,raw):
        pin,rows=parse_json(raw)
        if pin!=self._plan.pin or type(rows) is not list: raise ValueError('plan mismatch')
        rows=tuple(rows)
        if self._encode(rows)!=raw: raise ValueError('checkpoint canonical form')
        return rows

    def _replay(self,rows,raw):
        if len(rows)>=MAX_REVIEWS: return None
        try:
            row=self._record(parse_json(raw))
            if canonical_json(row)!=raw: return None
            return rows+(row,)
        except (ValueError,TypeError): return None

    def initialize(self): return self._journal.initialize(()).fence

    def recover_from_anchor(self):
        """Explicit operator recovery; the protected anchor is not freshness proof."""
        return self._journal.read().fence

    def verify_report(self,expected,report):
        if type(expected) is not Fence: raise ValueError('independent evolution fence required')
        rows=self._journal.read(expected).state
        return bool(rows and type(report) is dict and _hash(report)==rows[-1]['report'])

    def _inputs_locked(self,db,r,w,retained,now):
        _fence(retained)
        if (type(r) is not Read or type(w) is not Read or r.query!=self._plan.query or w.query!=self._plan.query
                or w.operation!='weights' or not _time(now)):
            raise ValueError('exact signed retrieval and weights queries required')
        hits=self._source._search_locked(db,r,self._plan.search,retained=retained,now=now)
        nodes,_=self._source._selection(w,retained=retained,now=now)
        weights=self._source._weights_locked(db,nodes)
        pool=candidates(tuple(h.text for h in hits),weights)
        # Bind R1 provenance even when removal leaves identical aggregate weights.
        lineage=[n['output'] for n in nodes if n['kind']=='R1']
        pin=_hash([self._plan.pin,_fence(retained),[asdict(h.citation) for h in hits],lineage,
                   [[str(x.numerator),str(x.denominator)] for x in weights],[list(x) for x in pool]])
        return pool,pin

    def run(self,expected,r,w,*,retained,now):
        if type(expected) is not Fence: raise ValueError('independent evolution fence required')
        if len(self._journal.read(expected).state)>=MAX_REVIEWS: return Outcome('EXHAUSTED',None,BASE)
        with self._source._vault() as db:
            pool,pin=self._inputs_locked(db,r,w,retained,now)
        arms=tuple((str(i),_config(pair)) for i,pair in enumerate(pool))
        dev_rows,_,dev=_evaluate(arms,self._plan.development,self._plan.horizon)
        eligible=[i for i in range(1,len(pool)) if _safe(dev[str(i)],dev['0'])]
        winner=max(eligible,key=lambda i:(dev[str(i)]['correct'],-dev[str(i)]['wrong'],-i),default=0)
        validation_arms=(('baseline',BASE),('candidate',_config(pool[winner])))
        val_rows,_,val=_evaluate(validation_arms,self._plan.validation,self._plan.horizon)
        chosen=pool[winner] if winner and _safe(val['candidate'],val['baseline']) else BASE_PAIR
        report={'schema':'memory-evolution-v1','plan':self._plan.pin,'input':pin,'source':_fence(retained),
                'candidates':[list(x) for x in pool],'development':dev,'development_rows':dev_rows,
                'validation':{'steps':val['candidate']['steps'],'baseline':val['baseline'],'candidate':val['candidate']},
                'validation_rows':val_rows,'development_winner':list(pool[winner]),'chosen':list(chosen),
                'release_authorized':False,'independent_holdout_verified':False}
        row={'source':_fence(retained),'input':pin,'report':_hash(report),'pair':list(chosen)}
        # Serialize against cooperating source mutations for the checkpoint commit.
        with self._source._vault() as db:
            if self._inputs_locked(db,r,w,retained,now)[1]!=pin: raise IntegrityError('memory changed during evaluation')
            u=self._journal.append(expected,canonical_json(row))
        if u.status!='COMMITTED': return Outcome(u.status,None,BASE)
        return Outcome(u.status,u.snapshot.fence,_config(chosen),report)

    def recommend(self,expected,r,w,*,retained,now):
        if type(expected) is not Fence: raise ValueError('independent evolution fence required')
        rows=self._journal.read(expected).state
        if not rows: return Outcome('BASELINE',expected,BASE)
        row=rows[-1]
        if row['source']!=_fence(retained): return Outcome('ROLLED_BACK',expected,BASE)
        try:
            with self._source._vault() as db:
                _,pin=self._inputs_locked(db,r,w,retained,now)
        except (ValueError,sqlite3.Error,OSError): return Outcome('ROLLED_BACK',expected,BASE)
        if pin!=row['input']: return Outcome('ROLLED_BACK',expected,BASE)
        pair=tuple(row['pair'])
        return Outcome('BASELINE' if pair==BASE_PAIR else 'RESEARCH_CANDIDATE',expected,_config(pair))
