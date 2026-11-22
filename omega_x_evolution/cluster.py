"""Asynchronous, checkpointed MAP-Elites islands on trusted Ray or local workers.

The driver owns authenticated durable state. Actors can lose all RAM and replay
one bounded transaction from the last committed snapshot. No external code is
executed. Ray membership is a trusted infrastructure boundary, not a sandbox.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import deque
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from contextlib import contextmanager, closing
from dataclasses import asdict, dataclass
from functools import partial
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import random
import sqlite3
import sys
from multiprocessing import get_context

from .engine import (Archive, Artifact, Audit, BASELINE, Cascade, Expression,
                     Genome, apply_patch, score, simulated_proposal)
from . import performance, annealed, holographic, safety_synthesis, epigenetics
from .topology import TopologicalArchive, TopologyPolicy
from .workers import EvaluationInput, evaluate_one
from .cluster_green import GreenLedger, Reading, WorkerPowerScenario, sample_worker_step

MAX_ISLANDS = 512
MAX_WORK = 100_000
MAX_STATE = 16 * 1024 * 1024


class ClusterError(RuntimeError):
    """Incompatible, stale, corrupt or unavailable cluster state."""


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def normalized(value):
    return json.loads(wire(value))


@dataclass(frozen=True)
class ClusterConfig:
    islands: int = 8
    rounds: int = 4
    batch: int = 4
    budget: int = 512  # proposal count, not synthetic credits or money
    parallelism: int = 8
    migration_interval: int = 2
    seed: int = 42
    timeout: int = 120
    policy: performance.Policy | None = None
    topology: TopologyPolicy | None = None
    annealed: bool = False
    holographic: bool = False
    formal_safety: bool = False
    epigenetic: bool = False
    pressure_schedule: tuple[tuple[int, int, int], ...] = ()

    @property
    def feedback(self):
        return self.annealed or self.holographic or self.formal_safety or self.epigenetic

    def __post_init__(self):
        fields = (self.islands,self.rounds,self.batch,self.budget,self.parallelism,
                  self.migration_interval,self.seed,self.timeout)
        if any(type(x) is not int for x in fields) or not (
            1 <= self.islands <= MAX_ISLANDS and 1 <= self.rounds <= 100 and
            1 <= self.batch <= 16 and self.islands <= self.budget <= MAX_WORK and
            1 <= self.parallelism <= MAX_ISLANDS and 1 <= self.migration_interval <= 100 and
            0 <= self.seed < 2**32 and 1 <= self.timeout <= 3600 and
            self.islands * (self.rounds*(self.batch+1)+1) <= MAX_WORK):
            raise ValueError('cluster resource bounds')
        if any(type(x) is not bool for x in (self.annealed,self.holographic,self.formal_safety,self.epigenetic)) or (self.feedback and min(self.budget,self.islands*self.rounds*self.batch)+self.islands*(self.rounds+1)>8192):
            raise ValueError('adaptive feedback/proof work bounds')
        if self.topology is not None and not isinstance(self.topology,TopologyPolicy):
            raise ValueError('invalid topology policy')
        if self.policy is not None and (not isinstance(self.policy,performance.Policy) or
                min(self.budget,self.islands*self.rounds*self.batch)+self.islands*(self.rounds+1)>performance.MAX_ATTEMPTS):
            raise ValueError('performance profiling attempt cap')

        if type(self.pressure_schedule) is not tuple or len(self.pressure_schedule) not in (0,self.rounds) or (self.pressure_schedule and not self.epigenetic):raise ValueError('pressure schedule')
        for row in self.pressure_schedule:
            if type(row) is not tuple or len(row)!=3:raise ValueError('pressure row')
            epigenetics.Telemetry(*row)

    def enabled_blocks(self):
        return tuple(x for x,enabled in zip(epigenetics.CLUSTER_OPTIONAL,(self.annealed,self.holographic,self.topology is not None)) if enabled)

    def allowance(self, i):
        return self.budget//self.islands + int(i < self.budget%self.islands)


def contract(cfg):
    root=Path(__file__).parent
    return {'schema':'omega-cluster-v1','config':asdict(cfg),'python':list(sys.version_info[:3]),
            'source':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in
                      ('cluster.py','engine.py','workers.py','performance.py','topology.py','annealed.py','holographic.py','safety_synthesis.py','modal.py','interval_checker.py','epigenetics.py')}}


def artifact(value):
    value=dict(value); g=dict(value.pop('genome')); g['weights']=tuple(g['weights'])
    value['metrics']=tuple(value['metrics'])
    return Artifact(genome=Genome(**g),**value)


def restore_archive(state,cfg=None):
    a=TopologicalArchive(cfg.topology) if cfg is not None and cfg.topology is not None else Archive(1)
    for item in state['lineage']:
        if not a.add(artifact(item)): raise ValueError('duplicate lineage')
    if isinstance(a,TopologicalArchive):
        a.adapt()
        if a.summary()!=state.get('topology'):raise ClusterError('topology snapshot mismatch')
    return a


def initial_state(cfg,i):
    if type(i) is not int or not 0<=i<cfg.islands: raise ValueError('island index')
    c=Cascade(cfg.seed)
    a=Artifact(f'i{i}-seed',None,0,0,BASELINE,Genome(),c.evaluate(BASELINE).metrics)
    state=normalized({'island':i,'round':0,'done':False,'attempts':0,'rejections':0,
        'lineage':[asdict(a)],'challenge':[[list(p),0] for p in c.challenge],
        'last_migrant':0,'migrations_seen':0,'migrations_accepted':0,'migrations_retained':0,
        'migration_history':[],'outgoing':None,'performance_records':[],
        'elite':asdict(a),'occupied_cells':1})
    book=safety_synthesis.RuleBook();book.learn(BASELINE,safety_synthesis.prove(BASELINE));state['safety_rules']=book.snapshot()
    if cfg.epigenetic:state['pressure_history']=[]
    if cfg.feedback:state['trajectories']=[];state['foreign_trajectories']=[]
    if cfg.formal_safety:
        certificate=safety_synthesis.prove(BASELINE)
        if not certificate['proved']:raise ClusterError('baseline formal proof failed')
        state['formal_seed']=certificate;state['formal_records']=[]
    if cfg.topology is not None:
        archive=TopologicalArchive(cfg.topology);archive.add(a);archive.adapt();state['topology']=archive.summary()
    return state


def _cascade(state,grid):
    c=Cascade.__new__(Cascade)
    c.grid=grid;c.challenge=[tuple(p) for p,_ in state['challenge']]
    c.failures={tuple(p):n for p,n in state['challenge']}
    return c


class _ReferenceArchive:
    def __init__(self,local,champion,code=None):
        self.local=local;self.cells=local.cells;self.champion=champion
        if isinstance(local,TopologicalArchive) and code is not None:
            self.cells=[{Expression(code).descriptor:local.cell_for(code)}]
    def best(self): return max((self.local.best(),self.champion),key=lambda a:(score(a.metrics),a.id))


class IslandActor:
    """Single-writer stateful actor. The signed driver snapshot is authoritative.

    Caches the live archive and last response; a restart or retry from an older
    snapshot rebuilds it from the supplied committed lineage. No storage key is
    distributed. An uncommitted step has no externally visible side effect.
    """
    def __init__(self,cfg:ClusterConfig,island:int,expected=None):
        if not 0<=island<cfg.islands: raise ValueError('island index')
        if expected is not None and contract(cfg)!=expected: raise ClusterError('actor runtime mismatch')
        self.cfg=cfg;self.island=island;self.grid=Cascade(cfg.seed).grid
        self._archive=None;self._state_key=None;self._request_key=None;self._response=None

    def step(self,state,migrant,champion,final=False):
        cfg=self.cfg;i=self.island
        if state['island']!=i or state['done'] or type(final) is not bool or final!=(state['round']==cfg.rounds):
            raise ValueError('invalid island transition')
        before=wire(state)
        request=wire([before,migrant,champion,final])
        if self._request_key==request: return normalized(self._response)
        a=self._archive if self._state_key==before else restore_archive(state,cfg)
        # Invalidate cache before mutation; errors cannot leave a cached partial archive.
        self._archive=None;self._state_key=None;self._request_key=None;self._response=None
        s=normalized(state);c=_cascade(s,self.grid);g=artifact(champion)
        r=state['round'] if final else state['round']+1
        rng=random.Random((cfg.seed<<32) ^ (i<<16) ^ r)
        audit=Audit(os.urandom(32),'omega-cluster-v1',Path(__file__).with_name('engine.py'))
        audit.rules=safety_synthesis.RuleBook(s['safety_rules'])
        last_outcome=None
        def admit(ident,code,parent,genome,external=False):
            nonlocal last_outcome
            if cfg.formal_safety:
                certificate=safety_synthesis.prove(code)
                s['formal_records'].append({'id':ident,'certificate':certificate})
                if not certificate['proved']:
                    last_outcome=0;return False
            result=c.evaluate(code);last_outcome=result.stage
            accepted=result.stage==3 and result.metrics[3]==1.
            if accepted and cfg.policy is not None:
                record=performance.check_candidate(ident,code,result.metrics[0],result.metrics[1],parent,
                                                    _ReferenceArchive(a,g,code),self.grid,cfg.policy)
                # Each pair is measured on that actor's current host. Do not compare stored durations cross-host.
                record['context']=performance.context(self.grid,cfg.policy)
                s['performance_records'].append(record);accepted=record['accepted']
            if accepted:
                token=audit.issue(ident,code,result.metrics)
                accepted=audit.verify(token,ident,code,result.metrics)
            if accepted:
                a.add(Artifact(ident,None if external else parent.id,0,r,code,genome,result.metrics))
            return accepted
        if migrant is not None:
            origin=migrant['source'];rev=migrant['revision'];incoming=artifact(migrant['artifact'])
            if (cfg.islands==1 or origin!=(i-1)%cfg.islands or type(rev) is not int or not 1<=rev<=cfg.rounds or
                not incoming.id.startswith(f'i{origin}-') or incoming.generation>rev):
                raise ValueError('invalid ring migration')
            if rev>s['last_migrant']:
                if cfg.holographic:
                    records=migrant.get('trajectories',[])
                    if len(records)>holographic.TRANSFER or any(holographic.validate(t)['island']!=origin for t in records):raise ValueError('invalid foreign trajectories')
                    s['foreign_trajectories']=records
                ident=f'i{i}-m{origin}-{rev}';s['last_migrant']=rev;s['migrations_seen']+=1
                passed=admit(ident,incoming.code,a.best(),incoming.genome,True)
                retained=passed and any(x.id==ident for cell in a.cells[0].values() for x in cell)
                s['migrations_accepted']+=int(passed);s['migrations_retained']+=int(retained)
                s['migration_history'].append({'source':origin,'revision':rev,'origin_id':incoming.id,
                    'id':ident,'accepted':passed,'retained':retained})
        if not final:
            active=set(cfg.enabled_blocks())
            if cfg.epigenetic:
                sample=epigenetics.Telemetry(*cfg.pressure_schedule[r-1]) if cfg.pressure_schedule else epigenetics.Telemetry.sample(min(100,100*cfg.batch//16))
                history=[x['sample'] for x in s['pressure_history']]+[asdict(sample)]
                s['pressure_history']=epigenetics.cluster_mask(history,cfg.enabled_blocks())
                active=set(s['pressure_history'][-1]['enabled'])
            async def propose():
                for w in range(min(cfg.batch,cfg.allowance(i)-s['attempts'])):
                    parent=a.sample(0,rng);model='deep' if w==0 else 'fast'
                    prompt=wire({'parent':parent.code,'inspiration':a.best().code,
                        'contract':'Return one exact SEARCH/REPLACE expression patch over x,y in [0,1].'})
                    patch=None;action=6;proposal_seed=None
                    records=holographic.bounded_records(s.get('trajectories',[]),s.get('foreign_trajectories',[]))
                    hits=holographic.Memory(records).retrieve(parent.code,3) if 'holographic' in active else []
                    if 'topological' in active and isinstance(a,TopologicalArchive) and (r+w)%2==0:
                        patch=a.guided_patch(parent,rng)
                    if patch is None and 'tensor' in active:
                        temperature=max(.1,1-r/max(1,cfg.rounds))
                        probabilities=annealed.policy(parent.code,records,temperature=temperature,associations=hits)
                        action=rng.choices(range(annealed.ACTIONS),probabilities)[0]
                        proposal_seed=rng.randrange(2**32);patch=annealed.propose(parent.code,action,proposal_seed)
                    if patch is None and 'holographic' in active and 'tensor' not in active:
                        hit=next((h['record'] for h in hits if h['record']['accepted'] and h['record']['reward']>0 and h['record']['child']!=parent.code),None)
                        if hit is not None:patch=f'<<<<<<< SEARCH\n{parent.code}\n=======\n{hit["child"]}\n>>>>>>> REPLACE'
                    if patch is None:
                        patch=await simulated_proposal(model,prompt,rng.randrange(2**32))
                    s['attempts']+=1;ident=f'i{i}-g{r}-p{w}'
                    try:code=apply_patch(parent.code,patch)
                    except (ValueError,TypeError):
                        if not cfg.feedback:s['rejections']+=1;continue
                        code=''
                    passed=admit(ident,code,parent,parent.genome.mutate(rng))
                    if not passed:s['rejections']+=1
                    if cfg.feedback:
                        s['trajectories'].append(holographic.trajectory(ident,i,parent.id,parent.code,code,action,passed,
                            score(a.lineage[ident].metrics) if passed else 0.,score(parent.metrics),last_outcome,proposal_seed))
            asyncio.run(propose())
            c.advance(cfg.seed+i*101+r);s['round']=r
        else:s['done']=True
        if isinstance(a,TopologicalArchive):
            a.adapt();s['topology']=a.summary()
        s['safety_rules']=audit.rules.snapshot()
        s['lineage']=[asdict(x) for x in a.lineage.values()]
        s['challenge']=[[list(p),c.failures[p]] for p in c.challenge]
        s['elite']=asdict(a.best());s['occupied_cells']=len(a.cells[0])
        if not final and (r%cfg.migration_interval==0 or r==cfg.rounds):
            s['outgoing']={'source':i,'revision':r,'artifact':s['elite']}
            if cfg.holographic:s['outgoing']['trajectories']=s['trajectories'][-holographic.TRANSFER:]
        s=normalized(s)
        self._archive=a;self._state_key=wire(s);self._request_key=request;self._response=s
        return normalized(s)

    def execute(self,*args,observed=False):
        if type(observed) is not bool:raise ValueError('observation flag must be boolean')
        def invoke(*items):return {'state':self.step(*items),'pid':os.getpid()}
        return sample_worker_step(invoke,*args) if observed else invoke(*args)


def _verify_record(row,new,local,champion,policy,grid):
    """Recheck policy arithmetic and reference identities; wall time is trusted actor evidence."""
    if row['candidate_sha256']!=hashlib.sha256(new.code.encode()).hexdigest() or row['correctness']!=new.metrics[0] or row['performance_proxy']!=new.metrics[1] or row['accepted'] is not True:
        raise ClusterError('admission profile mismatch')
    parent=local.lineage[new.parent] if new.parent is not None else local.best()
    cell=local.cell_for(new.code) if isinstance(local,TopologicalArchive) else local.cells[0].get(Expression(new.code).descriptor,[])
    role,ref=('cell',max(cell,key=lambda a:(score(a.metrics),a.id))) if cell else ('champion',_ReferenceArchive(local,champion).best())
    expected=[('parent',parent)]+([(role,ref)] if ref.code!=parent.code else [])
    ctx=performance.context(grid,policy)
    stable=('schema','policy','workload_sha256','implementation_sha256','engine_sha256','rounds','passes','python')
    if len(row['comparisons'])!=len(expected) or any(row['context'][k]!=ctx[k] for k in stable): raise ClusterError('missing or incompatible profile references')
    for p,(role,ref) in zip(row['comparisons'],expected):
        if (p['role']!=role or p['baseline_id']!=ref.id or p['baseline_sha256']!=hashlib.sha256(ref.code.encode()).hexdigest() or
                p['baseline_quality']!=ref.metrics[0] or p['candidate_quality']!=new.metrics[0]): raise ClusterError('wrong performance baseline')
        cmp=performance.Comparison(role,ref.id,ref.metrics[0],new.metrics[0],
                       tuple(performance.Latency(**x) for x in p['baseline']),tuple(performance.Latency(**x) for x in p['candidate']))
        d=performance.decide(cmp,policy)
        if not d.accepted or normalized(asdict(d))!=p['decision']: raise ClusterError('invalid performance decision')


def _verify_feedback(cfg,old,new,migrant,consume,mid,n,r,grid,challenge,byid):
    if not cfg.feedback:
        if any(k in new for k in ('trajectories','foreign_trajectories','formal_records','formal_seed')):raise ClusterError('unexpected feedback')
        return
    history=new['trajectories'];prior=old['trajectories'];fresh=history[len(prior):]
    if history[:len(prior)]!=prior or len(fresh)!=n:raise ClusterError('trajectory count or prefix mismatch')
    foreign=migrant.get('trajectories',[]) if cfg.holographic and consume else old['foreign_trajectories']
    if new['foreign_trajectories']!=foreign or len(foreign)>holographic.TRANSFER:raise ClusterError('foreign trajectory mismatch')
    for t in foreign:holographic.validate(t)
    proofs=new.get('formal_records',[]);previous=old.get('formal_records',[])
    if cfg.formal_safety:
        if old.get('formal_seed')!=new.get('formal_seed') or not safety_synthesis.verify(BASELINE,new.get('formal_seed')):raise ClusterError('invalid seed certificate')
        if proofs[:len(previous)]!=previous or len(proofs)-len(previous)!=n+consume:raise ClusterError('missing formal obligations')
        fresh_proofs=proofs[len(previous):]
        expected_ids=([mid] if consume else [])+[f'i{old["island"]}-g{r}-p{w}' for w in range(n)]
        if [p['id'] for p in fresh_proofs]!=expected_ids:raise ClusterError('proof order mismatch')
        certificates={p['id']:p['certificate'] for p in fresh_proofs}
    else:
        if 'formal_records' in new or 'formal_seed' in new:raise ClusterError('unexpected formal record')
        certificates={}
    admitted={x['id']:artifact(x) for x in new['lineage'][len(old['lineage']):]}
    available={x['id']:artifact(x) for x in old['lineage']}
    def check(ident,code):
        if cfg.formal_safety:
            proof=safety_synthesis.prove(code)
            if certificates[ident]!=proof:raise ClusterError('invalid proof certificate')
            if not proof['proved']:
                if ident in admitted:raise ClusterError('unproved admission')
                return 0
        outcome=evaluate_one(EvaluationInput(code,challenge,grid)).result
        qualified=outcome.stage==3 and outcome.metrics[3]==1.
        if ident in admitted:
            if not qualified or admitted[ident].code!=code or admitted[ident].metrics!=outcome.metrics:raise ClusterError('invalid feedback admission')
        elif qualified and not (cfg.policy is not None and ident in byid and byid[ident]['accepted'] is False):
            raise ClusterError('unexplained rejected feedback')
        return outcome.stage
    if consume:
        check(mid,migrant['artifact']['code'])
        if mid in admitted:available[mid]=admitted[mid]
    for w,t in enumerate(fresh):
        t=holographic.validate(t);ident=f'i{old["island"]}-g{r}-p{w}'
        parent=available.get(t['parent_id'])
        if t['id']!=ident or t['island']!=old['island'] or parent is None or t['parent']!=parent.code or t['baseline']!=score(parent.metrics):raise ClusterError('trajectory provenance mismatch')
        if (t['action']<annealed.ACTIONS and (not cfg.annealed or t['proposal_seed'] is None)) or (t['action']==6 and t['proposal_seed'] is not None):raise ClusterError('unverified operator identity')
        result=check(ident,t['child']);accepted=ident in admitted
        if t['accepted']!=accepted or t['stage']!=result or (accepted and (t['quality']!=score(admitted[ident].metrics) or admitted[ident].parent!=parent.id)):
            raise ClusterError('trajectory reward or stage mismatch')
        if accepted:available[ident]=admitted[ident]

def verify_transition(cfg,old,new,migrant,champion,final):
    """Independently recompute every newly admitted candidate's deterministic gate.

    Accepted lineage is append-only; the driver never trusts worker fitness.
    Physical timing samples remain in the trusted Ray actor boundary.
    """
    try:
        i=old['island'];r=old['round'] if final else old['round']+1
        if (new['island']!=i or new['round']!=r or new['done'] is not final or
            new['lineage'][:len(old['lineage'])]!=old['lineage'] or
            new['performance_records'][:len(old['performance_records'])]!=old['performance_records'] or
            new['migration_history'][:len(old['migration_history'])]!=old['migration_history']): raise ClusterError('nonappend transition')
        n=0 if final else min(cfg.batch,cfg.allowance(i)-old['attempts'])
        rejected=new['rejections']-old['rejections'];fresh=new['lineage'][len(old['lineage']):]
        consume=int(migrant is not None and migrant['revision']>old['last_migrant'])
        migrations=new['migration_history'][len(old['migration_history']):]
        if len(migrations)!=consume or new['migrations_seen']!=old['migrations_seen']+consume or new['attempts']!=old['attempts']+n or not 0<=rejected<=n:
            raise ClusterError('counter mismatch')
        if consume:
            m=migrations[0]; incoming=artifact(migrant['artifact']);mid=f'i{i}-m{migrant["source"]}-{migrant["revision"]}'
            if (m['source']!=migrant['source'] or m['revision']!=migrant['revision'] or m['origin_id']!=incoming.id or m['id']!=mid or
                type(m['accepted']) is not bool or type(m['retained']) is not bool or (m['retained'] and not m['accepted'])): raise ClusterError('migration receipt mismatch')
        else: m=None;mid=None
        mcount=int(bool(m and m['accepted']));retained=int(bool(m and m['retained']))
        if (new['last_migrant']!=(migrant['revision'] if consume else old['last_migrant']) or new['migrations_accepted']!=old['migrations_accepted']+mcount or
            new['migrations_retained']!=old['migrations_retained']+retained or len(fresh)!=n-rejected+mcount): raise ClusterError('migration/accounting mismatch')
        grid=Cascade(cfg.seed).grid;challenge=tuple(tuple(p) for p,_ in old['challenge']);a=restore_archive(old,cfg)
        profiles=new['performance_records'][len(old['performance_records']):];byid={p['candidate_id']:p for p in profiles}
        if len(byid)!=len(profiles) or (cfg.policy is None and profiles) or len(profiles)>n+consume: raise ClusterError('profile budget mismatch')
        expected_ids={f'i{i}-g{r}-p{w}' for w in range(n)}|({mid} if consume else set())
        if set(byid)-expected_ids: raise ClusterError('unexpected profiling identity')
        rules=safety_synthesis.RuleBook(old['safety_rules'])
        for index,item in enumerate(fresh):
            x=artifact(item)
            if x.generation!=r or x.island!=0 or x.id not in expected_ids: raise ClusterError('artifact identity mismatch')
            if x.id==mid:
                if index!=0 or not mcount or x.parent is not None or x.code!=incoming.code or x.genome!=incoming.genome:raise ClusterError('migration artifact mismatch')
            elif x.parent not in a.lineage:raise ClusterError('missing local parent')
            outcome=evaluate_one(EvaluationInput(x.code,challenge,grid)).result
            if outcome.stage!=3 or outcome.metrics!=x.metrics or x.metrics[3]!=1.: raise ClusterError('independent evaluator mismatch')
            g=x.genome
            if not (2<=g.sharpness<=30 and .1<=g.threshold<=.9 and .3<=g.novelty<=2.5 and len(g.weights)==4 and
                all(type(w) in (int,float) and math.isfinite(w) and 0<=w<=1 for w in g.weights) and g.weights[3]==0 and math.isclose(sum(g.weights),1.)):
                raise ClusterError('invalid genome')
            if cfg.policy is not None: _verify_record(byid[x.id],x,a,artifact(champion),cfg.policy,grid)
            rules.learn(x.code,safety_synthesis.prove(x.code))
            if not a.add(x):raise ClusterError('duplicate admitted artifact')
            if x.id==mid and m['retained']!=any(z.id==mid for cell in a.cells[0].values() for z in cell):
                raise ClusterError('migration retention mismatch')
        if new['safety_rules']!=rules.snapshot():raise ClusterError('invalid learned safety rule registry')
        if mcount and mid not in a.lineage:raise ClusterError('missing migrant')
        if cfg.epigenetic:
            prior=old['pressure_history'];history=new['pressure_history']
            if len(history)!=len(prior)+int(not final) or history[:len(prior)]!=prior or history!=epigenetics.cluster_mask([x['sample'] for x in history],cfg.enabled_blocks()):raise ClusterError('invalid epigenetic history')
            if not final:
                if cfg.pressure_schedule and history[-1]['sample']!=asdict(epigenetics.Telemetry(*cfg.pressure_schedule[r-1])):raise ClusterError('pressure schedule mismatch')
                if 'tensor' not in history[-1]['enabled'] and any(t['action']<annealed.ACTIONS for t in new['trajectories'][len(old['trajectories']):]):raise ClusterError('disabled tensor action')
        elif 'pressure_history' in new:raise ClusterError('unexpected epigenetics')
        _verify_feedback(cfg,old,new,migrant,consume,mid,n,r,grid,challenge,byid)
        if isinstance(a,TopologicalArchive):
            a.adapt()
            if new.get('topology')!=a.summary():raise ClusterError('topology summary mismatch')
        elif 'topology' in new:raise ClusterError('unexpected topology')
        if normalized(asdict(a.best()))!=new['elite'] or len(a.cells[0])!=new['occupied_cells']: raise ClusterError('archive summary mismatch')
        outgoing={'source':i,'revision':r,'artifact':new['elite']} if not final and (r%cfg.migration_interval==0 or r==cfg.rounds) else old['outgoing']
        if cfg.holographic and not final and (r%cfg.migration_interval==0 or r==cfg.rounds):outgoing['trajectories']=new['trajectories'][-holographic.TRANSFER:]
        if new['outgoing']!=outgoing:raise ClusterError('invalid outgoing elite')
        # Challenge points remain bounded; exact failure counts are actor-generated.
        ch=new['challenge']
        if not 1<=len(ch)<=36 or not {(0.,0.),(0.,1.),(1.,0.),(.5,.5)}<={tuple(p) for p,_ in ch} or len({tuple(p) for p,_ in ch})!=len(ch) or any(len(p)!=2 or any(type(v) not in (int,float) or not 0<=v<=1 for v in p) or type(k) is not int or k<0 for p,k in ch):raise ClusterError('invalid challenge')
    except (ValueError,TypeError,KeyError,IndexError,OverflowError,AttributeError) as exc:
        raise ClusterError('invalid worker transition') from exc


class Store:
    """One authenticated CAS row per island, including its latest published elite.

    The operator controls the SQLite file/directory and key. No shared NFS or
    cluster filesystem required. One driver is supported, not HA consensus.
    """
    def __init__(self,path,key,cfg):
        if type(key) is not bytes or not 32<=len(key)<=4096 or not isinstance(cfg,ClusterConfig): raise ValueError('invalid store configuration')
        self.path=Path(path).absolute();self.key=key;self.cfg=cfg;self.identity=wire(contract(cfg))

    def _mac(self,i,rev,body):
        return hmac.digest(self.key,wire(['omega-cluster-v1',self.identity,i,rev,body]).encode(),'sha256')

    @contextmanager
    def _db(self,write=False):
        try:
            with closing(sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True,timeout=5)) as db:
                db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA synchronous=FULL')
                with db:
                    db.execute('BEGIN IMMEDIATE' if write else 'BEGIN');yield db
        except sqlite3.Error as exc:raise ClusterError('cluster storage failure') from exc

    def initialize(self):
        try:os.close(os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
        except OSError as exc:raise ClusterError('use a new store or explicit resume') from exc
        with self._db(True) as db:
            db.execute('CREATE TABLE meta (id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL,mac BLOB NOT NULL)')
            db.execute('CREATE TABLE islands (id INTEGER PRIMARY KEY,rev INTEGER NOT NULL,body TEXT NOT NULL,mac BLOB NOT NULL)')
            db.execute('INSERT INTO meta VALUES (1,?,?)',(self.identity,self._mac(-1,0,self.identity)))
            for i in range(self.cfg.islands):
                body=wire(initial_state(self.cfg,i));db.execute('INSERT INTO islands VALUES (?,?,?,?)',(i,0,body,self._mac(i,0,body)))
        return self

    def open(self):
        with self._db() as db:
            row=db.execute('SELECT body,mac FROM meta WHERE id=1').fetchone()
            if not row or row[0]!=self.identity or type(row[1]) is not bytes or not hmac.compare_digest(row[1],self._mac(-1,0,row[0])):raise ClusterError('contract or key mismatch')
            if db.execute('SELECT count(*) FROM islands').fetchone()[0]!=self.cfg.islands:raise ClusterError('missing island records')
        return self

    def _read(self,db,i):
        row=db.execute('SELECT rev,body,mac FROM islands WHERE id=? AND length(body)<=?',(i,MAX_STATE)).fetchone()
        if not row or type(row[0]) is not int or not 0<=row[0]<=self.cfg.rounds+1 or type(row[1]) is not str or type(row[2]) is not bytes or not hmac.compare_digest(row[2],self._mac(i,row[0],row[1])):raise ClusterError('snapshot authentication failure')
        state=json.loads(row[1]);rev=row[0]
        if state['island']!=i or state['round']+int(state['done'])!=rev:raise ClusterError('snapshot revision mismatch')
        return rev,state

    def read(self,i):
        if type(i) is not int or not 0<=i<self.cfg.islands:raise ValueError('invalid island')
        with self._db() as db:return self._read(db,i)

    def commit(self,i,revision,state):
        body=wire(state)
        if len(body.encode())>MAX_STATE or state['island']!=i or state['round']+int(state['done'])!=revision+1:raise ClusterError('invalid snapshot bounds')
        with self._db(True) as db:
            rev,_=self._read(db,i)
            if rev!=revision:raise ClusterError('stale island revision')
            changed=db.execute('UPDATE islands SET rev=?,body=?,mac=? WHERE id=? AND rev=?',
                        (rev+1,body,self._mac(i,rev+1,body),i,rev)).rowcount
            if changed!=1:raise ClusterError('concurrent island commit')


def _process(cfg,i,expected,args,observed=False):
    return IslandActor(cfg,i,expected).execute(*args,observed=observed)


class LocalBackend:
    """Thread simulation or actual spawned local process transport."""
    def __init__(self,cfg,*,processes=False):
        self.cfg=cfg;self.worker_pids=set();self.processes=processes
        self.pool=(ProcessPoolExecutor(max_workers=min(cfg.parallelism,32),mp_context=get_context('spawn')) if processes else ThreadPoolExecutor(max_workers=min(cfg.parallelism,32)))
        self.actors=None if processes else [IslandActor(cfg,i) for i in range(cfg.islands)]
        self.expected=contract(cfg)

    async def call(self,i,*args,observed=False):
        if type(observed) is not bool:raise ValueError('observation flag must be boolean')
        loop=asyncio.get_running_loop()
        result=await (loop.run_in_executor(self.pool,_process,self.cfg,i,self.expected,args,observed)
                      if self.processes else loop.run_in_executor(self.pool,partial(self.actors[i].execute,*args,observed=observed)))
        self.worker_pids.add(result['pid'])
        return result if observed else result['state']

    def close(self):self.pool.shutdown(wait=True,cancel_futures=True)
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


class RayIslandActor(IslandActor):
    def execute(self,*args,observed=False):
        import ray
        return {**super().execute(*args,observed=observed),'node_id':ray.get_runtime_context().get_node_id()}


class RayBackend:
    """Real Ray actor transport, explicitly attached to an operator-owned cluster.

    Full snapshots make retries safe even after constructor-only actor restart.
    No `ray.get` blocks the event loop; ObjectRef is awaitable.
    """
    def __init__(self,cfg,*,address,distinct_nodes=False):
        if type(address) is not str or not address or '://' in address:raise ValueError('explicit direct Ray address required (local, auto, existing or head host:port)')
        try:import ray
        except ImportError as exc:raise ClusterError('install optional ray extra') from exc
        self.ray=ray;self.owned=not ray.is_initialized();self.actors=[];self.worker_pids=set();self.nodes=set();self.pinned={}
        if not self.owned and address!='existing':raise ClusterError('already initialized; use explicit existing Ray session')
        if self.owned and address=='existing':raise ClusterError('no existing Ray session')
        try:
            if self.owned:
                if address=='local':ray.init(address='local',include_dashboard=False)
                else:ray.init(address=address)
            if ray.cluster_resources().get('CPU',0)<cfg.islands:raise ClusterError('one CPU reservation per island required')
            remote=ray.remote(num_cpus=1,max_restarts=3,max_task_retries=3,max_concurrency=1,max_pending_calls=2)(RayIslandActor)
            nodes=sorted(n['NodeID'] for n in ray.nodes() if n['Alive'] and n['Resources'].get('CPU',0)>=1)
            if distinct_nodes and len(nodes)<cfg.islands:raise ClusterError('insufficient distinct Ray nodes')
            expected=contract(cfg)
            for i in range(cfg.islands):
                strategy='SPREAD'
                if distinct_nodes:
                    from ray.util.scheduling_strategies import NodeAffinitySchedulingStrategy
                    strategy=NodeAffinitySchedulingStrategy(node_id=nodes[i],soft=False)
                    self.pinned[i]=nodes[i]
                self.actors.append(remote.options(scheduling_strategy=strategy).remote(cfg,i,expected))
        except BaseException:self.close();raise

    async def call(self,i,*args,observed=False):
        if type(observed) is not bool:raise ValueError('observation flag must be boolean')
        result=await self.actors[i].execute.remote(*args,observed=observed)
        node=result['node_id']
        if not isinstance(node,str) or not node or (i in self.pinned and self.pinned[i]!=node):raise ClusterError('Ray node placement mismatch')
        self.nodes.add(node);self.worker_pids.add((node,result['pid']))
        return result if observed else result['state']

    def close(self):
        for a in self.actors:
            try:self.ray.kill(a,no_restart=True)
            except Exception:pass
        self.actors.clear()
        if self.owned:self.ray.shutdown()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


async def run_cluster(store,backend,*,stop_after=None,green=None):
    """Independent island progress, bounded in-flight work, latest-value ring.

    A final drain delivers the last committed outbound elite from each neighbor.
    No per-generation barrier. Stop count is the number of new durable commits.
    """
    cfg=store.cfg;store.open()
    if stop_after is not None and (type(stop_after) is not int or not 1<=stop_after<=cfg.islands*(cfg.rounds+1)):raise ValueError('invalid stop count')
    rows=[store.read(i) for i in range(cfg.islands)]
    if green is not None and type(green) is not WorkerPowerScenario:
        raise ValueError('typed optional worker power scenario required')
    ledger=(GreenLedger(green,islands=cfg.islands,initial_revisions=tuple(rev for rev,_ in rows))
            if green is not None else None)
    commits=0;pending={};todo=deque(i for i,(_,s) in enumerate(rows) if s['round']<cfg.rounds)
    draining=False
    def champion():return max((s['elite'] for _,s in rows),key=lambda x:(score(x['metrics']),x['id']))
    async def dispatch(i,old,m,g,final):
        if ledger is not None:
            return await asyncio.wait_for(backend.call(i,old,m,g,final,observed=True),cfg.timeout)
        return await asyncio.wait_for(backend.call(i,old,m,g,final),cfg.timeout)
    try:
        while True:
            if not todo and not pending:
                if draining:break
                draining=True;todo=deque(i for i,(_,s) in enumerate(rows) if not s['done'])
                if not todo:break
            while todo and len(pending)<cfg.parallelism and (stop_after is None or commits+len(pending)<stop_after):
                i=todo.popleft();rev,old=rows[i];m=rows[(i-1)%cfg.islands][1]['outgoing'] if cfg.islands>1 else None
                if m is not None and m['revision']<=old['last_migrant']:m=None
                g=champion();task=asyncio.create_task(dispatch(i,old,m,g,draining));pending[task]=(i,rev,old,m,g,draining)
            if not pending:break
            ready,_=await asyncio.wait(pending,return_when=asyncio.FIRST_COMPLETED)
            for task in sorted(ready,key=lambda t:pending[t][0]):
                i,rev,old,m,g,final=pending.pop(task)
                answer=task.result()
                new=answer['state'] if ledger is not None else answer
                verify_transition(cfg,old,new,m,g,final)
                store.commit(i,rev,new);rows[i]=(rev+1,new);commits+=1
                if ledger is not None:
                    try:
                        signal=answer['green_reading']
                        reading=Reading(**signal)
                    except (TypeError,KeyError,ValueError,OverflowError):
                        reading=None  # corrupt worker clock is UNKNOWN, never synthetic zero
                    try:
                        ledger.commit(i,rev+1,reading,
                                      attempts=new['attempts']-old['attempts'],
                                      rejections=new['rejections']-old['rejections'],
                                      profiled=len(new['performance_records'])-len(old['performance_records']),
                                      perf_rejected=(sum(not p['accepted'] for p in new['performance_records'])
                                                     -sum(not p['accepted'] for p in old['performance_records'])))
                    except (TypeError,KeyError,ValueError,OverflowError):
                        pass  # no telemetry side effect may change the committed state
                if not final and new['round']<cfg.rounds:todo.append(i)
            if stop_after is not None and commits>=stop_after:break
    finally:
        for task in pending:task.cancel()
        if pending:await asyncio.gather(*pending,return_exceptions=True)
    states=[s for _,s in rows];c=Cascade(cfg.seed);best=champion()
    report={'schema':'omega-async-cluster-v1','complete':all(s['done'] for s in states),
        'islands':cfg.islands,'commits':sum(rev for rev,_ in rows),'attempts':sum(s['attempts'] for s in states),
        'rejections':sum(s['rejections'] for s in states),'budget':cfg.budget,
        'occupied_cells':sum(s['occupied_cells'] for s in states),'lineage_size':sum(len(s['lineage']) for s in states),
        'migrations_seen':sum(s['migrations_seen'] for s in states),'migrations_accepted':sum(s['migrations_accepted'] for s in states),
        'migrations_retained':sum(s['migrations_retained'] for s in states),
        'performance_profiled':sum(len(s['performance_records']) for s in states),
        'performance_rejections':sum(not p['accepted'] for s in states for p in s['performance_records']),
        'baseline_score':score(c.evaluate(BASELINE).metrics),'champion_score':score(best['metrics']),
        'champion':best['code'],'holdout_quality':c.heldout(best['code']) if all(s['done'] for s in states) else None,
        'island_rounds':[s['round'] for s in states]}
    if cfg.feedback:
        report['trajectory_count']=sum(len(s['trajectories']) for s in states)
        report['foreign_trajectories']=sum(len(s['foreign_trajectories']) for s in states)
        report['formal_checks']=sum(len(s.get('formal_records',[])) for s in states)
        report['formal_rejections']=sum(not p['certificate']['proved'] for s in states for p in s.get('formal_records',[]))
        report['action_counts']=[sum(t['action']==i for s in states for t in s['trajectories']) for i in range(7)]
    if cfg.topology is not None:
        report['topology']={'leaf_count':sum(s['topology']['leaf_count'] for s in states),'islands':[s['topology'] for s in states]}
    if ledger is not None:
        report['green_computing']=ledger.report(expected_commits=commits)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for f in ('islands','rounds','batch','budget','parallelism','migration_interval','seed','timeout'):
        p.add_argument('--'+f.replace('_','-'),type=int,default=getattr(ClusterConfig(),f))
    p.add_argument('--db',type=Path,required=True);p.add_argument('--key-file',type=Path,required=True)
    p.add_argument('--backend',choices=('process','ray','simulation'),default='process');p.add_argument('--ray-address');p.add_argument('--distinct-nodes',action='store_true')
    p.add_argument('--topology',action='store_true');p.add_argument('--topology-depth',type=int,default=4);p.add_argument('--topology-split-count',type=int,default=4);p.add_argument('--topology-window',type=int,default=64)
    p.add_argument('--epigenetic',action='store_true');p.add_argument('--annealed',action='store_true');p.add_argument('--holographic',action='store_true');p.add_argument('--formal-safety',action='store_true')
    p.add_argument('--performance-regression',action='store_true');p.add_argument('--resume',action='store_true');p.add_argument('--stop-after',type=int)
    p.add_argument('--green-watts',type=float,nargs=3,metavar=('LOW','MID','HIGH'))
    p.add_argument('--green-power-source');p.add_argument('--green-intensity-g-per-kwh',type=float)
    p.add_argument('--green-intensity-source')
    args=vars(p.parse_args());db=args.pop('db');key_file=args.pop('key_file');mode=args.pop('backend');address=args.pop('ray_address');distinct=args.pop('distinct_nodes');resume=args.pop('resume');stop=args.pop('stop_after');policy=performance.Policy() if args.pop('performance_regression') else None
    watts=args.pop('green_watts');power_source=args.pop('green_power_source');intensity=args.pop('green_intensity_g_per_kwh');intensity_source=args.pop('green_intensity_source')
    supplied=[watts,power_source,intensity,intensity_source]
    if any(x is not None for x in supplied) and not all(x is not None for x in supplied):p.error('all four Green Computing settings are required together')
    try:green=WorkerPowerScenario(*watts,intensity,power_source,intensity_source) if watts is not None else None
    except ValueError as exc:p.error(str(exc))
    if mode=='ray' and not address or mode!='ray' and (address or distinct):p.error('Ray requires --ray-address; Ray flags cannot be used with local backend')
    topology=TopologyPolicy(depth=args.pop('topology_depth'),split_count=args.pop('topology_split_count'),window=args.pop('topology_window'))
    enabled=args.pop('topology')
    cfg=ClusterConfig(**args,policy=policy,topology=topology if enabled else None)
    with key_file.open('rb') as f:key=f.read(4097)
    store=Store(db,key,cfg)
    backend=RayBackend(cfg,address=address,distinct_nodes=distinct) if mode=='ray' else LocalBackend(cfg,processes=mode=='process')
    with backend:
        store.open() if resume else store.initialize()
        r=asyncio.run(run_cluster(store,backend,stop_after=stop,green=green));r.update(backend=mode,worker_processes=len(backend.worker_pids))
        if mode=='ray':r['observed_ray_nodes']=len(backend.nodes)
    print(json.dumps(r,indent=2,allow_nan=False))


if __name__=='__main__':main()
