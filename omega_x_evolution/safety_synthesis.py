"""Candidate-specific safety obligations under immutable binary64 interpreter policy.

Interval proof certificates cover all binary64 input pairs in [0,1]^2.
Conservative outward rounding can yield unknown; unknown never grants admission.
The modal model is a small finite transition system, not a general modal prover.
"""
from __future__ import annotations
import argparse
import ast
from functools import lru_cache
import hashlib
import json
import math
from .engine import Expression

LIMIT = 1e12
MAX_DEPTH = 8
POLICY = 'omega-binary64-totality-v1'


def _wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_wire(value).encode()).hexdigest()


def _out(values):
    if not all(math.isfinite(v) for v in values):
        raise ArithmeticError('nonfinite interval')
    return math.nextafter(min(values), -math.inf), math.nextafter(max(values), math.inf)


def _interval(node, box, obligations, path='root'):
    if isinstance(node, ast.Constant):
        v=float(node.value); bounds=(v,v)
    elif isinstance(node, ast.Name):
        bounds=box[0 if node.id=='x' else 1]
    elif isinstance(node, ast.UnaryOp):
        a=_interval(node.operand,box,obligations,path+'.0')
        bounds=(-a[1],-a[0]) if isinstance(node.op,ast.USub) else a
    elif isinstance(node, ast.BinOp):
        a=_interval(node.left,box,obligations,path+'.0'); b=_interval(node.right,box,obligations,path+'.1')
        if isinstance(node.op,ast.Add): bounds=_out((a[0]+b[0],a[1]+b[1]))
        elif isinstance(node.op,ast.Sub): bounds=_out((a[0]-b[1],a[1]-b[0]))
        elif isinstance(node.op,ast.Mult): bounds=_out(tuple(x*y for x in a for y in b))
        elif isinstance(node.op,ast.Div):
            if b[0]<=0<=b[1]: raise ArithmeticError('denominator may contain zero')
            obligations.append([path,'nonzero',list(b)])
            bounds=_out(tuple(x/y for x in a for y in b))
        else: raise ArithmeticError('unsupported operation')
    elif isinstance(node,ast.Call):
        args=[_interval(n,box,obligations,path+f'.{i}') for i,n in enumerate(node.args)]
        a=args[0]
        if node.func.id=='abs': bounds=(0. if a[0]<=0<=a[1] else min(map(abs,a)),max(map(abs,a)))
        elif node.func.id=='min': bounds=(min(a[0],args[1][0]),min(a[1],args[1][1]))
        elif node.func.id=='max': bounds=(max(a[0],args[1][0]),max(a[1],args[1][1]))
        else: raise ArithmeticError('unsupported call')
    else: raise ArithmeticError('unsupported node')
    if not all(math.isfinite(v) and abs(v)<=LIMIT for v in bounds):
        raise ArithmeticError('intermediate bound unproved')
    obligations.append([path,'finite_bound',list(bounds)])
    return bounds


def modal_invariant(*,bypass=False):
    """Check AG(admitted -> proved AND empirical AND performance AND audit).

    All reachable states of the immutable abstract fail-closed admission protocol.
    bypass exists only as a negative-control test of the model checker.
    """
    initial=(0,False,False,False,False)
    seen=set();pending=[initial]
    while pending:
        s=pending.pop()
        if s in seen:continue
        seen.add(s);stage,*flags=s
        if stage==5 and not all(flags):return False
        if 0<=stage<4:
            pending.append((-1,*flags)) # failed or unknown -> reject
            f=list(flags);f[stage]=True
            pending.append((stage+1,*f))
        elif stage==4:pending.append((5,*flags))
        if bypass and stage==0:pending.append((5,*flags))
    return True


@lru_cache(maxsize=512)
def _prove(code):
    digest=hashlib.sha256(code.encode()).hexdigest()
    outcome={'policy':POLICY,'source_sha256':digest,'proved':False,'boxes':0,'obligations':0,'digest':'','reason':'unproved'}
    try:e=Expression(code)
    except ValueError:
        outcome['reason']='invalid AST';return _wire(outcome)
    todo=[(((0.,1.),(0.,1.)),0)]; transcript=hashlib.sha256(); boxes=0; count=0
    while todo:
        box,depth=todo.pop(); obligations=[]
        try:_interval(e.tree,box,obligations)
        except (ArithmeticError,OverflowError) as exc:
            if depth==MAX_DEPTH:
                outcome.update(boxes=boxes,obligations=count,reason=str(exc));return _wire(outcome)
            dim=depth%2; lo,hi=box[dim];mid=(lo+hi)/2
            for span in ((mid,hi),(lo,mid)):
                child=list(box);child[dim]=span;todo.append((tuple(child),depth+1))
            continue
        transcript.update(_wire([box,obligations]).encode());boxes+=1;count+=len(obligations)
    outcome.update(proved=modal_invariant(),boxes=boxes,obligations=count,digest=transcript.hexdigest(),reason='proved totality and intermediate bounds')
    return _wire(outcome)


def prove(code):
    if not isinstance(code,str) or len(code)>2048:raise ValueError('invalid source')
    return json.loads(_prove(code))


def verify(code,certificate):
    return isinstance(certificate,dict) and certificate.get('proved') is True and certificate==prove(code)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('expression');a=p.parse_args()
    result=prove(a.expression);print(json.dumps(result,indent=2));return 0 if result['proved'] else 1


if __name__=='__main__':raise SystemExit(main())
