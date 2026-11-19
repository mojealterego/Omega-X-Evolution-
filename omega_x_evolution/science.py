"""Dimension-aware sparse equation discovery across bounded numeric domains."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import re

import numpy as np

from .graph_memory import canonical

Unit = tuple[int, int, int, int]  # length, mass, time, amount
Row = tuple[tuple[float, ...], float]
DOMAINS = ('kinematics', 'mechanics', 'kinetics', 'dynamics')


def _unit(value):
    if type(value) is not tuple or len(value) != 4 or any(type(v) is not int or abs(v)>8 for v in value):
        raise ValueError('unit must be four bounded integer exponents')


def _number(value):
    return type(value) in (int,float) and -1e6<=value<=1e6


@dataclass(frozen=True)
class Data:
    names: tuple[str, ...]
    units: tuple[Unit, ...]
    output_unit: Unit
    train: tuple[Row, ...]
    validation: tuple[Row, ...]
    test: tuple[Row, ...]

    def __post_init__(self):
        if (type(self.names) is not tuple or not 1<=len(self.names)<=8 or
            any(type(n) is not str or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,31}',n) for n in self.names) or
            len(set(self.names))!=len(self.names) or type(self.units) is not tuple or len(self.units)!=len(self.names)):
            raise ValueError('invalid features')
        for unit in (*self.units,self.output_unit): _unit(unit)
        seen=set()
        for group in (self.train,self.validation,self.test):
            if type(group) is not tuple or not 1<=len(group)<=512: raise ValueError('invalid split size')
            for row in group:
                if type(row) is not tuple or len(row)!=2: raise ValueError('invalid observation')
                x,z=row
                if type(x) is not tuple or len(x)!=len(self.names) or not all(_number(v) for v in (*x,z)) or x in seen:
                    raise ValueError('invalid or overlapping coordinates')
                seen.add(x)

    def to_json(self): return canonical(asdict(self))

    def digest(self): return hashlib.sha256(self.to_json().encode()).hexdigest()

    @classmethod
    def from_json(cls,raw):
        if type(raw) is not str or len(raw)>524288: raise ValueError('dataset size')
        try:
            d=json.loads(raw)
            if type(d) is not dict or any(type(d.get(k)) is not list for k in ('names','units','output_unit','train','validation','test')) or set(d)!={'names','units','output_unit','train','validation','test'}: raise ValueError('dataset fields')
            return cls(tuple(d['names']),tuple(tuple(u) for u in d['units']),tuple(d['output_unit']),
                       *(tuple((tuple(x),z) for x,z in d[k]) for k in ('train','validation','test')))
        except (KeyError,TypeError,RecursionError) as exc: raise ValueError('invalid dataset') from exc


def fixture(domain, *, seed=42):
    if domain not in DOMAINS or type(seed) is not int or not 0<=seed<2**32: raise ValueError('invalid domain or seed')
    L=(1,0,0,0); T=(0,0,1,0); V=(1,0,-1,0); A=(1,0,-2,0); M=(0,1,0,0); C=(-3,0,0,1)
    specs={
        'kinematics':(('position','velocity','acceleration','time'),(L,V,A,T),L,lambda x:x[0]+x[1]*x[3]+.5*x[2]*x[3]**2),
        'mechanics':(('mass','acceleration','velocity'),(M,A,V),(1,1,-2,0),lambda x:x[0]*x[1]),
        'kinetics':(('rate_constant','reactant_a','reactant_b'),((3,0,-1,-1),C,C),(-3,0,-1,1),lambda x:x[0]*x[1]*x[2]),
        'dynamics':(('displacement','velocity','stiffness','damping'),(L,V,(0,0,-2,0),(0,0,-1,0)),A,lambda x:-x[0]*x[2]-x[1]*x[3]),
    }
    names,units,out,fn=specs[domain]
    rng=random.Random(seed); rows=[]
    for _ in range(96):
        x=tuple(rng.uniform(.1,2) for _ in names); rows.append((x,fn(x)))
    return Data(names,units,out,tuple(rows[:48]),tuple(rows[48:72]),tuple(rows[72:]))


def library(data:Data, degree:int):
    """Monomial basis whose total units equal the target; coefficients dimensionless."""
    if not isinstance(data,Data) or type(degree) is not int or not 1<=degree<=3: raise ValueError('degree bound')
    out=[]
    for d in range(degree+1):
        for term in itertools.combinations_with_replacement(range(len(data.names)),d):
            if tuple(sum(data.units[i][k] for i in term) for k in range(4))==data.output_unit: out.append(term)
    return tuple(out)


def _matrix(rows,terms):
    x=np.asarray([r[0] for r in rows],dtype=np.float64)
    return np.column_stack([np.prod(x[:,term],axis=1) if term else np.ones(len(x)) for term in terms])


def _rmse(pred,truth):
    result=float(np.sqrt(np.mean(np.square(pred-truth))))
    if not math.isfinite(result): raise ValueError('nonfinite fit')
    return result


def discover(data:Data, *, degree=3,max_terms=8,budget=128):
    if not isinstance(data,Data) or type(max_terms) is not int or not 1<=max_terms<=12 or type(budget) is not int or not 1<=budget<=4096: raise ValueError('search budget')
    terms=library(data,degree)
    if not terms: raise ValueError('no dimensionally valid monomials')
    # Training-only normalized pursuit. Validation chooses the best prefix;
    # each prefix consumes one fit attempt, and no test labels are read here.
    a=_matrix(data.train,terms); y=np.asarray([r[1] for r in data.train]); b=_matrix(data.validation,terms); v=np.asarray([r[1] for r in data.validation])
    norm=np.linalg.norm(a,axis=0); available={i for i,n in enumerate(norm) if n>0}
    selected=[]; candidates=[]; residual=y.copy(); history=[]; attempts=0
    for _ in range(min(max_terms,budget,len(available),len(y))):
        if not available: break
        j=min(available,key=lambda i:(-abs(float(a[:,i]@residual))/norm[i],i))
        available.remove(j); selected.append(j);attempts+=1
        coefficients,_,rank,_=np.linalg.lstsq(a[:,selected]/norm[selected],y,rcond=1e-12)
        coefficients=coefficients/norm[selected]
        if rank!=len(selected) or not np.isfinite(coefficients).all():
            selected.pop(); continue
        residual=y-a[:,selected]@coefficients
        tr=_rmse(a[:,selected]@coefficients,y); val=_rmse(b[:,selected]@coefficients,v)
        record={'indices':list(selected),'coefficients':coefficients.tolist(),'train_rmse':tr,'validation_rmse':val}
        history.append(record); candidates.append(record)
        if tr<=1e-12*max(1.,float(np.max(np.abs(y)))): break
    if not candidates: raise ValueError('no full rank fit')
    best=min(candidates,key=lambda r:(r['validation_rmse'],len(r['indices']),r['indices']))
    # Favor sparse models within a small train-derived numerical tolerance.
    tolerance=1e-12*max(1.,float(np.max(np.abs(y))))
    best=min((r for r in candidates if r['validation_rmse']<=best['validation_rmse']+tolerance), key=lambda r:(len(r['indices']),r['validation_rmse'],r['indices']))
    chosen=[terms[i] for i in best['indices']]
    test=_rmse(_matrix(data.test,chosen)@np.asarray(best['coefficients']),np.asarray([r[1] for r in data.test]))
    return {'schema':'omega-science-v1','data_sha256':data.digest(),'degree':degree,'max_terms':max_terms,'budget':budget,
            'library_size':len(terms),'fit_attempts':attempts,'terms':[{'features':[data.names[i] for i in t],'coefficient':c,'unit':list(data.output_unit)} for t,c in zip(chosen,best['coefficients'])],
            'selection':best,'history':history,'test_rmse':test,'test_evaluations':1}


def verify(data,report):
    try: return canonical(discover(data,degree=report['degree'],max_terms=report['max_terms'],budget=report['budget']))==canonical(report)
    except (ValueError,TypeError,KeyError,OverflowError,np.linalg.LinAlgError): return False


def main():
    p=argparse.ArgumentParser(description=__doc__); group=p.add_mutually_exclusive_group(required=True);group.add_argument('--domain',choices=DOMAINS);group.add_argument('--dataset',type=Path)
    p.add_argument('--seed',type=int,default=42);p.add_argument('--degree',type=int,default=3);p.add_argument('--max-terms',type=int,default=8);p.add_argument('--budget',type=int,default=128);a=p.parse_args()
    if a.dataset:
        with a.dataset.open(encoding='utf-8') as f: data=Data.from_json(f.read(524289))
    else: data=fixture(a.domain,seed=a.seed)
    print(json.dumps(discover(data,degree=a.degree,max_terms=a.max_terms,budget=a.budget),indent=2,allow_nan=False))


if __name__=='__main__': main()
