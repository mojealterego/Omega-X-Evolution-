"""Bounded symbolic regression from observations, with separated holdout.

Candidate expressions use the existing restricted interpreter. Hypotheses are
empirical fits, not proofs of scientific laws. No formula is provided to search.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import itertools
import json
import math
from pathlib import Path
import random

from .engine import Expression

SCHEMA='omega-discovery-v1'
ATOMS=('x','y','0','1','2','0.5')
BINARY=('+','-','*','/')
STRATEGIES=('enumeration','random','evolution')
TASKS=('sum','product','squares','distance','ratio')


def _encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


@dataclass(frozen=True)
class Observation:
    x:float
    y:float
    z:float

    def __post_init__(self):
        if any(type(v) not in (float,int) or not -1e12<=v<=1e12 for v in (self.x,self.y,self.z)) or not 0<=self.x<=1 or not 0<=self.y<=1:
            raise ValueError('invalid observation')


@dataclass(frozen=True)
class Dataset:
    train:tuple[Observation,...]
    holdout:tuple[Observation,...]

    def __post_init__(self):
        for group in (self.train,self.holdout):
            if type(group) is not tuple or not 1<=len(group)<=512 or any(not isinstance(p,Observation) for p in group): raise ValueError('invalid dataset')
        points=[(p.x,p.y) for p in self.train+self.holdout]
        if len(set(points))!=len(points): raise ValueError('duplicate or overlapping observations')

    def digest(self):
        return hashlib.sha256(_encode(asdict(self)).encode()).hexdigest()

    @classmethod
    def from_json(cls,raw):
        if not isinstance(raw,str) or len(raw)>131072: raise ValueError('dataset size')
        try:
            obj=json.loads(raw)
            if set(obj)!={'train','holdout'}: raise ValueError('dataset fields')
            return cls(*(tuple(Observation(**p) for p in obj[k]) for k in ('train','holdout')))
        except (TypeError,KeyError,RecursionError) as exc: raise ValueError('invalid dataset') from exc


def fixture(task, *, seed):
    if task not in TASKS or type(seed) is not int or not 0<=seed<2**32: raise ValueError('invalid fixture')
    functions={'sum':lambda x,y:x+y,'product':lambda x,y:x*y,
               'squares':lambda x,y:x*x+y*y,'distance':lambda x,y:abs(x-y),
               'ratio':lambda x,y:(x+1)/(y+1)}
    rng=random.Random(seed); fn=functions[task]
    points=[]; seen=set()
    while len(points)<48:
        x=rng.random(); y=rng.random()
        if (x,y) not in seen: points.append(Observation(x,y,fn(x,y))); seen.add((x,y))
    return Dataset(tuple(points[:32]),tuple(points[32:]))


def _rmse(expr, data):
    try:
        return math.sqrt(math.fsum((expr.evaluate(float(p.x),float(p.y))-p.z)**2 for p in data)/len(data))
    except (ArithmeticError,ValueError): return None


def _combine(a,b,op): return f'({a}{op}{b})'


def _grammar():
    # Grammar ordering is fixed and shared by all strategies, independent of targets.
    yield from ATOMS
    # Cover all variable-only combinations first, then a compositional layer.
    pair=[_combine(a,b,op) for a,b,op in itertools.product(ATOMS[:2],ATOMS[:2],BINARY)]
    yield from pair
    yield from (f'abs({a})' for a in pair)
    yield from (_combine(_combine("x","x",inner),_combine("y","y",inner),outer)
                for inner,outer in itertools.product(BINARY,BINARY))
    yield from (_combine(a,b,op) for a,b,op in itertools.product(pair,pair,BINARY))
    yield from (_combine(a,b,op) for a,b,op in itertools.product(ATOMS,ATOMS,BINARY))


def _random(rng,depth):
    if not depth or rng.random()<.35: return rng.choice(ATOMS)
    if rng.random()<.2: return f'abs({_random(rng,depth-1)})'
    return _combine(_random(rng,depth-1),_random(rng,depth-1),rng.choice(BINARY))


def _mutate(rng,elite):
    a=rng.choice(elite); b=rng.choice(elite+list(ATOMS))
    if rng.random()<.2: return f'abs({a})'
    return _combine(a,b,rng.choice(BINARY))


def discover(data:Dataset, *, seed=42,budget=128,strategy='evolution'):
    if not isinstance(data,Dataset) or type(seed) is not int or not 0<=seed<2**32 or type(budget) is not int or not 1<=budget<=4096 or strategy not in STRATEGIES:
        raise ValueError('invalid experiment configuration')
    if budget*len(data.train)>1_000_000: raise ValueError('observation evaluation budget')
    rng=random.Random(seed); grammar=list(dict.fromkeys(_grammar()))
    ranking=[]; seen=set(); valid=0; first_exact=None
    # Shared seed library for evolutionary and enumeration strategies. Random
    # baseline starts with the same first atom, so every method has a finite fit.
    # Each proposal (duplicate or invalid included) consumes one attempt.
    for i in range(budget):
        if i==0: source=ATOMS[0]
        elif strategy=='enumeration': source=grammar[i%len(grammar)]
        elif strategy=='random': source=grammar[rng.randrange(len(grammar))] if i%2 else _random(rng,3)
        elif i<min(54,len(grammar)): source=grammar[i]
        elif i%3==0: source=grammar[rng.randrange(len(grammar))]
        else: source=_mutate(rng,[r[3] for r in ranking[:12]])
        if source in seen: continue
        seen.add(source)
        try: expr=Expression(source)
        except ValueError: continue
        loss=_rmse(expr,data.train)
        if loss is None: continue
        valid+=1
        if loss<=1e-12 and first_exact is None: first_exact=i+1
        ranking.append((loss,expr.operations,expr.count,source)); ranking.sort()
        if len(ranking)>12: ranking.pop()
    loss,ops,nodes,source=ranking[0]
    # Validation never affects selection. It is read exactly once after search.
    held=_rmse(Expression(source),data.holdout)
    return {'schema':SCHEMA,'dataset_sha256':data.digest(),'seed':seed,'strategy':strategy,
            'attempts':budget,'unique_attempts':len(seen),'valid_candidates':valid,'first_exact_attempt':first_exact,
            'expression':source,'operations':ops,'nodes':nodes,'training_rmse':loss,
            'holdout_rmse':held,'holdout_evaluations':1,'empirical_match':held is not None and held<=1e-12 and loss<=1e-12}


def verify_report(data,report):
    # Reproduce the entire bounded experiment rather than trusting reported metrics.
    if not isinstance(report,dict): return False
    try: return _encode(discover(data,seed=report['seed'],budget=report['attempts'],strategy=report['strategy']))==_encode(report)
    except (ValueError,TypeError,KeyError,OverflowError): return False


def main():
    p=argparse.ArgumentParser(description=__doc__); group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--task',choices=TASKS); group.add_argument('--dataset',type=Path)
    p.add_argument('--seed',type=int,default=42); p.add_argument('--budget',type=int,default=128); p.add_argument('--strategy',choices=STRATEGIES,default='evolution')
    a=p.parse_args()
    try:
        if a.dataset:
            with a.dataset.open(encoding='utf-8') as f: data=Dataset.from_json(f.read(131073))
        else: data=fixture(a.task,seed=a.seed)
        result=discover(data,seed=a.seed,budget=a.budget,strategy=a.strategy)
    except (ValueError,OSError) as exc: p.error(str(exc))
    print(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__': main()
