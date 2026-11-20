"""Bounded QUBO selection of diverse MAP-Elites representatives.
Classical reference and explicit, single-submission quantum adapter.
"""
from __future__ import annotations
from dataclasses import dataclass
from itertools import combinations
from numbers import Integral
import argparse
import json
import math
import random
import time


@dataclass(frozen=True)
class Problem:
    quality: tuple[int, ...]
    features: tuple[tuple[int, ...], ...]
    k: int

    def __post_init__(self):
        n=len(self.quality)
        if (type(self.quality) is not tuple or type(self.features) is not tuple or
            not 2<=n<=32 or len(self.features)!=n or type(self.k) is not int or not 1<=self.k<=min(8,n) or
            any(type(q) is not int or not 0<=q<=1000 for q in self.quality) or
            any(type(f) is not tuple or not 1<=len(f)<=16 or len(f)!=len(self.features[0]) or
                any(type(v) is not int or not 0<=v<=100 for v in f) for f in self.features)):
            raise ValueError('QUBO bounds')

    @property
    def n(self):return len(self.quality)

    def diversity(self,i,j):
        # Integer normalization, up to 200 reward per selected pair.
        return 2*sum(abs(a-b) for a,b in zip(self.features[i],self.features[j]))//len(self.features[i])

    @property
    def penalty(self):return 1+sum(self.quality)+200*self.n*(self.n-1)//2

    def _indices(self,indices):
        x=tuple(indices)
        if any(type(i) is not int or not 0<=i<self.n for i in x) or len(set(x))!=len(x):raise ValueError('invalid selected indices')
        return tuple(sorted(x))

    def energy(self,indices):
        x=self._indices(indices)
        if len(x)!=self.k:raise ValueError('cardinality constraint')
        return -sum(self.quality[i] for i in x)-sum(self.diversity(i,j) for i,j in combinations(x,2))

    def qubo(self):
        p=self.penalty
        return {(i,j):p*(1-2*self.k)-self.quality[i] if i==j else 2*p-self.diversity(i,j)
                for i in range(self.n) for j in range(i,self.n)}

    def qubo_energy(self,indices):
        x=self._indices(indices);q=self.qubo()
        return self.penalty*self.k**2+sum(q[i,i] for i in x)+sum(q[i,j] for i,j in combinations(x,2))


def _result(p,x,backend,work,started):
    x=p._indices(x)
    return {'backend':backend,'indices':list(x),'energy':p.energy(x),'objective_evaluations':work,
            'wall_seconds':time.perf_counter()-started}


def exact(p):
    count=math.comb(p.n,p.k)
    if count>100000:raise ValueError('exact enumeration budget')
    t=time.perf_counter();x=min(combinations(range(p.n),p.k),key=lambda x:(p.energy(x),x))
    return _result(p,x,'exact',count,t)


def anneal(p,*,seed=42,steps=512):
    if type(seed) is not int or not 0<=seed<2**32 or type(steps) is not int or not 1<=steps<=16384:raise ValueError('annealing budget')
    t=time.perf_counter();rng=random.Random(seed);x=tuple(sorted(rng.sample(range(p.n),p.k)));e=p.energy(x);best=(e,x);work=1
    if p.k<p.n:
        for s in range(steps):
            out=rng.choice(x);inc=rng.choice([i for i in range(p.n) if i not in x]);y=tuple(sorted(set(x)-{out}|{inc}))
            # At k>=5 the exact swap delta uses fewer pair terms than recomputation.
            # Retained pairs cancel; integer arithmetic preserves the acceptance path.
            if p.k>=5:
                v=e+p.quality[out]-p.quality[inc]+sum(p.diversity(out,j)-p.diversity(inc,j) for j in x if j!=out)
            else:
                v=p.energy(y)
            work+=1
            temp=500*(.001**(s/max(1,steps-1)))
            if v<=e or rng.random()<math.exp((e-v)/temp):x,e=y,v
            best=min(best,(e,x))
    return _result(p,best[1],'classical-anneal',work,t)


