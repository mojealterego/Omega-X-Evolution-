"""Budgeted online LoRA for the v32 contextual mutation router.
Frozen base, independently qualified v25 trajectories, separate promotion and
retention sets, durable charged reservations and reversible adapter selection.
"""
from __future__ import annotations
import argparse
import ast
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import random
import re
import numpy as np
from .annealed import ACTIONS, propose
from .checkpoint import CheckpointStore
from .engine import Cascade, Expression, BASELINE, apply_patch, score
from .graph_memory import canonical
from .holographic import trajectory, validate
from .safety_synthesis import prove
from .swarm import NeuralRouter


def _digest(v):return hashlib.sha256(canonical(v).encode()).hexdigest()


@dataclass(frozen=True)
class Policy:
    seed:int=42
    rank:int=2
    steps:int=80
    max_updates:int=4
    def __post_init__(self):
        if any(type(x) is not int for x in (self.seed,self.rank,self.steps,self.max_updates)) or not (0<=self.seed<2**32 and 1<=self.rank<=2 and 1<=self.steps<=400 and 1<=self.max_updates<=16):raise ValueError('plasticity policy')
    @property
    def base_digest(self):
        r=NeuralRouter(self.seed);return _digest([r.w,r.v])
    def initial(self):
        rng=np.random.default_rng(self.seed)
        return {'a':rng.uniform(-.1,.1,(6,self.rank)).tolist(),'b':np.zeros((self.rank,ACTIONS)).tolist()}


def _weights(policy,adapter):
    if not isinstance(policy,Policy) or type(adapter) is not dict or set(adapter)!={'a','b'}:raise ValueError('adapter schema')
    if any(type(m) is not list or any(type(row) is not list or any(type(x) not in (int,float) for x in row) for row in m) for m in adapter.values()):raise ValueError('adapter type')
    a,b=(np.asarray(adapter[k],dtype=np.float64) for k in ('a','b'))
    if a.shape!=(6,policy.rank) or b.shape!=(policy.rank,ACTIONS) or any(not np.isfinite(x).all() or np.max(np.abs(x))>10 for x in (a,b)):raise ValueError('adapter bounds')
    return a,b


def _assessment(code):
    cert=prove(code);r=Cascade(42).evaluate(code) if cert['proved'] else None
    quality=score(r.metrics) if r is not None and r.stage==3 and r.metrics[3]==1. else None
    return quality, r.stage if r is not None else 0

def _qualified(code):return _assessment(code)[0]


def validate_record(row):
    r=validate(row)
    if any(type(r[k]) not in (int,float) for k in ('quality','baseline','reward')):raise ValueError('trajectory numeric type')
    if r['action']>=ACTIONS or r['proposal_seed'] is None:raise ValueError('replayable v25 trajectory required')
    base=_qualified(r['parent']);child,stage=_assessment(r['child'])
    if base is None or r['baseline']!=base or r['accepted'] is not (child is not None) or r['quality']!=(child if child is not None else 0.):raise ValueError('trajectory qualification mismatch')
    if r['stage']!=stage:raise ValueError('trajectory stage mismatch')
    return r


def _prepare(groups):
    seen=set();contexts=set();out=[]
    for g in groups:
        if type(g) is not tuple or not 1<=len(g)<=64:raise ValueError('trajectory split bounds')
        rows=tuple(validate_record(r) for r in g);local=set()
        for r in rows:
            key=(r['island'],r['id']);ctx=ast.dump(Expression(r['parent']).tree,include_attributes=False)
            if key in seen or ctx in contexts:raise ValueError('trajectory split overlap')
            seen.add(key);local.add(ctx)
        contexts.update(local);out.append(rows)
    return out


def _features(policy,rows):
    router=NeuralRouter(policy.seed);w=np.array(router.w);v=np.array(router.v).T
    ents=[Expression(r['parent']) for r in rows]
    x=np.array([[1.,e.count/100,e.operations/100] for e in ents]);h=np.tanh(x@w.T)
    act=np.array([r['action'] for r in rows]);target=np.array([r['reward'] for r in rows]);return h,v,act,target


def _loss(features,a,b):
    h,v,act,target=features
    err=(h@(v+a@b))[np.arange(len(act)),act]-target
    return float(np.mean(err**2))


