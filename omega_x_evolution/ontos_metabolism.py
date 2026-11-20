"""Finite offline thermodynamic accounting. Estimates, not measured power."""
from dataclasses import dataclass
import math
import numpy as np

KB = 1.380649e-23


def number(x, low, high):
    return isinstance(x,(int,float,np.integer,np.floating)) and not isinstance(x,(bool,np.bool_)) and low<=x<=high and math.isfinite(x)


def probability(p):
    if type(p) is not tuple or not 1<=len(p)<=64 or not all(number(x,0,1) for x in p):
        raise ValueError('probability vector')
    s=math.fsum(p)
    if abs(s-1)>1e-12: raise ValueError('probability sum')
    return tuple(float(x)/s for x in p)


def channel(g, n=None):
    if type(g) is not tuple or not 1<=len(g)<=64 or (n is not None and len(g)!=n):
        raise ValueError('channel rows')
    rows=tuple(probability(row) for row in g)
    if any(len(row)!=len(rows[0]) for row in rows): raise ValueError('channel shape')
    return rows


def mix(p,g):
    return tuple(math.fsum(w*row[j] for w,row in zip(p,g)) for j in range(len(g[0])))


def entropy(p):
    return -math.fsum(x*math.log2(x) for x in p if x)


def kl(p,q):
    if len(p)!=len(q) or any(x and not y for x,y in zip(p,q)): raise ValueError('KL support')
    return math.fsum(x*(math.log(x)-math.log(y)) for x,y in zip(p,q) if x)


def transition_cost(p,q,g,ops,temperature_k,j_per_op):
    """Row-stochastic G; separate entropy bound, mismatch and compute scenario."""
    p,q=probability(p),probability(q); g=channel(g,len(p))
    if type(ops) is not int or not 0<=ops<=10**12 or not number(temperature_k,1e-6,1e6) or not number(j_per_op,0,1.):
        raise ValueError('cost bounds')
    p1,q1=mix(p,g),mix(q,g)
    decrease=max(0.,entropy(p)-entropy(p1))
    mismatch=kl(p,q)-kl(p1,q1)
    if mismatch < -1e-10: raise ArithmeticError('data processing inequality')
    mismatch=max(0.,mismatch)
    landauer=KB*temperature_k*math.log(2)*decrease
    mismatch_j=KB*temperature_k*mismatch
    compute=ops*j_per_op
    # Conservative accounting convention: independent modeled debits; not a physical measurement.
    return {'entropy_decrease_bits':decrease,'mismatch_nats':mismatch,'landauer_j':landauer,'mismatch_j':mismatch_j,'compute_j':compute,'charged_j':math.fsum((landauer,mismatch_j,compute))}


@dataclass(frozen=True)
class Ledger:
    budget_j: float
    spent_j: float = 0.

    def __post_init__(self):
        if not number(self.budget_j,0,1e12) or not number(self.spent_j,0,self.budget_j): raise ValueError('energy budget')

    def charge(self,p,q,g,ops,temperature_k,j_per_op):
        receipt=transition_cost(p,q,g,ops,temperature_k,j_per_op)
        spend=math.fsum((self.spent_j,receipt['charged_j']))
        if receipt['charged_j']>self.budget_j-self.spent_j or spend>self.budget_j or (receipt['charged_j']>0 and spend==self.spent_j): raise ValueError('energy budget exhausted or debit below resolution')
        return Ledger(self.budget_j,spend),receipt
