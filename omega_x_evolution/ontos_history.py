"""Offline bitemporal record and fixed prototype diagnostics; no operational memory writes."""
from dataclasses import dataclass
import math
import re
from .ontos_metabolism import number


def token(x):
    return type(x) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,64}',x) is not None


def timestamp(x):
    return type(x) is int and 0<=x<2**63


@dataclass(frozen=True)
class Fact:
    tenant: str
    subject: str
    predicate: str
    value: str
    start: int
    end: int
    tx: int
    source: str

    def __post_init__(self):
        if not (all(token(x) for x in (self.tenant,self.subject,self.predicate,self.source)) and type(self.value) is str and 1<=len(self.value)<=256 and all(timestamp(x) for x in (self.start,self.end,self.tx)) and self.start<self.end):
            raise ValueError('fact contract')


@dataclass(frozen=True)
class Snapshot:
    facts: tuple[Fact,...]

    def __post_init__(self):
        f=self.facts
        if type(f) is not tuple or len(f)>256 or any(type(x) is not Fact for x in f) or len(set(f))!=len(f):
            raise ValueError('history bounds or duplicate')
        for i,a in enumerate(f):
            for b in f[:i]:
                if (a.tenant,a.subject,a.predicate,a.tx)==(b.tenant,b.subject,b.predicate,b.tx) and max(a.start,b.start)<min(a.end,b.end):
                    raise ValueError('ambiguous transaction')


def view(snapshot,tenant,subject,predicate,valid_at,known_at):
    if type(snapshot) is not Snapshot or not all(token(x) for x in (tenant,subject,predicate)) or not all(timestamp(x) for x in (valid_at,known_at)):
        raise ValueError('view contract')
    rows=(f for f in snapshot.facts if (f.tenant,f.subject,f.predicate)==(tenant,subject,predicate) and f.start<=valid_at<f.end and f.tx<=known_at)
    return max(rows,key=lambda f:f.tx,default=None)


def unit(v,n=None):
    if type(v) is not tuple or not 1<=len(v)<=64 or (n is not None and len(v)!=n) or not all(number(x,-1,1) for x in v):
        raise ValueError('vector contract')
    norm=math.hypot(*v)
    if norm<1e-12: raise ValueError('zero vector')
    return tuple(x/norm for x in v)


def prototype_audit(reference,patterns,observed,*,max_noise):
    """Measure one fixed Hopfield energy step and cosine deviation, without returning recall state."""
    r=unit(reference); q=unit(observed,len(r))
    if type(patterns) is not tuple or not 1<=len(patterns)<=64 or not number(max_noise,0,2):
        raise ValueError('prototype contract')
    p=tuple(unit(x,len(r)) for x in patterns)
    dot=lambda a,b: math.fsum(x*y for x,y in zip(a,b))
    def logits(x): return tuple(5*dot(v,x) for v in p)
    def energy(x):
        z=logits(x); m=max(z)
        return .5*dot(x,x)-(m+math.log(math.fsum(math.exp(v-m) for v in z)))/5
    z=logits(q); m=max(z); w=tuple(math.exp(v-m) for v in z); total=math.fsum(w)
    rec=tuple(math.fsum(a*v[i] for a,v in zip(w,p))/total for i in range(len(q)))
    noise=min(2.,max(0.,1-dot(r,q)))
    return {'quarantined':noise>max_noise,'cosine_deviation':noise,'energy_before':energy(q),'energy_after':energy(rec)}


def vsa_noise_audit(a,b,flips):
    """Bipolar binding/unbinding on fixed vectors; emit error metrics only."""
    if (type(a) is not tuple or type(b) is not tuple or not 1<=len(a)==len(b)<=512
            or any(type(x) is not int or x not in (-1,1) for x in a+b)
            or type(flips) is not tuple or len(flips)>len(a)
            or any(type(i) is not int or not 0<=i<len(a) for i in flips) or len(set(flips))!=len(flips)):
        raise ValueError('VSA diagnostic bounds')
    mask=set(flips)
    bound=tuple(x*y*(-1 if i in mask else 1) for i,(x,y) in enumerate(zip(a,b)))
    restored=tuple(x*y for x,y in zip(bound,b))
    return {'bit_error_rate':sum(x!=y for x,y in zip(a,restored))/len(a),'cosine':sum(x*y for x,y in zip(a,restored))/len(a)}
