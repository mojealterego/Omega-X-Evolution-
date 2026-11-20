"""Resumable, exhaustive-by-size search of the supported typed score grammar.

An ordinal cursor replaces the frontier and the visited set. The campaign has
no 8192-evaluation lifetime cap. Every transaction has explicit work and count
limits, and every individual plan retains the original safe size/depth limits.
This does not generate arbitrary primitives or executable host code.
"""
from __future__ import annotations
from dataclasses import asdict
from functools import lru_cache
import hashlib
from pathlib import Path
import sys

from .architecture import Case
from .architecture_search import LEAVES, Search, _hash
from .architecture_synthesis import Plan, SynthesizedIndex, _wire, UNARY_OPS, BINARY_OPS
from .checkpoint import CheckpointStore
from .graph_memory import tokens
from .infrastructure import _lock

MAX_SIZE = 255
MAX_DEPTH = 16
UNARY = UNARY_OPS
BINARY = BINARY_OPS
QUERY_WORK = 4_000_000  # reserve includes one bounded operation beyond retrieval cap
MAX_STEP_WORK = 200_000_000


@lru_cache(maxsize=(MAX_SIZE + 1) * (MAX_DEPTH + 1))
def _count(size: int, depth: int) -> int:
    if size < 1 or depth < 0 or size > min(MAX_SIZE, 2**(depth+1)-1):
        return 0
    if size == 1:
        return len(LEAVES)
    if depth == 0:
        return 0
    return (len(UNARY)*_count(size-1, depth-1) + len(BINARY)*sum(
        _count(a,depth-1)*_count(size-1-a,depth-1) for a in range(1,size-1)))


def tree_count(size: int, depth: int) -> int:
    if type(size) is not int or type(depth) is not int or not 1<=size<=MAX_SIZE or not 0<=depth<=MAX_DEPTH:
        raise ValueError('grammar bounds')
    return _count(size,depth)


def tree_at(size: int, depth: int, ordinal: int) -> tuple:
    n = tree_count(size,depth)
    if type(ordinal) is not int or not 0<=ordinal<n:
        raise ValueError('grammar ordinal')
    if size == 1:
        return LEAVES[ordinal]
    unary = _count(size-1,depth-1)
    if ordinal < len(UNARY)*unary:
        op, child = divmod(ordinal,unary)
        return (UNARY[op],tree_at(size-1,depth-1,child))
    ordinal -= len(UNARY)*unary
    for left in range(1,size-1):
        right = size-1-left
        a,b = _count(left,depth-1),_count(right,depth-1)
        span = a*b
        if ordinal < len(BINARY)*span:
            op,offset = divmod(ordinal,span)
            i,j = divmod(offset,b)
            return (BINARY[op],tree_at(left,depth-1,i),tree_at(right,depth-1,j))
        ordinal -= len(BINARY)*span
    raise RuntimeError('unranking inconsistency')


