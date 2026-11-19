"""Classical quantum-inspired tensor-train policy and annealed hypothesis search.

TT-SVD compresses a small contextual reward tensor. All selected hypotheses
consume individual proposal/evaluation slots; no quantum speedup is assumed.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import random
from .engine import Expression

ACTIONS=6


@dataclass(frozen=True)
class TensorTrain:
    cores: tuple

    @classmethod
    def fit(cls,tensor,rank=2):
        import numpy as np
        a=np.asarray(tensor,dtype=float)
        if a.shape!=(4,4,6) or not np.isfinite(a).all() or type(rank) is not int or not 1<=rank<=4:
            raise ValueError('tensor shape/rank')
        cores=[];left=1;rest=a
        for n in a.shape[:-1]:
            u,s,v=np.linalg.svd(rest.reshape(left*n,-1),full_matrices=False)
            # Avoid retaining zero singular modes; rank-1 tensors compress exactly.
            r=min(rank,max(1,int(np.count_nonzero(s>max(1e-12,s[0]*1e-12)))))
            cores.append(u[:,:r].reshape(left,n,r));rest=s[:r,None]*v[:r];left=r
        cores.append(rest.reshape(left,a.shape[-1],1))
        for c in cores:c.setflags(write=False)
        return cls(tuple(cores))

    @property
    def parameters(self):return sum(c.size for c in self.cores)

    def at(self,i,j,k):
        if not (0<=i<4 and 0<=j<4 and 0<=k<ACTIONS):raise ValueError('tensor index')
        return float((self.cores[0][:,i,:]@self.cores[1][:,j,:]@self.cores[2][:,k,:])[0,0])


def context(code):
    e=Expression(code)
    return min(3,e.count//8),min(3,e.operations//4)


def policy(parent,records,*,temperature=0.5,associations=()):
    import numpy as np
    if not math.isfinite(temperature) or not .1<=temperature<=2 or len(records)>64 or len(associations)>8:
        raise ValueError('policy bounds')
    # Shrink sparse local means toward the global action prior, then TT compress.
    sums=np.zeros((4,4,ACTIONS));counts=np.zeros_like(sums);global_sum=np.zeros(ACTIONS);global_n=np.zeros(ACTIONS)
    for row in records:
        a=row['action']
        if a>=ACTIONS:continue
        i,j=context(row['parent']); reward=row['reward'];sums[i,j,a]+=reward;counts[i,j,a]+=1;global_sum[a]+=reward;global_n[a]+=1
    prior=global_sum/(global_n+2)
    tt=TensorTrain.fit((sums+2*prior)/(counts+2),3)
    i,j=context(parent);values=np.array([tt.at(i,j,a) for a in range(ACTIONS)])
    for hit in associations:
        row=hit['record'];a=row['action']
        if a<ACTIONS:values[a]+=hit['weight']*row['reward']
    # Parallel vector scoring, annealed Gibbs sampling, positive exploration floor.
    logits=(values-values.max())/temperature;prob=np.exp(logits);prob/=prob.sum()
    return tuple(float(.9*x+.1/ACTIONS) for x in prob)


def propose(parent,action,seed):
    if type(action) is not int or not 0<=action<ACTIONS:raise ValueError('action')
    Expression(parent);rng=random.Random(seed)
    a=round(rng.uniform(.2,3),3);b=round(rng.uniform(.005,.1),4);c=round(rng.uniform(.1,3),3)
    codes=[f'-(x+y+{a}*abs(x-y)+{c})',f'-(x+y+{a}*(x-y)*(x-y)+{c})',f'-(x+y+{a}*max(x,y)+{c})',f'-(x+y+{a}*abs(x-y)/(x+y+{b})+{c})',f'-(x+y+{a}*(x-y)*(x-y)/({b}+x*y)+{c})',f'-(x+y+{a}*(x-y)*(x-y)/({b}+min(x,y))+{c})']
    return f'<<<<<<< SEARCH\n{parent}\n=======\n{codes[action]}\n>>>>>>> REPLACE'
