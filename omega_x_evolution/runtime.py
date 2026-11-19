"""Bounded autonomous research campaigns: typed dispatch, budget, durable replay."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import random
import sys

import numpy as np

from . import science, polyglot, experiments, neuro_symbolic
from .training import TARGETS
from .engine import Config, run
from .compute import Router, probe
from .checkpoint import CheckpointStore, CheckpointError
from .graph_memory import GraphMemory, canonical

TASKS=(*science.DOMAINS,'bits','numeric','scheduler')


@dataclass(frozen=True)
class Task:
    domain:str
    seed:int
    data_json:str|None=None

    def __post_init__(self):
        if self.domain not in TASKS or type(self.seed) is not int or not 0<=self.seed<2**32: raise ValueError('invalid research task')
        if self.data_json is not None:
            if type(self.data_json) is not str or len(self.data_json)>524288: raise ValueError('task data size')
            if self.domain=='scheduler': raise ValueError('scheduler fixed benchmark does not accept custom data')
            if self.domain in science.DOMAINS: canonical_data=science.Data.from_json(self.data_json).to_json()
            elif self.domain=='bits': canonical_data=canonical(dict(zip(('train','holdout'),polyglot.parse_dataset(self.data_json))))
            else:
                data=neuro_symbolic.Split.from_json(self.data_json)
                canonical_data=canonical(asdict(data))
            object.__setattr__(self,'data_json',canonical_data)

    def contract(self):
        return {'domain':self.domain,'seed':self.seed,'data_sha256':None if self.data_json is None else hashlib.sha256(self.data_json.encode()).hexdigest()}


@dataclass(frozen=True)
class Campaign:
    tasks:tuple[Task,...]
    budget:int=128
    epochs:int=100
    work_cap:int=50_000_000
    training_backend:str="numpy"
    inference_backend:str="cpu"

    def __post_init__(self):
        if (type(self.tasks) is not tuple or not 1<=len(self.tasks)<=12 or any(not isinstance(t,Task) for t in self.tasks) or len(set(self.tasks))!=len(self.tasks) or
            type(self.budget) is not int or not 1<=self.budget<=4096 or type(self.epochs) is not int or not 1<=self.epochs<=400 or type(self.work_cap) is not int or not 1<=self.work_cap<=200_000_000): raise ValueError('campaign limits')
        if self.training_backend not in ('numpy',*TARGETS) or self.inference_backend not in ('cpu','torch','npu','qnn'): raise ValueError('device policy')
        if sum(len(t.data_json or '') for t in self.tasks)>1_500_000: raise ValueError('campaign data cap')
        if self.budget*len(self.tasks)>16384: raise ValueError('campaign proposal cap')

    def wire(self): return json.loads(canonical(asdict(self)))

    def contract(self): return {**self.wire(),'tasks':[t.contract() for t in self.tasks]}

    @classmethod
    def from_json(cls,raw):
        if type(raw) is not str or len(raw)>2000000: raise ValueError('campaign size')
        try:
            d=json.loads(raw);d['tasks']=tuple(Task(**v) for v in d['tasks']);return cls(**d)
        except (TypeError,KeyError,RecursionError) as exc: raise ValueError('campaign format') from exc


def _contract(campaign):
    root=Path(__file__).parent
    # Existing checkpoint modules remain unchanged; bind all canonical source
    # files to prevent resuming a campaign under silently changed semantics.
    return {'schema':'omega-campaign-v1','campaign':campaign.contract(),'python':list(sys.version_info[:3]),'numpy':np.__version__,
            'runtime':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob('*.py'))}}


def _perform(task,campaign,remaining):
    if task.domain=='scheduler':
        # Each generation creates at most islands*workers proposals. Keep both
        # count and synthetic credit budgets within the campaign allocation.
        islands=2 if campaign.budget>=4 else 1;workers=2 if campaign.budget>=4 else 1
        cfg=Config(seed=task.seed,generations=min(8,campaign.budget//(islands*workers)),islands=islands,workers=workers,budget=campaign.budget)
        r=asyncio.run(run(cfg))
        if r['attempts']>campaign.budget or r['spent']>campaign.budget:raise RuntimeError('scheduler budget mismatch')
        return r,0
    if task.domain in science.DOMAINS:
        d=science.fixture(task.domain,seed=task.seed) if task.data_json is None else science.Data.from_json(task.data_json)
        return science.discover(d,budget=campaign.budget),0
    if task.domain=='bits':
        if task.data_json is not None: train,test=polyglot.parse_dataset(task.data_json)
        else:
            rng=random.Random(task.seed); coords=[]; seen=set()
            while len(coords)<64:
                xy=rng.randrange(65536),rng.randrange(65536)
                if xy not in seen: seen.add(xy);coords.append(xy)
            rows=tuple((x,y,((x+y)^y)&65535) for x,y in coords);train,test=rows[:32],rows[32:]
        return polyglot.evolve(train,test,seed=task.seed,budget=campaign.budget),0
    data=neuro_symbolic.fixture('smooth',seed=task.seed) if task.data_json is None else neuro_symbolic.Split.from_json(task.data_json)
    # A zero remaining neural budget admits symbolic-only (one work unit still
    # cannot admit a neural model for this fixed fixture).
    plan=experiments.design(data,seed=task.seed,budget=campaign.budget,epochs=campaign.epochs,work_cap=max(1,remaining),training_backend=campaign.training_backend)
    policy=campaign.inference_backend
    router=Router(probe(enable_torch=policy in ("torch","npu"),enable_npu=policy=="npu",enable_qnn=policy=="qnn"))
    result=experiments.execute(plan,data,router=router)
    return result,result['training_work']


def run_campaign(campaign:Campaign, *, checkpoint:CheckpointStore|None=None,memory:GraphMemory|None=None,resume=False,stop_after=None):
    if not isinstance(campaign,Campaign) or type(resume) is not bool or (resume and checkpoint is None) or (checkpoint is not None and not isinstance(checkpoint,CheckpointStore)) or (memory is not None and not isinstance(memory,GraphMemory)):
        raise ValueError('invalid campaign services')
    target=len(campaign.tasks) if stop_after is None else stop_after
    if type(target) is not int or not 1<=target<=len(campaign.tasks): raise ValueError('invalid stop target')
    contract=_contract(campaign); identity=hashlib.sha256(canonical(contract).encode()).hexdigest()
    records=[]; used=0; completed=0
    if resume:
        completed,state=checkpoint.load()
        if state.get('contract')!=contract or not 0<=completed<=target: raise CheckpointError('campaign contract mismatch')
        try:
            records=state['records'];used=state['work_used']
            if type(records) is not list or len(records)!=completed or type(used) is not int or not 0<=used<=campaign.work_cap or sum(r['training_work'] for r in records)!=used: raise ValueError('invalid progress')
            for i,r in enumerate(records):
                if r['task']!=campaign.tasks[i].contract() or r['index']!=i or r['campaign_id']!=identity: raise ValueError('invalid task order')
        except (TypeError,KeyError,ValueError,IndexError) as exc: raise CheckpointError('invalid campaign state') from exc
    elif checkpoint is not None: checkpoint.initialize({'contract':contract,'records':records,'work_used':0})

    def publish(record):
        if memory is not None:
            memory.record_experiment({'campaign':identity,'index':record['index'],'task':record['task']},record,title=f"campaign experiment plan {record['task']['domain']}",result_text=f"campaign result {record['task']['domain']} evidence and validation")

    # The checkpoint is the source of truth. Commit before publishing; replay
    # repairs an interrupted graph write via content-addressed idempotency.
    for record in records: publish(record)
    for i in range(completed,target):
        task=campaign.tasks[i]
        result,work=_perform(task,campaign,campaign.work_cap-used)
        if type(work) is not int or not 0<=work<=campaign.work_cap-used: raise RuntimeError('work accounting mismatch')
        used+=work; record={'campaign_id':identity,'index':i,'task':task.contract(),'training_work':work,'result':result}
        # Normalize tuples before both persistence and returning for exact replay.
        record=json.loads(canonical(record));records.append(record)
        if checkpoint is not None: checkpoint.save(i+1,{'contract':contract,'records':records,'work_used':used})
        publish(record)
    return {'schema':'omega-campaign-v1','campaign_id':identity,'completed':target,'planned':len(campaign.tasks),'work_used':used,'work_cap':campaign.work_cap,'proposal_cap':campaign.budget*len(campaign.tasks),'records':records}


def verify_campaign(campaign,report):
    """Offline replay, with the same device policy and numerical runtime."""
    try:
        completed=report['completed']
        return canonical(run_campaign(campaign,stop_after=completed))==canonical(report)
    except (ValueError,TypeError,KeyError,RuntimeError,OverflowError):return False


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--domains',nargs='+',choices=TASKS,default=list(TASKS));p.add_argument('--seed',type=int,default=42);p.add_argument('--budget',type=int,default=128);p.add_argument('--epochs',type=int,default=100);p.add_argument('--work-cap',type=int,default=50_000_000);p.add_argument('--training-backend',choices=('numpy',*TARGETS),default='numpy');p.add_argument('--inference-backend',choices=('cpu','torch','npu','qnn'),default='cpu');p.add_argument('--campaign',type=Path);p.add_argument('--verify-report',type=Path);p.add_argument('--checkpoint',type=Path);p.add_argument('--key-file',type=Path);p.add_argument('--memory',type=Path);p.add_argument('--memory-key',type=Path);p.add_argument('--tenant',default='research');p.add_argument('--resume',action='store_true');p.add_argument('--stop-after',type=int);a=p.parse_args()
    if bool(a.checkpoint)!=bool(a.key_file) or bool(a.memory)!=bool(a.memory_key): p.error('store and key required together')
    if a.campaign:
        with a.campaign.open(encoding='utf-8') as f: c=Campaign.from_json(f.read(2000001))
    else: c=Campaign(tuple(Task(d,a.seed+i) for i,d in enumerate(a.domains)),a.budget,a.epochs,a.work_cap,a.training_backend,a.inference_backend)
    if a.verify_report:
        with a.verify_report.open(encoding="utf-8") as f: r=json.loads(f.read(4_000_001))
        if not verify_campaign(c,r): raise SystemExit("campaign verification failed")
        print("verified");return
    def key(path):
        with path.open('rb') as f: value=f.read(4097)
        if not 32<=len(value)<=4096: raise ValueError('key length')
        return value
    ck=CheckpointStore(a.checkpoint,key(a.key_file)) if a.checkpoint else None
    mem=GraphMemory(a.memory,key(a.memory_key),a.tenant) if a.memory else None
    print(json.dumps(run_campaign(c,checkpoint=ck,memory=mem,resume=a.resume,stop_after=a.stop_after),indent=2,allow_nan=False))


if __name__=='__main__': main()
