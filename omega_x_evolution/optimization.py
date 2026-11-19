"""Integer QUBO compiler for constrained cluster assignment and sparse tensor coding.

All external samples are rescored locally. The solver's feasibility status is
not a proof of infeasibility unless its exhaustive flag is true.
"""
from __future__ import annotations
from dataclasses import dataclass
from itertools import product
import math
import random


@dataclass(frozen=True)
class BinaryProblem:
    linear: tuple[int, ...]
    pairs: tuple[tuple[int, int, int], ...]
    equalities: tuple[tuple[tuple[int, ...], int], ...]
    slack: tuple[tuple[int, ...], ...] = ()  # groups of auxiliary bit indices
    constant: int = 0
    scale: int = 1

    def __post_init__(self):
        n = len(self.linear)
        def integer(v): return type(v) is int and abs(v) <= 10**12
        if not 2 <= n <= 64 or not all(integer(v) for v in self.linear) or not integer(self.constant) or not integer(self.scale) or self.scale < 1:
            raise ValueError('objective bounds')
        if len(self.pairs) > n*(n-1)//2 or len({(i,j) for i,j,_ in self.pairs}) != len(self.pairs) or any(type(i) is not int or type(j) is not int or not 0 <= i < j < n or not integer(v) for i,j,v in self.pairs):
            raise ValueError('quadratic terms')
        if not 1 <= len(self.equalities) <= 64 or any(len(a)!=n or not all(integer(x) for x in a) or not integer(b) for a,b in self.equalities):
            raise ValueError('constraints')
        indices=[i for g in self.slack for i in g]
        if len(indices)!=len(set(indices)) or any(type(i) is not int or not 0<=i<n for i in indices):raise ValueError('slack indices')
        auxiliary=set(indices)
        if len(auxiliary)>=n or any(self.linear[i]!=0 for i in auxiliary) or any(v and (i in auxiliary or j in auxiliary) for i,j,v in self.pairs):raise ValueError('slack must have zero objective')
        for group in self.slack:
            if not group:raise ValueError('empty slack group')
            rows=[(a,b) for a,b in self.equalities if any(a[i] for i in group)]
            if len(rows)!=1:raise ValueError('slack must belong to exactly one equation')
            row,rhs=rows[0]
            if tuple(row[i] for i in group)!=tuple(1<<k for k in range(len(group))) or any(row[i] for i in auxiliary-set(group)):raise ValueError('invalid independent binary slack')

    @property
    def n(self): return len(self.linear)
    @property
    def penalty(self): return 1+sum(map(abs,self.linear))+sum(abs(v) for _,_,v in self.pairs)
    def bits(self,bits):
        b=tuple(bits)
        if len(b)!=self.n or any(type(x) is not int or x not in (0,1) for x in b):raise ValueError('binary vector')
        return b
    def objective(self,bits):
        b=self.bits(bits)
        return self.constant+sum(x*v for x,v in zip(b,self.linear))+sum(b[i]*b[j]*v for i,j,v in self.pairs)
    def violation(self,bits):
        x=self.bits(bits)
        return sum((sum(a*b for a,b in zip(row,x))-rhs)**2 for row,rhs in self.equalities)
    def compile(self):
        q={(i,i):v for i,v in enumerate(self.linear)}
        q.update({(i,j):v for i,j,v in self.pairs}); p=self.penalty; c=self.constant
        for a,b in self.equalities:
            c+=p*b*b
            live=[(i,v) for i,v in enumerate(a) if v]
            for k,(i,v) in enumerate(live):
                q[i,i]+=p*(v*v-2*b*v)
                for j,w in live[k+1:]:q[i,j]=q.get((i,j),0)+2*p*v*w
        return q,c
    def qubo_energy(self,bits):
        b=self.bits(bits); q,c=self.compile()
        return c+sum(v*b[i]*b[j] for (i,j),v in q.items())


def logistics(durations,capacities):
    """Minimize total device runtime; one placement per job, hard capacity per device."""
    if not 1<=len(durations)<=8 or not 2<=len(capacities)<=8 or any(type(c) is not int or not 1<=c<=65535 for c in capacities) or any(len(row)!=len(capacities) or any(type(v) is not int or not 1<=v<=65535 for v in row) for row in durations):raise ValueError('logistics bounds')
    j,m=len(durations),len(capacities); base=j*m; cursor=base; groups=[]; weights=[]
    for cap in capacities:
        # Binary slack range includes [0,cap], and equality excludes excess.
        w=tuple(1<<i for i in range(cap.bit_length()));weights.append(w)
        groups.append(tuple(range(cursor,cursor+len(w))));cursor+=len(w)
    if cursor>64:raise ValueError('variable cap')
    eq=[]
    for i in range(j):eq.append((tuple(int(i*m<=k<(i+1)*m) for k in range(cursor)),1))
    for d,cap in enumerate(capacities):
        row=[0]*cursor
        for i in range(j):row[i*m+d]=durations[i][d]
        for k,w in zip(groups[d],weights[d]):row[k]=w
        eq.append((tuple(row),cap))
    return BinaryProblem(tuple(v for row in durations for v in row)+(0,)*(cursor-base),(),tuple(eq),tuple(groups))