def fit_adapter(policy,train,validation,retention,*,active=None):
    if not isinstance(policy,Policy):raise ValueError('policy required')
    train,validation,retention=_prepare((train,validation,retention))
    active=policy.initial() if active is None else active
    a,b=_weights(policy,active);a=a.copy();b=b.copy()
    start=_weights(policy,active);original=_weights(policy,policy.initial())
    tr,va,re=(_features(policy,g) for g in (train,validation,retention))
    before=_loss(tr,*start);vb=_loss(va,*start);rb=_loss(re,*start);root_ret=_loss(re,*original)
    h,v,act,target=tr
    # Full batch gradient on the selected action reward; base v and hidden w never updated.
    for _ in range(policy.steps):
        err=(h@(v+a@b))[np.arange(len(act)),act]-target
        dy=np.zeros((len(act),ACTIONS));dy[np.arange(len(act)),act]=2*err/len(act)
        dw=h.T@dy;ga=dw@b.T;gb=a.T@dw
        a-=.5*np.clip(ga,-1,1);b-=.5*np.clip(gb,-1,1)
    candidate={'a':a.tolist(),'b':b.tolist()};_weights(policy,candidate)
    ta,vc,rc=_loss(tr,a,b),_loss(va,a,b),_loss(re,a,b)
    promote=vc<vb-1e-9 and rc<=min(rb,root_ret)+.002
    return {'schema':'omega-router-lora-v1','base_sha256':policy.base_digest,'rank':policy.rank,'steps':policy.steps,'trainable_parameters':int(a.size+b.size),'frozen_parameters':54,'train_before':before,'train_after':ta,'validation_before':vb,'validation_candidate':vc,'retention_before':rb,'retention_candidate':rc,'retention_base':root_ret,'selected_validation':vc if promote else vb,'promoted':promote,'adapter':candidate if promote else active,'candidate_sha256':_digest(candidate),'split_sha256':_digest([train,validation,retention])}


def evaluate_adapter(policy,adapter,rows):
    """Final offline test; never called from training or promotion."""
    if type(rows) is not tuple or not 1<=len(rows)<=64:raise ValueError('test bounds')
    rows=tuple(validate_record(r) for r in rows);f=_features(policy,rows)
    return {'base_mse':_loss(f,*_weights(policy,policy.initial())),'adapter_mse':_loss(f,*_weights(policy,adapter)),'rows':len(rows)}


def choose(policy,adapter,parent,seed):
    """Adapter affects proposals only; actual candidate must pass fixed gates."""
    if type(seed) is not int or not 0<=seed<2**32:raise ValueError('proposal seed')
    a,b=_weights(policy,adapter);router=NeuralRouter(policy.seed);e=Expression(parent)
    h=np.tanh(np.array(router.w)@np.array([1.,e.count/100,e.operations/100]));v=h@(np.array(router.v).T+a@b);rng=random.Random(seed)
    action=rng.randrange(ACTIONS) if rng.random()<.2 else int(np.argmax(v));s=rng.randrange(2**32)
    code=apply_patch(parent,propose(parent,action,s));quality,stage=_assessment(code);baseline=_qualified(parent)
    if baseline is None:raise ValueError('unqualified parent')
    return trajectory(f'plastic-{seed}',0,'parent',parent,code,action,quality is not None,quality if quality is not None else 0.,baseline,stage,s)


def collect_store(store, islands):
    """Read a bounded set of authenticated v25 snapshots; never mutate them.
    The fixed seed-42 evaluator requalifies each sample; incompatible dynamic
    challenges, measured performance rejections and missing seeds are excluded.
    """
    from .cluster import Store
    if not isinstance(store,Store) or store.cfg.seed!=42 or not store.cfg.annealed or not store.cfg.formal_safety or store.cfg.policy is not None:raise ValueError('compatible seed-42 formal annealed store required')
    if type(islands) is not tuple or not 1<=len(islands)<=16 or any(type(i) is not int or not 0<=i<store.cfg.islands for i in islands) or len(set(islands))!=len(islands):raise ValueError('island sample bounds')
    store.open();rows=[];excluded=0;revisions=[]
    for i in islands:
        rev,state=store.read(i);revisions.append([i,rev])
        for raw in state['trajectories']:
            try:r=validate_record(raw)
            except ValueError:excluded+=1;continue
            if len(rows)<64:rows.append(r)
            else:excluded+=1
    return tuple(rows),{'revisions':revisions,'accepted':len(rows),'excluded':excluded}


def fixture(seed=42,*,groups=3):
    """Actual qualified proposal trajectories, disjoint parent programs per split."""
    if type(seed) is not int or not 0<=seed<2**32 or type(groups) is not int or not 3<=groups<=4:raise ValueError('fixture bounds')
    rng=random.Random(seed);out=[]
    for g in range(groups):
        rows=[]
        for i in range(6):
            parent=f'-(x+y+{g+1}.{i+1})' if i%2==0 else f'-(x+y+{g+1}.{i+1}*abs(x-y))'
            base=_qualified(parent)
            for action in range(ACTIONS):
                s=rng.randrange(2**32);code=apply_patch(parent,propose(parent,action,s));q,stage=_assessment(code)
                rows.append(trajectory(f'{g}-{i}-{action}',0,'seed',parent,code,action,q is not None,q if q is not None else 0.,base,stage,s))
        out.append(tuple(rows))
    return tuple(out)