def hardware(p,sampler,*,authorized=False,reads=64):
    """One authorized submission. Treat samples as untrusted; score locally.
    A provider callback is operator-owned; no automatic external fallback.
    """
    if authorized is not True:raise PermissionError('explicit quantum submission authorization required')
    if type(reads) is not int or not 1<=reads<=256:raise ValueError('quantum reads budget')
    t=time.perf_counter();best=None;count=0
    for raw in sampler(p.qubo(),reads):
        count+=1
        if count>reads:raise ValueError('provider exceeded read cap')
        x=p._indices(raw)
        if len(x)!=p.k:continue
        candidate=(p.energy(x),x);best=candidate if best is None else min(best,candidate)
    if best is None:raise ValueError('no feasible quantum sample')
    return _result(p,best[1],'external-sampler',count,t)


def dwave_sample(qubo,reads):
    """Opt-in Ocean adapter; operator supplies credentials and provider limits."""
    if type(reads) is not int or not 1<=reads<=256:raise ValueError('quantum reads budget')
    from dwave.system import DWaveSampler, EmbeddingComposite
    with DWaveSampler(failover=False,request_timeout=15,polling_timeout=90,permissive_ssl=False) as sampler:
        samples=EmbeddingComposite(sampler).sample_qubo(qubo,num_reads=reads)
        # Resolve provider data before closing sampler. Never trust reported energy.
        result=[]
        for r in samples.data(fields=['sample','num_occurrences']):
            count=r.num_occurrences
            if isinstance(count,bool) or not isinstance(count,Integral) or count<=0:
                raise ValueError('invalid quantum occurrence count')
            if count>reads-len(result):raise ValueError('provider exceeded read cap')
            if any(v not in (0,1) for v in r.sample.values()):raise ValueError('invalid quantum binary sample')
            if set(r.sample)!={i for i,j in qubo if i==j}:raise ValueError('quantum variable mismatch')
            selected=tuple(int(i) for i,v in r.sample.items() if v==1)
            result.extend([selected]*int(count))
        return result


def select_elites(artifacts,k,*,seed=42,steps=512,sampler=None,authorized=False,reads=64):
    from .engine import score, Expression
    from .topology import phenotype
    # Dedup + rank cap applied before selection; fixed fitness never changed.
    if sampler is not None and authorized is not True:raise PermissionError('explicit quantum submission authorization required')
    ranked=sorted(artifacts,key=lambda a:(-score(a.metrics),a.id)); unique={}
    for a in ranked:unique.setdefault(a.code,a)
    rows=list(unique.values())[:32]
    if type(k) is not int or not 1<=k<=8:raise ValueError('selection count')
    if not rows:raise ValueError('empty archive')
    if len(rows)==1:return rows,{'backend':'singleton','indices':[0],'energy':None,'objective_evaluations':0,'wall_seconds':0.}
    features=tuple(phenotype(a.code,101)+tuple(int(m*100) for m in a.metrics[:3]) for a in rows)
    p=Problem(tuple(round(score(a.metrics)*1000) for a in rows),features,min(k,len(rows)))
    result=anneal(p,seed=seed,steps=steps)
    if sampler is not None:
        q=hardware(p,sampler,authorized=authorized,reads=reads)
        # Keep best feasible result; no provider-supplied fitness or automatic retry.
        chosen=min((result,q),key=lambda r:(r['energy'],r['indices']))
        result={**chosen,'classical_reference':result,'quantum_trial':q,'provider_submissions':1}
    return [rows[i] for i in result['indices']],result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seed',type=int,default=42);p.add_argument('--steps',type=int,default=512);p.add_argument('--qpu',action='store_true');p.add_argument('--authorize-paid-submission',action='store_true');p.add_argument('--reads',type=int,default=64);a=p.parse_args()
    rng=random.Random(a.seed);problem=Problem(tuple(rng.randrange(400,1001) for _ in range(16)),tuple(tuple(rng.randrange(101) for _ in range(8)) for _ in range(16)),4)
    r={'exact':exact(problem),'classical':anneal(problem,seed=a.seed,steps=a.steps)}
    if a.qpu:r['quantum']=hardware(problem,dwave_sample,authorized=a.authorize_paid_submission,reads=a.reads)
    print(json.dumps(r,indent=2))


if __name__=='__main__':main()
