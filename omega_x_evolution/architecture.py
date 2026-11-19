"""Typed synthesis of memory retrieval architectures over authenticated graph snapshots.
Search on train; one validation promotion; final test after selection.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict, dataclass
import hashlib
import itertools
import json
import math
import re
from pathlib import Path
from .graph_memory import GraphMemory, canonical, tokens


@dataclass(frozen=True)
class Case:
    query:str
    target:str
    def __post_init__(self):
        if type(self.query) is not str or not 1<=len(self.query)<=1024 or not tokens(self.query) or type(self.target) is not str or not re.fullmatch('[a-f0-9]{64}',self.target):raise ValueError('query case')


@dataclass(frozen=True)
class Plan:
    lexical:int=1
    associative:int=0
    hops:int=0
    decay:int=1 # integer denominator for propagation
    def __post_init__(self):
        if any(type(x) is not int for x in (self.lexical,self.associative,self.hops,self.decay)) or not (0<=self.lexical<=2 and 0<=self.associative<=2 and self.lexical+self.associative>0 and 0<=self.hops<=2 and 1<=self.decay<=3):raise ValueError('invalid architecture')

    def dag(self):
        nodes=['authenticated_snapshot','query']
        if self.lexical:nodes.append('lexical_index')
        if self.associative:nodes.append('hashed_association')
        nodes+=['rank_fusion']
        if self.hops:nodes+=['provenance_diffusion']*self.hops
        return nodes+['bounded_cited_results']


def vector(text):
    # Stable signed hashed character trigrams; no pretrained model claim.
    v=[0]*128
    for w in sorted(tokens(text)):
        s='^'+w+'$'
        for i in range(len(s)-2):
            h=hashlib.blake2s(s[i:i+3].encode(),digest_size=4).digest();v[int.from_bytes(h[:2],'big')%128]+=1 if h[2]&1 else -1
    norm=math.sqrt(sum(x*x for x in v))
    return tuple(x/norm for x in v) if norm else tuple(v)


class Index:
    def __init__(self,memory):
        if not isinstance(memory,GraphMemory):raise ValueError('authenticated graph required')
        self.nodes,self.adj=memory.snapshot()
        if not 1<=len(self.nodes)<=512 or sum(map(len,self.adj.values()))>4096:raise ValueError('architecture index bounds')
        self.terms={i:tokens(n['text']) for i,n in self.nodes.items()}
        self.vectors={i:vector(n['text']) for i,n in self.nodes.items()}
        self.digest=hashlib.sha256(canonical([self.nodes,self.adj]).encode()).hexdigest()

    def retrieve(self,plan,query,*,limit=8):
        if not isinstance(plan,Plan) or type(query) is not str or not 1<=len(query)<=1024 or type(limit) is not int or not 1<=limit<=32:raise ValueError('retrieval bounds')
        terms=tokens(query);q=vector(query) if plan.associative else ()
        if not terms:self.last_work=0;return []
        best={};work=0
        for i in self.nodes:
            lexical=len(terms&self.terms[i])/len(terms) if plan.lexical else 0.
            assoc=max(0.,sum(x*y for x,y in zip(q,self.vectors[i]))) if plan.associative else 0.
            score=(plan.lexical*lexical+plan.associative*assoc)/(plan.lexical+plan.associative)
            work+=int(bool(plan.lexical))+128*int(bool(plan.associative))
            if score>0:best[i]=(score,[i],[])
        frontier=dict(best)
        for _ in range(plan.hops):
            fresh={}
            for i,(s,path,rels) in sorted(frontier.items()):
                for j,r,d in sorted(self.adj[i]):
                    work+=1
                    if j in path:continue
                    value=s/(plan.decay+1);old=best.get(j)
                    if old is None or value>old[0]:
                        nextrow=(value,path+[j],rels+[{'relation':r,'direction':d}]);best[j]=nextrow;fresh[j]=nextrow
            frontier=fresh
        self.last_work=work
        return [{'id':i,**self.nodes[i],'score':s,'path':path,'relations':rels} for i,(s,path,rels) in sorted(best.items(),key=lambda x:(-x[1][0],x[0]))[:limit]]


def _evaluate(index,plan,cases):
    scores=[];work=0
    for c in cases:
        rows=index.retrieve(plan,c.query);work+=index.last_work
        scores.append(next((1/(i+1) for i,row in enumerate(rows) if row['id']==c.target),0.))
    return {'mrr':sum(scores)/len(cases),'work':work,'queries':len(cases)}


def synthesize(index,train,validation,test,*,budget=24):
    groups=(train,validation,test)
    if type(budget) is not int or not 2<=budget<=56 or any(type(g) is not tuple or not 1<=len(g)<=64 for g in groups):raise ValueError('architecture search budget')
    seen=set()
    for c in itertools.chain(*groups):
        if not isinstance(c,Case) or c.target not in index.nodes:raise ValueError('unknown target or invalid case')
        signature=tuple(sorted(tokens(c.query)))
        if signature in seen:raise ValueError('overlapping query features')
        seen.add(signature)
    if (budget*len(train)+2*len(validation)+2*len(test))*len(index.nodes)>200000:raise ValueError('search work cap')
    baseline=Plan();candidates=[baseline]
    for h,l,a,d in itertools.product(range(3),range(3),range(3),range(1,4)):
        if l+a and (h or d==1):
            p=Plan(l,a,h,d)
            if p!=baseline:candidates.append(p)
    candidates=candidates[:budget]
    results=[(p,_evaluate(index,p,train)) for p in candidates]
    challenger,training=max(results,key=lambda r:(r[1]['mrr'],-r[1]['work']))
    bv=_evaluate(index,baseline,validation);cv=_evaluate(index,challenger,validation)
    promoted=cv['mrr']>bv['mrr'] or (cv['mrr']==bv['mrr'] and cv['work']<bv['work'])
    selected=challenger if promoted else baseline
    return {'schema':'omega-memory-architecture-v1','snapshot_sha256':index.digest,'evaluations':len(results),'selected':asdict(selected),'dag':selected.dag(),
            'challenger':asdict(challenger),'train':training,'validation':cv,'baseline_validation':bv,'promoted':promoted,
            'test':_evaluate(index,selected,test),'baseline_test':_evaluate(index,baseline,test),
            'search':[{'plan':asdict(p),**r} for p,r in results]}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',required=True,type=Path);p.add_argument('--key-file',required=True,type=Path);p.add_argument('--tenant',required=True);p.add_argument('--cases',required=True,type=Path);p.add_argument('--budget',type=int,default=24);a=p.parse_args()
    with a.key_file.open('rb') as f:key=f.read(4097)
    with a.cases.open('rb') as f:raw=f.read(262145)
    if len(raw)>262144:raise ValueError('case file cap')
    data=json.loads(raw);index=Index(GraphMemory(a.db,key,a.tenant))
    print(json.dumps(synthesize(index,*(tuple(Case(**r) for r in data[g]) for g in ('train','validation','test')),budget=a.budget),indent=2))


if __name__=='__main__':main()