class StreamingSearch:
    def __init__(self,path,key,index,train,validation,test,*,create=False):
        import numpy as np
        if not isinstance(index,SynthesizedIndex) or type(create) is not bool:
            raise ValueError('streaming search configuration')
        seen=set()
        for group in (train,validation,test):
            if type(group) is not tuple or not 1<=len(group)<=32:
                raise ValueError('query split bounds')
            for c in group:
                if not isinstance(c,Case) or c.target not in index.nodes:
                    raise ValueError('case binding')
                sig=tuple(sorted(tokens(c.query)))
                if sig in seen:raise ValueError('query leakage')
                seen.add(sig)
        self.path=Path(path).absolute();self.store=CheckpointStore(self.path,key)
        self.index=index;self.train=train;self.validation=validation;self.test=test
        root=Path(__file__).parent
        self.contract=_hash(['omega-streaming-synthesis-v1',index.structure_sha256,
            [[asdict(c) for c in group] for group in (train,validation,test)],
            list(sys.version_info[:3]),np.__version__,*[hashlib.sha256((root/name).read_bytes()).hexdigest()
                for name in ('architecture.py','architecture_synthesis.py','architecture_search.py','streaming_synthesis.py')]])
        if create:
            self.store.initialize({'contract':self.contract,'cursor':[1,0],'evaluations':0,'rejected':0,
                'work':0,'best':None,'final':None})
        self.inspect()

    def _load(self):
        revision,s=self.store.load()
        if s.get('contract')!=self.contract:raise ValueError('streaming search checkpoint mismatch')
        size,ordinal=s['cursor']
        if not (size==MAX_SIZE+1 and ordinal==0 or 1<=size<=MAX_SIZE and 0<=ordinal<tree_count(size,MAX_DEPTH)):
            raise ValueError('streaming search cursor')
        return revision,s

    def inspect(self):
        return self._load()[1]

    def _evaluate(self,plan,group):
        # The real index performs bounded retrieval. Reject only its explicit
        # work-limit error; unrelated errors abort the entire transaction.
        work=0;rr=[]
        for c in group:
            try:rows=self.index.retrieve(plan,c.query)
            except ValueError as exc:
                if str(exc)!='retrieval work cap':raise
                if not 0<=self.index.last_work<=QUERY_WORK:raise RuntimeError('retrieval accounting exceeded reservation')
                return None, work+self.index.last_work
            if not 0<=self.index.last_work<=QUERY_WORK:raise RuntimeError('retrieval accounting exceeded reservation')
            work+=self.index.last_work
            rr.append(next((1/(i+1) for i,row in enumerate(rows) if row['id']==c.target),0.))
        return {'mrr':sum(rr)/len(rr),'work':work},work

    def step(self,count=64,*,work_cap=MAX_STEP_WORK):
        reserve=QUERY_WORK*len(self.train)
        if type(count) is not int or not 1<=count<=256 or type(work_cap) is not int or not reserve<=work_cap<=MAX_STEP_WORK:
            raise ValueError('streaming transaction limits')
        with _lock(self.path):
            rev,s=self._load()
            if s['final'] is not None:raise ValueError('search sealed by test evaluation')
            size,ordinal=s['cursor'];charged=0;completed=0
            while completed<count and size<=MAX_SIZE and charged+reserve<=work_cap:
                plan=Plan(tree_at(size,MAX_DEPTH,ordinal));measurement,work=self._evaluate(plan,self.train)
                charged+=work;s['evaluations']+=1;completed+=1
                if measurement is None:s['rejected']+=1
                else:
                    row={'plan':_wire(plan.tree),'train':measurement}
                    if Search._better(row,s['best']):s['best']=row
                ordinal+=1
                if ordinal==tree_count(size,MAX_DEPTH):
                    size+=1;ordinal=0
                    while size<=MAX_SIZE and not tree_count(size,MAX_DEPTH):size+=1
            s['cursor']=[size,ordinal];s['work']+=charged
            if completed:self.store.save(rev+1,s)
            return {'completed':completed,'evaluations':s['evaluations'],'work':charged,'cursor':s['cursor'],'exhausted':size>MAX_SIZE}

    def finalize(self):
        with _lock(self.path):
            rev,s=self._load()
            if s['final'] is not None:return s['final']
            if s['best'] is None:raise ValueError('no qualified candidates')
            baseline=Plan(('lex',));challenger=Plan.from_json(s['best']['plan'])
            bv,bw=self._evaluate(baseline,self.validation);cv,cw=self._evaluate(challenger,self.validation)
            if bv is None:raise ValueError('baseline exceeds validation work cap')
            promoted=cv is not None and (cv['mrr'],-cv['work'])>(bv['mrr'],-bv['work'])
            selected=challenger if promoted else baseline
            st,sw=self._evaluate(selected,self.test);bt,tw=self._evaluate(baseline,self.test)
            s['work']+=bw+cw+sw+tw
            s['final']={'schema':'omega-streaming-architecture-v1','contract':self.contract,
                'evaluations':s['evaluations'],'rejected':s['rejected'],'work':s['work'],'cursor':s['cursor'],
                'selected':_wire(selected.tree),'challenger':_wire(challenger.tree),'promoted':promoted,
                'validation':cv,'baseline_validation':bv,'test':st,'baseline_test':bt,'test_evaluations':2,
                'test_qualified':st is not None and bt is not None}
            self.store.save(rev+1,s);return s['final']
