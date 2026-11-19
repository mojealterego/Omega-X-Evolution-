"""Bounded context-keyed modern Hopfield retrieval over validated trajectories.

Feature hashing is stable across processes; quantized keys are not executable.
Original records retain provenance and signed cluster snapshots authenticate them.
"""
from __future__ import annotations
import ast
import hashlib
import math
import re
from .engine import Expression

DIM=128
CAPACITY=64
TRANSFER=8


def trajectory(ident,island,parent_id,parent,child,action,accepted,quality,baseline,stage,proposal_seed=None):
    if (not isinstance(ident,str) or not 1<=len(ident)<=128 or type(island) is not int or not 0<=island<512 or
        not isinstance(parent_id,str) or not 1<=len(parent_id)<=128 or not isinstance(child,str) or len(child)>2048 or
        type(action) is not int or not 0<=action<=6 or type(accepted) is not bool or type(stage) is not int or not 0<=stage<=3 or
        any(type(v) not in (float,int) or not math.isfinite(v) or not 0<=v<=1 for v in (quality,baseline)) or
        (accepted and stage!=3) or (not accepted and quality!=0)):
        raise ValueError('trajectory bounds')
    Expression(parent)
    if accepted:Expression(child)
    if proposal_seed is not None:
        from .annealed import propose
        from .engine import apply_patch
        if type(proposal_seed) is not int or not 0<=proposal_seed<2**32 or action>=6 or apply_patch(parent,propose(parent,action,proposal_seed))!=child:
            raise ValueError('proposal seed mismatch')
    return {'id':ident,'island':island,'parent_id':parent_id,'parent':parent,'child':child,'action':action,
            'accepted':accepted,'quality':quality,'baseline':baseline,'stage':stage,'proposal_seed':proposal_seed,'reward':quality-baseline if accepted else -baseline}


def validate(r):
    if not isinstance(r,dict):raise ValueError('invalid trajectory')
    try: expected=trajectory(r['id'],r['island'],r['parent_id'],r['parent'],r['child'],r['action'],r['accepted'],r['quality'],r['baseline'],r['stage'],r['proposal_seed'])
    except (KeyError,TypeError) as exc:raise ValueError('invalid trajectory') from exc
    if r!=expected:raise ValueError('trajectory integrity')
    return expected


def encode(context):
    e=Expression(context)
    tokens=re.findall(r'[A-Za-z]+|[0-9.]+|[^\s]',context)
    features=['ast:'+type(n).__name__ for n in ast.walk(e.tree)]
    features+=['tok:'+t for t in tokens]+['big:'+a+'|'+b for a,b in zip(tokens,tokens[1:])]
    # Signed int8 feature keys; normalized cosine uses these quantized values.
    vec=[0]*DIM
    for f in features:
        h=hashlib.blake2b(f.encode(),digest_size=8,person=b'omega-holo-v1').digest()
        i=int.from_bytes(h[:4],'big')%DIM;vec[i]+=1 if h[4]&1 else -1
    scale=max(1,max(map(abs,vec)))
    return bytes(round(127*v/scale)&255 for v in vec)


def _cos(a,b):
    a=memoryview(a).cast('b');b=memoryview(b).cast('b')
    n=math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return sum(x*y for x,y in zip(a,b))/n if n else 0.


class Memory:
    def __init__(self,records):
        if len(records)>CAPACITY:raise ValueError('memory capacity')
        unique={}
        for row in records:
            r=validate(row); k=(r['island'],r['id'])
            if k in unique and unique[k]!=r:raise ValueError('conflicting trajectory')
            unique[k]=r
        self.records=tuple(unique.values());self.keys=tuple(encode(r['parent']) for r in self.records)

    def retrieve(self,context,k=3):
        if type(k) is not int or not 1<=k<=CAPACITY:raise ValueError('retrieval limit')
        if not self.records:return []
        q=encode(context); logits=[8*_cos(q,key) for key in self.keys]; peak=max(logits)
        weights=[math.exp(x-peak) for x in logits]; total=sum(weights)
        order=sorted(range(len(weights)),key=lambda i:(-weights[i],self.records[i]['island'],self.records[i]['id']))[:k]
        return [{'record':dict(self.records[i]),'weight':weights[i]/total} for i in order]


def bounded_records(local,foreign):
    # Keep the latest foreign batch and local history; never re-broadcast imports.
    return list(local[-(CAPACITY-len(foreign)):])+list(foreign) if foreign else list(local[-CAPACITY:])
