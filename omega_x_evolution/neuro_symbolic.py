"""Symbolic discovery plus learned residual with a separate selection and test split."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import hashlib
import math
from pathlib import Path
import random
import numpy as np
from .discovery import Dataset, Observation, discover
from .engine import Expression
from .formal import verified_optimize
from .neural import Architecture, fit, predict, rmse, digest


@dataclass(frozen=True)
class Split:
    train:tuple[Observation,...]
    validation:tuple[Observation,...]
    test:tuple[Observation,...]

    def __post_init__(self):
        points=[]
        for rows in (self.train,self.validation,self.test):
            if type(rows) is not tuple or not 1<=len(rows)<=512 or any(not isinstance(p,Observation) for p in rows): raise ValueError('invalid data split')
            points.extend((p.x,p.y) for p in rows)
        if len(set(points))!=len(points): raise ValueError('overlapping observations')

    def digest(self):
        return hashlib.sha256(json.dumps(asdict(self),sort_keys=True,allow_nan=False,separators=(',',':')).encode()).hexdigest()

    @classmethod
    def from_json(cls, raw):
        if not isinstance(raw,str) or len(raw)>262144: raise ValueError('dataset size')
        try:
            ob=json.loads(raw)
            if set(ob)!= {'train','validation','test'}: raise ValueError('dataset fields')
            return cls(*(tuple(Observation(**p) for p in ob[k]) for k in ('train','validation','test')))
        except (TypeError,KeyError,RecursionError) as e: raise ValueError('invalid dataset') from e


def fixture(task, *, seed=42):
    if type(seed) is not int or not 0<=seed<2**32 or task not in ('smooth','xor'): raise ValueError('invalid fixture')
    rng=random.Random(seed); points=[]; seen=set()
    while len(points)<192:
        x,y=rng.random(),rng.random()
        if (x,y) in seen: continue
        seen.add((x,y));z=x+y+.25*math.sin(2*math.pi*x)*math.cos(2*math.pi*y) if task=='smooth' else float((x>.5)!=(y>.5))
        points.append(Observation(x,y,z))
    return Split(tuple(points[:96]),tuple(points[96:144]),tuple(points[144:]))


def symbolic_predictions(source, data):
    e=Expression(source)
    return np.array([e.evaluate(float(o.x),float(o.y)) for o in data],dtype=np.float64).reshape(-1,1)


def hybrid(data:Split, *, seed=42,budget=128,epochs=200):
    if not isinstance(data,Split): raise ValueError('invalid split')
    # Symbolic search has training data only; its reported holdout is the
    # selection split, not the final test. Optimization must pass v7 proof gate.
    report=discover(Dataset(data.train,data.validation),seed=seed,budget=budget)
    source=verified_optimize(report['expression']).source
    tr=symbolic_predictions(source,data.train)
    val=symbolic_predictions(source,data.validation)
    model=fit(Architecture((16,16),'tanh','momentum',.05),data.train,seed=seed,epochs=epochs,residual=tr)
    baseline=rmse(val,data.validation); candidate=rmse(val+predict(model,data.validation),data.validation)
    chosen=candidate<baseline
    try:
        test=symbolic_predictions(source,data.test)
        test_base=rmse(test,data.test); test_hybrid=rmse(test+predict(model,data.test),data.test)
    except (ArithmeticError,ValueError):
        test_base=test_hybrid=None
    return {'schema':'omega-hybrid-v1','dataset_sha256':data.digest(),'seed':seed,'epochs':epochs,'expression':source,'symbolic_attempts':report['attempts'],'selected':'hybrid' if chosen else 'symbolic',
            'validation':{'symbolic':baseline,'hybrid':candidate,'selected':candidate if chosen else baseline},
            'test':{'symbolic':test_base,'hybrid':test_hybrid,'selected':test_hybrid if chosen else test_base},
            'training_loss_before':model.losses[0],'training_loss_after':model.losses[-1],
            'residual_model':asdict(model.architecture),'parameters':model.architecture.parameters,'weights_sha256':digest(model),'model':json.loads(model.to_json())}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seed',type=int,default=42);p.add_argument('--budget',type=int,default=128);p.add_argument('--epochs',type=int,default=200);p.add_argument('--dataset',type=Path);a=p.parse_args()
    if a.dataset:
        with a.dataset.open(encoding='utf-8') as f: data=Split.from_json(f.read(262145))
    else: data=fixture('smooth',seed=a.seed)
    print(json.dumps(hybrid(data,seed=a.seed,budget=a.budget,epochs=a.epochs),indent=2,allow_nan=False))


if __name__=='__main__': main()
