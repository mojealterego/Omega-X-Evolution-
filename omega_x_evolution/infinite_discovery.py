"""Exact polynomial conjectures over infinite fields, and dimensioned rational laws.

A finite determining grid is a mathematical identity test for bounded-degree
polynomials, not a claim that finitely many physics observations prove a law.
"""
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
from itertools import product, combinations_with_replacement
import hashlib
import json
import random
from .graph_memory import canonical

VARIABLES=('x','y','z')
MAX_GRID=729


@dataclass(frozen=True)
class Polynomial:
    tree:tuple
    def __post_init__(self):
        count=0
        def walk(t,depth):
            nonlocal count
            count+=1
            if type(t) is not tuple or not t or depth>7 or count>63:raise ValueError('polynomial bound')
            if t[0] in VARIABLES and len(t)==1:return
            if t[0]=='lit' and len(t)==3 and type(t[1]) is int and type(t[2]) is int and -100<=t[1]<=100 and 1<=t[2]<=100:return
            if t[0] in ('add','sub','mul') and len(t)==3:walk(t[1],depth+1);walk(t[2],depth+1);return
            raise ValueError('polynomial grammar')
        walk(self.tree,0)
        if self.grid_size>MAX_GRID:raise ValueError('degree grid cap')
    @property
    def degrees(self):
        def go(t):
            if t[0] in VARIABLES:return tuple(int(t[0]==i) for i in VARIABLES)
            if t[0]=='lit':return (0,0,0)
            a,b=go(t[1]),go(t[2]);return tuple((x+y if t[0]=='mul' else max(x,y)) for x,y in zip(a,b))
        return go(self.tree)
    @property
    def grid_size(self):
        import math
        return math.prod(d+1 for d in self.degrees)
    def evaluate(self,coordinates):
        def go(t):
            if t[0] in VARIABLES:return Fraction(coordinates[VARIABLES.index(t[0])])
            if t[0]=='lit':return Fraction(t[1],t[2])
            a,b=go(t[1]),go(t[2]);return a+b if t[0]=='add' else a-b if t[0]=='sub' else a*b
        return go(self.tree)


def _degrees(a,b):return tuple(max(x,y) for x,y in zip(a.degrees,b.degrees))
def _wire(t):return json.loads(canonical(t))
def _ratio(v):return [v.numerator,v.denominator]


def classify(a,b):
    import math
    if not isinstance(a,Polynomial) or not isinstance(b,Polynomial):raise ValueError('polynomial input')
    degrees=_degrees(a,b);count=math.prod(d+1 for d in degrees)
    base={'left':_wire(a.tree),'right':_wire(b.tree),'degrees':list(degrees),'domain':'Q and R (polynomial identity)'}
    if count>MAX_GRID:return {**base,'status':'unknown','reason':'determining grid cap'}
    h=hashlib.sha256()
    for point in product(*(range(d+1) for d in degrees)):
        x,y=a.evaluate(point),b.evaluate(point)
        if x!=y:return {**base,'status':'refuted','counterexample':list(point),'values':[_ratio(x),_ratio(y)]}
        h.update(canonical([point,_ratio(x)]).encode())
    return {**base,'status':'proved','grid_points':count,'grid_sha256':h.hexdigest()}


def _normal(t):
    # Independent formal coefficient expansion, rather than sampling.
    if t[0] in VARIABLES:return {tuple(int(t[0]==i) for i in VARIABLES):Fraction(1)}
    if t[0]=='lit':return {(0,0,0):Fraction(t[1],t[2])}
    a,b=_normal(t[1]),_normal(t[2]);out={}
    if t[0]=='mul':
        for i,x in a.items():
            for j,y in b.items():
                k=tuple(m+n for m,n in zip(i,j));out[k]=out.get(k,Fraction(0))+x*y
    else:
        out=dict(a)
        for i,y in b.items():out[i]=out.get(i,Fraction(0))+(y if t[0]=='add' else -y)
    return {i:v for i,v in out.items() if v}


def verify(a,b,report):
    try:
        if report!=classify(a,b):return False
        if report['status']=='proved':return {k:v for k,v in _normal(a.tree).items() if v}=={k:v for k,v in _normal(b.tree).items() if v}
        if report['status']=='refuted':p=tuple(report['counterexample']);return a.evaluate(p)!=b.evaluate(p)
        return False
    except (ValueError,TypeError,KeyError,ArithmeticError,AttributeError):return False


