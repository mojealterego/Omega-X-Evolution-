"""Durable expansion of typed memory programs with a learned corpus projection.

A campaign can run in bounded transactions. Its final test is not used for
candidate selection, and seals the ledger. No arbitrary generated host code.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
from dataclasses import asdict
from .architecture import Case
from .architecture_synthesis import Plan,SynthesizedIndex,_wire
from .checkpoint import CheckpointStore
from .graph_memory import canonical,tokens
from .infrastructure import _lock

LEAVES=tuple((x,) for x in ('lex','assoc','hyper','latent1','latent2','latent4','latent8'))


def _hash(x):return hashlib.sha256(canonical(x).encode()).hexdigest()


class Search:
    def __init__(self,path,key,index,train,validation,test,*,budget=1024,work_cap=100_000_000,create=False):
        import numpy as np
        if not isinstance(index,SynthesizedIndex) or type(budget) is not int or not 8<=budget<=8192 or type(work_cap) is not int or not 1000<=work_cap<=200_000_000:raise ValueError('synthesis limits')
        seen=set()
        for group in (train,validation,test):
            if type(group) is not tuple or not 1<=len(group)<=32:raise ValueError('query split bounds')
            for c in group:
                if not isinstance(c,Case) or c.target not in index.nodes:raise ValueError('case binding')
                sig=tuple(sorted(tokens(c.query)))
                if sig in seen:raise ValueError('query leakage')
                seen.add(sig)
        if type(create) is not bool:raise ValueError('create mode')
        self.path=Path(path);self.store=CheckpointStore(path,key);self.index=index;self.train=train;self.validation=validation;self.test=test;self.budget=budget;self.work_cap=work_cap
        root=Path(__file__).parent;self.contract=_hash([index.structure_sha256,[[asdict(c) for c in g] for g in (train,validation,test)],budget,work_cap,list(sys.version_info[:3]),np.__version__,*[hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ('architecture.py','architecture_synthesis.py','architecture_search.py')]])
        if create:self.store.initialize({'contract':self.contract,'evaluations':0,'work':0,'queue':[_wire(t) for t in LEAVES],'seen':[], 'recent':None, 'best':None,'final':None})
        self.inspect()
    def _load(self):
        rev,s=self.store.load()
        if s['contract']!=self.contract:raise ValueError('architecture checkpoint mismatch')
        return rev,s
    def inspect(self):return self._load()[1]
    def _evaluate(self,plan,group):
        work=0;rr=[]
        for c in group:
            rows=self.index.retrieve(plan,c.query);work+=self.index.last_work
            rr.append(next((1/(i+1) for i,r in enumerate(rows) if r['id']==c.target),0.))
        return {'mrr':sum(rr)/len(rr),'work':work}
    @staticmethod
    def _better(a,b):return b is None or (a['train']['mrr'],-a['train']['work'],canonical(a['plan']))>(b['train']['mrr'],-b['train']['work'],canonical(b['plan']))
    def step(self,count=64):
        if type(count) is not int or not 1<=count<=256:raise ValueError('transaction budget')
        with _lock(self.path):
            rev,s=self._load()
            if s['final'] is not None:raise ValueError('search sealed by test evaluation')
            seen=set(s['seen']);queued={_hash(t) for t in s['queue']};left=min(count,self.budget-s['evaluations'])
            while left and s['queue']:
                raw=s['queue'].pop(0);ident=_hash(raw);queued.discard(ident)
                if ident in seen:continue
                plan=Plan.from_json(raw);measurement=self._evaluate(plan,self.train)
                if s['work']+measurement['work']>self.work_cap:raise ValueError('architecture evaluation work exhausted')
                s['work']+=measurement['work'];s['evaluations']+=1;left-=1;seen.add(ident);row={'plan':raw,'train':measurement}
                if self._better(row,s['best']):s['best']=row
                # Expand every valid candidate, not just the incumbent; derive
                # compositions recursively and retain deterministic search order.
                tree=plan.tree
                children=[('prop',tree),('square',tree)]
                for leaf in LEAVES:
                    children.extend((op,tree,leaf) for op in ('add','mul','max'))
                # Periodic crossover joins two previously evaluated non-leaf
                # trees. Insert a bounded number near the head without starving
                # ordinary breadth expansion. Persist the parent across restarts.
                previous=s['recent']
                if len(tree)>1:
                    s['recent']=raw
                    if previous is not None and s['evaluations']%8==0:
                        other=Plan.from_json(previous).tree
                        for op in ('add','mul','max'):
                            try:p=Plan((op,tree,other))
                            except ValueError:continue
                            v=_wire(p.tree);h=_hash(v)
                            if len(s['queue'])<8192 and h not in seen and h not in queued:
                                s['queue'].insert(min(16,len(s['queue'])),v);queued.add(h)
                for child in children:
                    if len(s['queue'])>=8192:break
                    try:p=Plan(child)
                    except ValueError:continue
                    v=_wire(p.tree);h=_hash(v)
                    if h not in seen and h not in queued:s['queue'].append(v);queued.add(h)
            s['seen']=sorted(seen);self.store.save(rev+1,s);return {'evaluations':s['evaluations'],'work':s['work'],'frontier':len(s['queue'])}
    def finalize(self):
        with _lock(self.path):
            rev,s=self._load()
            if s['final'] is not None:return s['final']
            if s['best'] is None:raise ValueError('no evaluated candidates')
            baseline=Plan(('lex',));candidate=Plan.from_json(s['best']['plan']);bv=self._evaluate(baseline,self.validation);cv=self._evaluate(candidate,self.validation);promoted=(cv['mrr'],-cv['work'])>(bv['mrr'],-bv['work']);selected=candidate if promoted else baseline
            # Reserve a conservative upper bound before touching final test.
            if s['work']+bv['work']+cv['work']+4_000_000*len(self.test)>self.work_cap:raise ValueError('insufficient final test budget')
            st=self._evaluate(selected,self.test);bt=self._evaluate(baseline,self.test);s['work']+=bv['work']+cv['work']+st['work']+bt['work']
            s['final']={'schema':'omega-durable-architecture-v1','contract':self.contract,'evaluations':s['evaluations'],'work':s['work'],'selected':_wire(selected.tree),'challenger':_wire(candidate.tree),'promoted':promoted,'validation':cv,'baseline_validation':bv,'test':st,'baseline_test':bt,'test_evaluations':2,'structures':[{'kind':'hypergraph','sha256':self.index.structure_sha256},{'kind':'latent','ranks':[1,2,4,8],'derived_from':self.index.digest}]}
            self.store.save(rev+1,s);return s['final']
