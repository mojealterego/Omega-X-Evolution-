"""Bounded finite Kripke/CTL model checker; no candidate code execution.
All transitions are total. Formulae are typed tuples, never evaluated as code.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Mapping
from types import MappingProxyType
import hashlib
import json

MAX_STATES=512
MAX_FORMULA=1024

@dataclass(frozen=True)
class Model:
    transitions: tuple[tuple[str, tuple[str, ...]], ...]
    labels: Mapping[str, tuple[str, ...]]

    def __post_init__(self):
        if type(self.transitions) is not tuple or not 1<=len(self.transitions)<=MAX_STATES:
            raise ValueError('model size')
        def name(s):return type(s) is str and 0<len(s)<=128
        if any(type(r) is not tuple or len(r)!=2 or not name(r[0]) or type(r[1]) is not tuple or not 1<=len(r[1])<=MAX_STATES or not all(name(x) for x in r[1]) or len(set(r[1]))!=len(r[1]) for r in self.transitions):
            raise ValueError('transition shape')
        states={r[0] for r in self.transitions}
        if len(states)!=len(self.transitions) or any(not set(r[1])<=states for r in self.transitions):raise ValueError('unknown or duplicate state')
        if not isinstance(self.labels,Mapping) or not set(self.labels)<=states or any(type(v) is not tuple or len(v)>MAX_FORMULA or not all(name(a) for a in v) or len(set(v))!=len(v) for v in self.labels.values()):raise ValueError('label shape')
        object.__setattr__(self,'labels',MappingProxyType(dict(self.labels)))


def check(model:Model, formula:tuple, initial:str)->dict:
    """Bottom-up satisfaction sets; least/greatest fixed points for temporal CTL.
    Certificate digest commits the exact denotation for each subformula.
    It is a model-check, not arbitrary HOL.
    """
    if not isinstance(model,Model):raise ValueError('typed model')
    edges=dict(model.transitions); universe=set(edges)
    if initial not in universe:raise ValueError('unknown initial state')
    trace=[];count=0
    def pre(s,all_paths):return {x for x,ys in edges.items() if (set(ys)<=s if all_paths else bool(set(ys)&s))}
    def fix(start,step):
        for _ in range(len(universe)+1):
            nxt=step(start)
            if nxt==start:return nxt
            start=nxt
        raise RuntimeError('fixed point not converged')
    def calc(f,depth=0):
        nonlocal count
        count+=1
        if count>MAX_FORMULA or depth>32 or type(f) is not tuple or not f or type(f[0]) is not str:raise ValueError('formula bound')
        op=f[0]
        if op=='atom' and len(f)==2 and type(f[1]) is str and 0<len(f[1])<=128:
            s={x for x in universe if f[1] in model.labels.get(x,())}
        elif op in ('not','AX','EX','AF','EF','AG','EG') and len(f)==2:
            a=calc(f[1],depth+1)
            if op=='not':s=universe-a
            elif op in ('AX','EX'):s=pre(a,op=='AX')
            elif op in ('AF','EF'):s=fix(set(),lambda z:a|pre(z,op=='AF'))
            else:s=fix(set(universe),lambda z:a&pre(z,op=='AG'))
        elif op in ('and','or','implies','AU','EU') and len(f)==3:
            a,b=calc(f[1],depth+1),calc(f[2],depth+1)
            if op=='and':s=a&b
            elif op=='or':s=a|b
            elif op=='implies':s=(universe-a)|b
            else:s=fix(set(),lambda z:b|(a&pre(z,op=='AU')))
        else:raise ValueError('unsupported formula')
        trace.append([op,sorted(s)])
        return s
    sat=calc(formula)
    # Digest commits all subformula satisfaction results, inputs and starting world.
    wire=json.dumps([sorted(model.transitions),sorted(model.labels.items()),formula,initial,trace],sort_keys=True,separators=(',',':'))
    return {'holds':initial in sat,'satisfying_worlds':sorted(sat),'worlds':len(universe),'subformulas':count,'digest':hashlib.sha256(wire.encode()).hexdigest()}


class _Exhausted(Exception):
    pass


def prove_k(formula:tuple, *, budget:int=8192)->dict:
    """Decide bounded propositional normal modal logic K by analytic tableaux.

    Negate the theorem, convert to negation normal form, saturate Boolean
    constraints and construct one successor per diamond carrying every box
    constraint. Arbitrary K frames may have dead ends. A closed tableau proves
    validity on *all* Kripke frames; an open one returns a checked countermodel.
    Resource exhaustion is UNKNOWN, never valid.
    """
    if type(budget) is not int or not 1<=budget<=8192:raise ValueError('tableau budget')
    count=0
    def nnf(f,neg=False,depth=0):
        nonlocal count
        count+=1
        if count>MAX_FORMULA or depth>32 or type(f) is not tuple or not f or type(f[0]) is not str:raise ValueError('formula bound')
        op=f[0]
        if op=='atom' and len(f)==2 and type(f[1]) is str and 0<len(f[1])<=128:return ('neg' if neg else 'pos',f[1])
        if op=='not' and len(f)==2:return nnf(f[1],not neg,depth+1)
        if op in ('box','diamond') and len(f)==2:return (('diamond' if op=='box' else 'box') if neg else op,nnf(f[1],neg,depth+1))
        if op in ('and','or','implies') and len(f)==3:
            if op=='implies':return ('and' if neg else 'or',nnf(f[1],not neg,depth+1),nnf(f[2],neg,depth+1))
            return (('or' if op=='and' else 'and') if neg else op,nnf(f[1],neg,depth+1),nnf(f[2],neg,depth+1))
        raise ValueError('unsupported K formula')
    root=nnf(formula,True);nodes=0;transcript=hashlib.sha256()
    def record(tag,body):
        transcript.update(json.dumps([tag,body],sort_keys=True,separators=(',',':')).encode());transcript.update(b'\n')
    def solve(forms,depth=0):
        nonlocal nodes
        nodes+=1
        if nodes>budget or depth>256:raise _Exhausted
        # Saturate every conjunction before branching; discard duplicate formulas.
        pending=list(forms);closed=set()
        while pending:
            it=pending.pop()
            if it in closed:continue
            if it[0]=='and':pending.extend(it[1:]);continue
            closed.add(it)
        record('branch',sorted(closed))
        positives={f[1] for f in closed if f[0]=='pos'}
        negatives={f[1] for f in closed if f[0]=='neg'}
        if positives&negatives:
            record('contradiction',sorted(positives&negatives));return None
        ors=sorted(f for f in closed if f[0]=='or')
        if ors:
            choice=ors[0];rest=closed-{choice}
            for alternative in choice[1:]:
                result=solve((*sorted(rest),alternative),depth+1)
                if result is not None:return result
            record('closed-disjunction',choice);return None
        boxes=sorted(f[1] for f in closed if f[0]=='box');children=[]
        for diamond in sorted(f[1] for f in closed if f[0]=='diamond'):
            child=solve((*boxes,diamond),depth+1)
            if child is None:
                record('closed-successor',diamond);return None
            children.append(child)
        record('open-world',sorted(positives));return (sorted(positives),children)
    try:tree=solve((root,))
    except _Exhausted:return {'status':'unknown','proved':False,'tableau_nodes':min(nodes,budget),'digest':transcript.hexdigest(),'countermodel':None}
    model=None
    if tree is not None:
        worlds=[]
        def flatten(world):
            if len(worlds)>=MAX_STATES:raise _Exhausted
            ident=len(worlds);row={'atoms':world[0],'successors':[]};worlds.append(row)
            row['successors']=[flatten(child) for child in world[1]];return ident
        try:flatten(tree)
        except _Exhausted:return {'status':'unknown','proved':False,'tableau_nodes':nodes,'digest':transcript.hexdigest(),'countermodel':None}
        model={'root':0,'worlds':worlds}
        # Independently evaluate the ORIGINAL formula in the finite witness.
        def truth(f,w):
            op=f[0]
            if op=='atom':return f[1] in worlds[w]['atoms']
            if op=='not':return not truth(f[1],w)
            if op=='and':return truth(f[1],w) and truth(f[2],w)
            if op=='or':return truth(f[1],w) or truth(f[2],w)
            if op=='implies':return not truth(f[1],w) or truth(f[2],w)
            if op=='box':return all(truth(f[1],i) for i in worlds[w]['successors'])
            return any(truth(f[1],i) for i in worlds[w]['successors'])
        if truth(formula,0):raise RuntimeError('invalid tableau countermodel')
    return {'status':'valid' if tree is None else 'countermodel','proved':tree is None,'tableau_nodes':nodes,'digest':transcript.hexdigest(),'countermodel':model}


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--formula',required=True,help='JSON modal K formula: atom/not/and/or/implies/box/diamond')
    p.add_argument('--budget',type=int,default=8192);a=p.parse_args()
    if len(a.formula)>65536:p.error('formula size')
    def decode(f,depth=0):
        if depth>32 or type(f) is not list or len(f)>3:raise ValueError('formula shape')
        return tuple(decode(x,depth+1) if type(x) is list else x for x in f)
    try:result=prove_k(decode(json.loads(a.formula)),budget=a.budget)
    except (ValueError,TypeError,RecursionError) as exc:p.error(str(exc))
    print(json.dumps(result,indent=2));return 0 if result['proved'] else 1

if __name__=='__main__':raise SystemExit(main())