@contextmanager
def _exclusive(path):
    # POSIX local disk advisory locking; keys and directory operator-controlled.
    import fcntl
    fd=os.open(str(path)+'.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:os.close(fd)


class Plasticity:
    def __init__(self,path,key,policy,*,create=False):
        if not isinstance(policy,Policy):raise ValueError('policy required')
        self.path=Path(path);self.store=CheckpointStore(path,key);self.policy=policy
        root=Path(__file__).parent
        self.contract=_digest([asdict(policy),policy.base_digest,np.__version__,*[hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ('plasticity.py','swarm.py','engine.py','annealed.py','holographic.py','safety_synthesis.py','checkpoint.py')]])
        if create:self.store.initialize({'contract':self.contract,'initial':policy.initial(),'active':policy.initial(),'used_steps':0,'updates':{},'rollbacks':0})
        self.inspect()
    def _load(self):
        rev,state=self.store.load()
        if state['contract']!=self.contract:raise ValueError('plasticity contract mismatch')
        _weights(self.policy,state['active']);return rev,state
    def inspect(self):return self._load()[1]
    def update(self,train,validation,retention,*,authorized=False,request_id='update'):
        if authorized is not True:raise PermissionError('explicit training authorization required')
        if type(request_id) is not str or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',request_id):raise ValueError('request id')
        groups=_prepare((train,validation,retention));ident=_digest(groups)
        with _exclusive(self.path):
            rev,s=self._load();rows=s['updates']
            # A previous process died after reserving work. Charge it and do not retry implicitly.
            pending=[r for r in rows.values() if r['status']=='reserved']
            if pending:
                for r in pending:r['status']='interrupted'
                rev+=1;self.store.save(rev,s)
            if request_id in rows:
                row=rows[request_id]
                if row['input']!=ident:raise ValueError('conflicting update request')
                if row['status']!='complete':raise ValueError('previous update interrupted; reservation consumed')
                return row['report']
            if len(rows)>=self.policy.max_updates:raise ValueError('training budget exhausted')
            rows[request_id]={'input':ident,'status':'reserved'};s['used_steps']+=self.policy.steps
            rev+=1;self.store.save(rev,s)
            report=fit_adapter(self.policy,*groups,active=s['active'])
            s['active']=report['adapter'];rows[request_id].update(status='complete',report=report);self.store.save(rev+1,s)
            return report
    def rollback(self,*,authorized=False):
        if authorized is not True:raise PermissionError('rollback authorization required')
        with _exclusive(self.path):
            rev,s=self._load();s['active']=s['initial'];s['rollbacks']+=1;self.store.save(rev+1,s)
            return s


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seed',type=int,default=42);p.add_argument('--rank',type=int,default=2);p.add_argument('--steps',type=int,default=80);p.add_argument('--max-updates',type=int,default=4);p.add_argument('--authorize-training',action='store_true');p.add_argument('--db',type=Path);p.add_argument('--key-file',type=Path);p.add_argument('--dataset',type=Path);p.add_argument('--request-id',default='update');p.add_argument('--create',action='store_true');p.add_argument('--rollback',action='store_true');p.add_argument('--inspect',action='store_true');a=p.parse_args()
    policy=Policy(a.seed,a.rank,a.steps,a.max_updates)
    if not a.inspect and not a.authorize_training:p.error('explicit training authorization required')
    if a.db:
        if not a.key_file:p.error('key file required')
        if a.create and not a.authorize_training:p.error('explicit creation authorization required')
        with a.key_file.open('rb') as f:key=f.read(4097)
        if not 32<=len(key)<=4096:raise ValueError('key size')
        store=Plasticity(a.db,key,policy,create=a.create)
        if a.inspect:result=store.inspect()
        elif a.rollback:result=store.rollback(authorized=a.authorize_training)
        else:
            if not a.dataset:p.error('explicit trajectory dataset required for durable update')
            with a.dataset.open('rb') as f:raw=f.read(1048577)
            if len(raw)>1048576:raise ValueError('dataset cap')
            data=json.loads(raw)
            if type(data) is not dict or set(data)!={'train','validation','retention'}:raise ValueError('dataset schema')
            result=store.update(*(tuple(data[k]) for k in ('train','validation','retention')),authorized=a.authorize_training,request_id=a.request_id)
    else:
        if any((a.key_file,a.dataset,a.create,a.rollback,a.inspect)):p.error('durable options require db')
        t,v,r,test=fixture(a.seed,groups=4)
        result=fit_adapter(policy,t,v,r);result['test']=evaluate_adapter(policy,result['adapter'],test);result['proposal']=choose(policy,result['adapter'],BASELINE,a.seed)
    print(json.dumps(result,indent=2,allow_nan=False))

if __name__=='__main__':main()
