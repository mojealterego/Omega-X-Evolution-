"""Finite polynomial lenses, open-set Heyting algebra and NARS evidence diagnostics."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Poly:
    fibers: tuple[int, ...]

    def __post_init__(self):
        if type(self.fibers) is not tuple or not 1<=len(self.fibers)<=64 or any(type(n) is not int or not 0<=n<=64 for n in self.fibers):
            raise ValueError('finite polynomial shape')


@dataclass(frozen=True)
class Lens:
    dom: Poly
    cod: Poly
    positions: tuple[int, ...]
    directions: tuple[tuple[int, ...], ...]

    def __post_init__(self):
        if (type(self.dom) is not Poly or type(self.cod) is not Poly or type(self.positions) is not tuple or type(self.directions) is not tuple
                or len(self.positions)!=len(self.dom.fibers) or len(self.directions)!=len(self.positions)):
            raise ValueError('lens shape')
        for i,(j,row) in enumerate(zip(self.positions,self.directions)):
            if (type(j) is not int or not 0<=j<len(self.cod.fibers) or type(row) is not tuple or len(row)!=self.cod.fibers[j]
                    or any(type(k) is not int or not 0<=k<self.dom.fibers[i] for k in row)):
                raise ValueError('lens fiber map')

    @classmethod
    def identity(cls,p):
        if type(p) is not Poly: raise ValueError('polynomial required')
        return cls(p,p,tuple(range(len(p.fibers))),tuple(tuple(range(n)) for n in p.fibers))

    def compose(self,other):
        if type(other) is not Lens or self.cod!=other.dom: raise ValueError('lens composition types')
        return Lens(self.dom,other.cod,tuple(other.positions[j] for j in self.positions),tuple(tuple(self.directions[i][k] for k in other.directions[j]) for i,j in enumerate(self.positions)))


@dataclass(frozen=True)
class Heyting:
    opens: tuple[int, ...]

    def __post_init__(self):
        o=self.opens
        if (type(o) is not tuple or not 1<=len(o)<=64 or any(type(x) is not int or not 0<=x<256 for x in o)
                or o!=tuple(sorted(set(o))) or o[0]!=0): raise ValueError('finite topology')
        members=set(o)
        if any((a|b) not in members or (a&b) not in members for a in o for b in o): raise ValueError('topology closure')

    def implies(self,a,b):
        if type(a) is not int or type(b) is not int or a not in self.opens or b not in self.opens: raise ValueError('open sets required')
        result=0
        for c in self.opens:
            if (c&a)&~b==0: result|=c
        return result


@dataclass(frozen=True)
class Evidence:
    ident: str
    positive: bool
    weight: int

    def __post_init__(self):
        if type(self.ident) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',self.ident) or type(self.positive) is not bool or type(self.weight) is not int or not 1<=self.weight<=1000:
            raise ValueError('evidence contract')


def revise(rows, *, k=1):
    """Independent evidence IDs are necessary, not proof of independence."""
    if type(rows) is not tuple or len(rows)>256 or any(type(r) is not Evidence for r in rows) or type(k) is not int or not 1<=k<=1000:
        raise ValueError('evidence bounds')
    if len({r.ident for r in rows})!=len(rows): raise ValueError('duplicate evidence')
    pos=sum(r.weight for r in rows if r.positive); neg=sum(r.weight for r in rows if not r.positive); total=pos+neg
    f=pos/total if total else .5; c=total/(total+k)
    return {'frequency':f,'confidence':c,'conflict':bool(pos and neg),'abstain':c<.5 or .4<=f<=.6,'evidence_ids':tuple(sorted(r.ident for r in rows))}


def simulated_mode(ratio,alarm,damage):
    """A source-compatible simulated label, never a capability grant."""
    from .ontos_metabolism import number
    if not number(ratio,0,1) or type(alarm) is not bool or not number(damage,0,1):
        raise ValueError('mode inputs')
    if alarm: return 'IMMUNE_LOCKDOWN'
    if ratio<.30 or damage>.35: return 'SHOCK_REPAIR'
    return 'HOMEOSTATIC'