def discover(*,seed=42,budget=128):
    if type(seed) is not int or not 0<=seed<2**32 or type(budget) is not int or not 16<=budget<=256:raise ValueError('discovery budget')
    rng=random.Random(seed);atoms=[(v,) for v in VARIABLES]+[('lit',0,1),('lit',1,1),('lit',1,2),('lit',2,1)]
    trees=atoms+[(op,a,b) for op,a,b in product(('add','sub','mul'),atoms,atoms)]
    for _ in range(budget):trees.append((rng.choice(('add','sub','mul')),rng.choice(trees[:154]),rng.choice(trees[:154])))
    pool=[Polynomial(t) for t in dict.fromkeys(trees)];groups={}
    for a in pool:
        signature=tuple(a.evaluate(p) for p in ((0,0,0),(1,1,1),(1,2,3),(2,3,1)))
        groups.setdefault(signature,[]).append(a)
    pairs=[(a,rows[0]) for rows in groups.values() for a in rows[1:]];rng.shuffle(pairs);pairs=pairs[:budget*3//4]
    seen={frozenset((a,b)) for a,b in pairs}
    for _ in range(4*budget):
        if len(pairs)>=budget:break
        a,b=rng.sample(pool,2);key=frozenset((a,b))
        if key not in seen:seen.add(key);pairs.append((a,b))
    out={'seed':seed,'budget':budget,'proved':[],'refuted':[],'unknown':[]}
    for a,b in pairs:
        r=classify(a,b)
        if r['status']!='unknown' and not verify(a,b,r):raise RuntimeError('independent proof failure')
        out[r['status']].append(r)
    return out


def rational_law(data,*,budget=64,max_terms=8,degree=3):
    import numpy as np
    from .science import Data
    if not isinstance(data,Data) or type(budget) is not int or not 1<=budget<=128 or type(max_terms) is not int or not 1<=max_terms<=8 or type(degree) is not int or not 1<=degree<=3:raise ValueError('rational law bounds')
    if any(abs(x)<1e-6 for split in (data.train,data.validation,data.test) for coords,_ in split for x in coords):raise ValueError('inverse-feature domain excludes zero')
    n=len(data.names);zero=(0,)*n;terms={zero}
    for d in range(1,degree+1):
        for seq in combinations_with_replacement(range(2*n),d):
            row=[0]*n
            for i in seq:row[i%n]+=1 if i<n else -1
            terms.add(tuple(row))
    terms=sorted(t for t in terms if tuple(sum(t[i]*data.units[i][j] for i in range(n)) for j in range(4))==data.output_unit)
    if not terms:raise ValueError('no dimensionally valid Laurent monomials')
    def matrix(rows):
        x=np.array([r[0] for r in rows],dtype=np.float64)
        a=np.column_stack([np.prod(np.power(x,np.array(t,dtype=int)),axis=1) for t in terms])
        if not np.isfinite(a).all():raise ValueError('nonfinite features')
        return a,np.array([r[1] for r in rows],dtype=float)
    a,y=matrix(data.train);b,v=matrix(data.validation);norm=np.linalg.norm(a,axis=0);remaining=set(i for i,z in enumerate(norm) if z>1e-15);selected=[];history=[];res=y.copy();attempts=0
    for _ in range(min(budget,max_terms,len(remaining),len(y))):
        if not remaining:break
        j=min(remaining,key=lambda i:(-abs(float(a[:,i]@res))/norm[i],i));remaining.remove(j);selected.append(j);attempts+=1
        coeff,_,rank,_=np.linalg.lstsq(a[:,selected]/norm[selected],y,rcond=1e-12);coeff=coeff/norm[selected]
        if rank!=len(selected) or not np.isfinite(coeff).all():selected.pop();continue
        res=y-a[:,selected]@coeff;err=float(np.sqrt(np.mean((v-b[:,selected]@coeff)**2)));history.append((err,selected.copy(),coeff.tolist()))
        if float(np.linalg.norm(res))<=1e-12*max(1.,float(np.linalg.norm(y))):break
    if not history:raise ValueError('no full rank fit')
    error,idx,coeff=min(history,key=lambda h:(h[0],len(h[1]),h[1]));test,truth=matrix(data.test);rmse=float(np.sqrt(np.mean((truth-test[:,idx]@coeff)**2)))
    return {'schema':'omega-laurent-law-v1','data_sha256':data.digest(),'library_size':len(terms),'attempts':attempts,'terms':[{'exponents':list(terms[j]),'coefficient':c} for j,c in zip(idx,coeff)],'validation_rmse':error,'test_rmse':rmse,'test_evaluations':1,'domain':'nonzero measured coordinates; empirical relation, not a proof of a physical law'}
