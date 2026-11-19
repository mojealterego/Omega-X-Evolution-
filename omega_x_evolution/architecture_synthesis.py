"""Data-dependent hypergraph memory and typed score-program synthesis.
No generated source or dynamic imports: plans are bounded pure score trees.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import defaultdict
import hashlib
import itertools
import math
from .architecture import Index, Case, vector
from .graph_memory import canonical, tokens


@dataclass(frozen=True)
class Plan:
    tree: tuple
    def __post_init__(self):
        count=0
        def validate(t,depth):
            nonlocal count
            count+=1
            if type(t) is not tuple or not t or depth>4 or count>15:raise ValueError('score tree bound')
            if t[0] in ('lex','assoc','hyper') and len(t)==1:return
            if t[0] in ('square','prop') and len(t)==2:validate(t[1],depth+1);return
            if t[0] in ('add','mul','max') and len(t)==3:
                validate(t[1],depth+1);validate(t[2],depth+1);return
            raise ValueError('invalid score program')
        validate(self.tree,0)
    @classmethod
    def from_json(cls,value):
        def freeze(v,depth=0):
            if depth>5 or type(v) is not list or not 1<=len(v)<=3 or type(v[0]) is not str:raise ValueError('invalid program encoding')
            return (v[0],*(freeze(x,depth+1) for x in v[1:]))
        return cls(freeze(value))


class SynthesizedIndex(Index):
    def __init__(self,memory):
        super().__init__(memory)
        edges=defaultdict(list)
        for ident,words in sorted(self.terms.items()):
            for word in sorted(words):edges[word].append(ident)
        if sum(map(len,edges.values()))>65536:raise ValueError('hypergraph index cap')
        self.hypergraph=dict(edges)
        self.structure_sha256=hashlib.sha256(canonical([self.digest,self.hypergraph]).encode()).hexdigest()

    def retrieve(self,plan,query,*,limit=8):
        if not isinstance(plan,Plan) or type(query) is not str or not 1<=len(query)<=1024 or type(limit) is not int or not 1<=limit<=32:raise ValueError('retrieval bounds')
        terms=tokens(query); keys=tuple(sorted(self.nodes)); n=len(keys); self.last_work=0
        if not terms:return []
        # Each score carries an auditable set of supporting document ids.
        # Inferred links are separate from the graph's authenticated relations.
        cache={}
        def calc(t):
            if t in cache:return cache[t]
            op=t[0];out={};self.last_work+=n
            if op=='lex':
                out={i:(len(terms&self.terms[i])/len(terms),{i}) for i in keys}
            elif op=='assoc':
                q=vector(query);self.last_work+=128*n
                out={i:(max(0.,sum(a*b for a,b in zip(q,self.vectors[i]))),{i}) for i in keys}
            elif op=='hyper':
                base=calc(('lex',));weights={};evidence={}
                for i,(s,_) in base.items():
                    if s<=0:continue
                    for token in sorted(self.terms[i]):
                        # Penalize frequent terms; no target labels used to build edges.
                        w=s/(1+len(self.hypergraph[token]));self.last_work+=1
                        if w>weights.get(token,0.):weights[token]=w;evidence[token]=i
                for token,w in weights.items():
                    if token in terms:continue
                    for i in self.hypergraph[token]:
                        self.last_work+=1
                        if w>out.get(i,(0.,set()))[0]:out[i]=(w,{i,evidence[token]})
                out={i:max((out.get(i,(0.,{i})),base[i]),key=lambda r:r[0]) for i in keys}
            elif op=='prop':
                a=calc(t[1]);out={i:(s,set(e)) for i,(s,e) in a.items()}
                for i,(s,e) in a.items():
                    if s<=0:continue
                    for j,_,_ in self.adj[i]:
                        self.last_work+=1
                        if s*.5>out[j][0]:out[j]=(s*.5,e|{j})
            elif op=='square':out={i:(s*s,e) for i,(s,e) in calc(t[1]).items()}
            else:
                a,b=calc(t[1]),calc(t[2])
                for i in keys:
                    x,e=a[i];y,f=b[i];s={'add':(x+y)*.5,'mul':x*y,'max':max(x,y)}[op]
                    out[i]=(s,e|f)
            if self.last_work>2_000_000:raise ValueError('retrieval work cap')
            cache[t]=out;return out
        found=calc(plan.tree)
        return [{'id':i,**self.nodes[i],'score':s,'supporting_nodes':sorted(e),'provenance':'authenticated nodes; inferred retrieval links are not graph assertions'} for i,(s,e) in sorted(found.items(),key=lambda x:(-x[1][0],x[0])) if s>0][:limit]


def synthesize(index,train,validation,test,*,budget=64):
    if not isinstance(index,SynthesizedIndex) or type(budget) is not int or not 8<=budget<=128:raise ValueError('synthesis bounds')
    seen=set()
    for group in (train,validation,test):
        if type(group) is not tuple or not 1<=len(group)<=32:raise ValueError('dataset bounds')
        for c in group:
            if not isinstance(c,Case) or c.target not in index.nodes:raise ValueError('invalid case')
            sig=tuple(sorted(tokens(c.query)))
            if sig in seen:raise ValueError('query leakage')
            seen.add(sig)
    if budget*len(train)*len(index.nodes)>100000:raise ValueError('search budget')
    total_work=0
    def assess(p,cases):
        nonlocal total_work
        rr=[];work=0
        for c in cases:
            hits=index.retrieve(p,c.query);work+=index.last_work
            rr.append(next((1/(i+1) for i,r in enumerate(hits) if r['id']==c.target),0.))
        total_work+=work
        if total_work>20_000_000:raise ValueError('aggregate work cap')
        return {'mrr':sum(rr)/len(rr),'work':work}
    baseline=Plan(('lex',)); leaves=[('lex',),('hyper',),('assoc',)]; queue=list(leaves); used=set();hist=[]
    for t in leaves:queue.extend([('prop',t),('square',t)])
    while queue and len(hist)<budget:
        t=queue.pop(0)
        if t in used:continue
        used.add(t)
        try:p=Plan(t)
        except ValueError:continue
        r=assess(p,train);hist.append((p,r))
        # Expand the best-scoring structures, not only fixed component weights.
        if len(hist)%6==0:
            for a,_ in sorted(hist,key=lambda z:(-z[1]['mrr'],z[1]['work'],repr(z[0].tree)))[:3]:
                for unary in ('prop','square'):queue.append((unary,a.tree))
                for b in leaves:
                    for op in ('add','mul','max'):queue.append((op,a.tree,b))
    challenger=max(hist,key=lambda z:(z[1]['mrr'],-z[1]['work']))[0]
    bv=assess(baseline,validation);cv=assess(challenger,validation)
    promoted=(cv['mrr'],-cv['work'])>(bv['mrr'],-bv['work']);selected=challenger if promoted else baseline
    return {'schema':'omega-memory-score-program-v1','snapshot_sha256':index.digest,'structure_sha256':index.structure_sha256,'hyperedges':len(index.hypergraph),'evaluations':len(hist),'selected':_wire(selected.tree),'challenger':_wire(challenger.tree),'promoted':promoted,'validation':cv,'baseline_validation':bv,'test':assess(selected,test),'baseline_test':assess(baseline,test),'test_evaluations':2,'work':total_work}


def _wire(t):return [t[0],*(_wire(x) for x in t[1:])]