def tensor_subset(target,factors,*,k,scale=10000):
    """Binary sparse decomposition into supplied atoms, with quantized squared error.

    Tensor dictionary selection, not unconstrained CP/Tucker factor learning.
    """
    import numpy as np
    t=np.asarray(target,dtype=float); f=np.asarray(factors,dtype=float)
    if not 1<=t.ndim<=4 or not 1<=t.size<=4096 or f.ndim!=t.ndim+1 or f.shape[1:]!=t.shape or not 2<=len(f)<=32 or type(k) is not int or not 1<=k<=len(f) or type(scale) is not int or not 1<=scale<=1000000 or not np.isfinite(t).all() or not np.isfinite(f).all() or np.max(np.abs(t))>10 or np.max(np.abs(f))>10:raise ValueError('tensor bounds')
    n=len(f); x=f.reshape(n,-1);t=t.ravel()
    lin=tuple(round(float(d)*scale) for d in (np.sum(x*x,axis=1)-2*(x@t)))
    gram=2*x@x.T
    pairs=tuple((i,j,round(float(gram[i,j])*scale)) for i in range(n) for j in range(i+1,n))
    return BinaryProblem(lin,pairs,(((1,)*n,k),),constant=round(float(t@t)*scale),scale=scale)


def solve(problem,*,steps=2048,seed=42,sampler=None,authorized=False,reads=64,exact_cap=65536):
    if not isinstance(problem,BinaryProblem) or type(steps) is not int or not 1<=steps<=16384 or type(seed) is not int or not 0<=seed<2**32 or type(exact_cap) is not int or not 0<=exact_cap<=65536 or type(reads) is not int or not 1<=reads<=256:raise ValueError('solver bounds')
    if sampler is not None and authorized is not True:raise PermissionError('explicit external quantum authorization required')
    q,c=problem.compile(); n=problem.n; rng=random.Random(seed); best=None; work=0
    # Exact arithmetic for all energies, no external claimed objective accepted.
    def evaluate(b):
        nonlocal best,work
        work+=1; e=problem.objective(b); v=problem.violation(b)
        if v==0:best=min(best,(e,b)) if best is not None else (e,b)
        return e+problem.penalty*v
    # Feasible logistics initialization with computed integer slack, also used
    # as an optimization neighborhood when many auxiliary bits are present.
    aux={i for g in problem.slack for i in g}; primary=[i for i in range(n) if i not in aux]
    def repair(b):
        x=list(b)
        for group in problem.slack:
            for i in group:x[i]=0
            row,rhs=next((r,y) for r,y in problem.equalities if all(r[i]>0 for i in group))
            v=rhs-sum(a*k for a,k in zip(row,x))
            if v>=0:
                for i in reversed(group):
                    if v>=row[i]:x[i]=1;v-=row[i]
        return tuple(x)
    exhaustive=(1<<len(primary))<=exact_cap
    if exhaustive:
        for b in product((0,1),repeat=len(primary)):
            x=[0]*n
            for i,v in zip(primary,b):x[i]=v
            evaluate(repair(x))
    else:
        # Detect disjoint exact-cardinality-one groups and preserve assignments.
        groups=[tuple(i for i in primary if row[i]) for row,rhs in problem.equalities if rhs==1 and all(v in (0,1) for v in row) and all(row[i]==0 for i in aux)]
        categorical=bool(groups) and sorted(i for g in groups for i in g)==primary
        cardinality=(not aux and len(problem.equalities)==1 and all(v==1 for v in problem.equalities[0][0]) and 0<=problem.equalities[0][1]<=n)
        x=[0]*n
        if cardinality:
            for i in rng.sample(primary,problem.equalities[0][1]):x[i]=1
        elif categorical:
            for group in groups:x[rng.choice(group)]=1
        else:
            x=[rng.randrange(2) for _ in range(n)]
        b=repair(x); energy=evaluate(b)
        magnitude=max(1,max(abs(v) for v in q.values()))
        for i in range(steps):
            x=list(b)
            if cardinality:
                a=[j for j in primary if x[j]];b0=[j for j in primary if not x[j]]
                if a and b0:x[rng.choice(a)]=0;x[rng.choice(b0)]=1
            elif categorical:
                group=rng.choice(groups)
                for pos in group:x[pos]=0
                x[rng.choice(group)]=1
            else:
                pos=rng.choice(primary);x[pos]^=1
            candidate=repair(x); e=evaluate(candidate)
            temp=magnitude*.001**(i/max(1,steps-1))
            if e<=energy or rng.random()<math.exp((energy-e)/temp):b,energy=candidate,e
    external=None
    if sampler is not None:
        count=0; feasible=0; external_best=None
        for raw in sampler(q,reads):
            count+=1
            if count>reads:raise ValueError('read budget exceeded')
            b=problem.bits(raw)
            if problem.violation(b)==0:
                feasible+=1; e=problem.objective(b);external_best=min(external_best,e) if external_best is not None else e;evaluate(b)
        external={'samples':count,'feasible_samples':feasible,'best_energy':external_best}
    return {'feasible':best is not None,'bits':list(best[1]) if best else None,'energy':best[0] if best else None,'scale':problem.scale,'exhaustive':exhaustive,'objective_evaluations':work,'external':external}


def ocean_vector_sampler(qubo,reads):
    from .quantum import dwave_sample
    n=max(i for i,j in qubo if i==j)+1
    return [tuple(int(i in sample) for i in range(n)) for sample in dwave_sample(qubo,reads)]
