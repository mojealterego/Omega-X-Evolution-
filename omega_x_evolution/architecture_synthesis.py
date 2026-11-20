"""Data-dependent hypergraph memory and typed score-program synthesis.
No generated source or dynamic imports: plans are bounded pure score trees.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import Counter, defaultdict
import hashlib
import itertools
import math
import re
from .architecture import Index, Case, vector
from .graph_memory import canonical, tokens


LEAF_OPS = ('lex','assoc','hyper','latent1','latent2','latent4','latent8','bm25')
UNARY_OPS = ('prop','square','diffuse')
BINARY_OPS = ('add','mul','max')
WORK_CAP = 2_000_000


@dataclass(frozen=True)
class Plan:
    tree: tuple
    def __post_init__(self):
        count=0
        def validate(t,depth):
            nonlocal count
            count+=1
            if type(t) is not tuple or not t or depth>16 or count>255:raise ValueError('score tree bound')
            if type(t[0]) is not str:raise ValueError('invalid score program')
            if t[0] in LEAF_OPS and len(t)==1:return
            if t[0] in UNARY_OPS and len(t)==2:validate(t[1],depth+1);return
            if t[0] in BINARY_OPS and len(t)==3:
                validate(t[1],depth+1);validate(t[2],depth+1);return
            raise ValueError('invalid score program')
        validate(self.tree,0)
    @classmethod
    def from_json(cls,value):
        count=0
        def freeze(v,depth=0):
            nonlocal count
            count+=1
            if count>255 or depth>16:raise ValueError('score tree bound')
            if type(v) is not list or not 1<=len(v)<=3 or type(v[0]) is not str:raise ValueError('invalid program encoding')
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
        self._latent=None
        self._frequencies = {i: Counter(re.findall(r'[^\W_]+',self.nodes[i]['text'].casefold(),flags=re.UNICODE)) for i in self.nodes}
        self._lengths = {i: sum(tf.values()) for i,tf in self._frequencies.items()}
        self._mean_length = sum(self._lengths.values()) / len(self.nodes) or 1.0
        self._neighbors = {i: tuple(sorted({j for j,_,_ in self.adj[i] if j != i})) for i in self.nodes}

    def _charge(self, work):
        self.last_work += work
        if self.last_work > WORK_CAP:
            raise ValueError('retrieval work cap')

    def _bm25(self, terms, keys):
        # Normalized BM25 (k1=1.2, b=0.75); absent terms contribute to the
        # denominator but not the document score. All weights come from the
        # authenticated corpus, never from the training/holdout target labels.
        n=len(keys); k1=1.2; b=.75
        weights=[(t,math.log1p((n-len(self.hypergraph.get(t,()))+.5)/(len(self.hypergraph.get(t,()))+.5))) for t in sorted(terms)]
        upper=sum(w for _,w in weights)*(k1+1)
        self._charge(n*len(weights)+len(weights))
        out={}
        for i in keys:
            norm=k1*(1-b+b*self._lengths[i]/self._mean_length)
            tf=self._frequencies[i]
            score=sum(w*tf[t]*(k1+1)/(tf[t]+norm) for t,w in weights if tf[t]) / upper
            out[i]=(min(1.,max(0.,score)),{i})
        return out

    def _diffuse(self, base, keys):
        # Bounded multi-source saturation, not a calibrated probability.
        # One contribution per adjacent node, independent of relation count.
        # Synchronous round: never use results from this round as input.
        complements=dict.fromkeys(keys,1.)
        evidence={i:set() for i in keys}
        for i in keys:
            score,support=base[i]; neighbors=self._neighbors[i]
            if score<=0 or not neighbors:continue
            share=.5*min(1.,score)/len(neighbors)
            for j in neighbors:
                self._charge(1+len(support))
                complements[j]*=1-share
                evidence[j].update(support)
        out={}
        for i in keys:
            score,support=base[i];incoming=1-complements[i]
            out[i]=(incoming,evidence[i]|{i}) if incoming>score else (score,set(support))
        return out

    def latent(self,query,rank):
        # Fit a projection solely from authenticated corpus contents, not labels.
        import numpy as np
        if self._latent is None:
            keys=tuple(sorted(self.nodes));words=tuple(sorted(self.hypergraph,key=lambda w:(-len(self.hypergraph[w]),w))[:128]);lookup={w:i for i,w in enumerate(words)}
            mat=np.zeros((len(keys),len(words)),dtype=np.float64)
            for i,k in enumerate(keys):
                for w in self.terms[k]:
                    if w in lookup:mat[i,lookup[w]]=1/math.sqrt(len(self.hypergraph[w]))
            if not words:raise ValueError('empty latent corpus')
            _,singular,vh=np.linalg.svd(mat,full_matrices=False)
            self._latent=(keys,lookup,mat,singular,vh)
        keys,lookup,mat,singular,vh=self._latent;effective=min(rank,len(singular));basis=vh[:effective].T
        q=np.zeros(len(lookup),dtype=np.float64)
        for w in tokens(query):
            if w in lookup:q[lookup[w]]=1/math.sqrt(len(self.hypergraph[w]))
        projected=mat@basis;v=q@basis;norm=np.linalg.norm(v);lengths=np.linalg.norm(projected,axis=1)
        out=np.divide(projected@v,lengths*norm,out=np.zeros(len(keys)),where=lengths*norm>1e-12)
        self.last_work+=len(keys)*len(lookup)*effective+len(lookup)*effective
        return {k:(float(min(1.,max(0.,x))),{k}) for k,x in zip(keys,out)}

    def retrieve(self,plan,query,*,limit=8):
        if type(plan) is not Plan or type(query) is not str or not 1<=len(query)<=1024 or type(limit) is not int or not 1<=limit<=32:raise ValueError('retrieval bounds')
        tree=plan.tree
        Plan(tree)  # validate immutable snapshot at the execution boundary
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
            elif op=='bm25':out=self._bm25(terms,keys)
            elif op=='assoc':
                q=vector(query);self.last_work+=128*n
                out={i:(max(0.,sum(a*b for a,b in zip(q,self.vectors[i]))),{i}) for i in keys}
            elif op.startswith('latent'):
                out=self.latent(query,int(op[6:]))
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
            elif op=='diffuse':out=self._diffuse(calc(t[1]),keys)
            elif op=='square':out={i:(s*s,e) for i,(s,e) in calc(t[1]).items()}
            else:
                a,b=calc(t[1]),calc(t[2])
                for i in keys:
                    x,e=a[i];y,f=b[i];s={'add':(x+y)*.5,'mul':x*y,'max':max(x,y)}[op]
                    out[i]=(s,e|f)
            if self.last_work>WORK_CAP:raise ValueError('retrieval work cap')
            cache[t]=out;return out
        found=calc(tree)
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
    baseline=Plan(('lex',)); leaves=[(op,) for op in LEAF_OPS]; queue=list(leaves); used=set();hist=[]
    for t in leaves:queue.extend((op,t) for op in UNARY_OPS)
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
                for unary in UNARY_OPS:queue.append((unary,a.tree))
                for b in leaves:
                    for op in BINARY_OPS:queue.append((op,a.tree,b))
    challenger=max(hist,key=lambda z:(z[1]['mrr'],-z[1]['work']))[0]
    bv=assess(baseline,validation);cv=assess(challenger,validation)
    promoted=(cv['mrr'],-cv['work'])>(bv['mrr'],-bv['work']);selected=challenger if promoted else baseline
    return {'schema':'omega-memory-score-program-v1','snapshot_sha256':index.digest,'structure_sha256':index.structure_sha256,'hyperedges':len(index.hypergraph),'evaluations':len(hist),'selected':_wire(selected.tree),'challenger':_wire(challenger.tree),'promoted':promoted,'validation':cv,'baseline_validation':bv,'test':assess(selected,test),'baseline_test':assess(baseline,test),'test_evaluations':2,'work':total_work}


def _wire(t):return [t[0],*(_wire(x) for x in t[1:])]
