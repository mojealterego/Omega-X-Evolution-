"""Checkable polynomial normalization certificates for pure modular u16 IR.
Optional Lean kernel checking of a generated bitvector theorem. No candidate
proof source/tactics are accepted; unknown is not a successful proof.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
from .polyglot import Program,evaluate,MASK
from .bitproof import _program

MAX_TERMS=1024
MAX_WORK=100000

def _trace(p):
    if not isinstance(p,Program):raise ValueError('validated IR required')
    records=[];work=0
    def visit(t):
        nonlocal work
        op=t[0]
        if op=='x':v={(1,0):1}
        elif op=='y':v={(0,1):1}
        elif op=='lit':v={(0,0):t[1]}
        elif op in ('add','sub','mul'):
            a,b=visit(t[1]),visit(t[2]);v={}
            if op=='mul':
                work+=len(a)*len(b)
                if work>MAX_WORK:raise ArithmeticError('proof work cap')
                for (i,j),x in a.items():
                    for (k,l),y in b.items():
                        key=(i+k,j+l);v[key]=(v.get(key,0)+x*y)&MASK
            else:
                work+=len(a)+len(b)
                if work>MAX_WORK:raise ArithmeticError('proof work cap')
                v=dict(a)
                for key,y in b.items():v[key]=(v.get(key,0)+(y if op=='add' else -y))&MASK
        else:raise ArithmeticError('unsupported polynomial operation')
        v={k:c for k,c in v.items() if c}
        if len(v)>MAX_TERMS:raise ArithmeticError('proof term cap')
        records.append([[i,j,c] for (i,j),c in sorted(v.items())]);return v
    visit(p.tree);return records

def _hash(p):return hashlib.sha256(json.dumps(p.tree,separators=(',',':')).encode()).hexdigest()

def certify(a,b):
    if not isinstance(a,Program) or not isinstance(b,Program):raise ValueError('validated IR required')
    base={'schema':'omega-u16-ring-proof-v1','left_sha256':_hash(a),'right_sha256':_hash(b),'proved':False,'left':[],'right':[],'domain_size':2**32}
    try:l,r=_trace(a),_trace(b)
    except ArithmeticError as e:return {**base,'reason':str(e)}
    return {**base,'left':l,'right':r,'proved':l[-1]==r[-1],'reason':'equal modular polynomial' if l[-1]==r[-1] else 'unknown: different normal forms'}

def verify_certificate(a,b,proof):
    """Check supplied postorder witnesses using an independent ring calculator."""
    if not isinstance(a,Program) or not isinstance(b,Program) or type(proof) is not dict:return False
    if set(proof)!={'schema','left_sha256','right_sha256','proved','left','right','domain_size','reason'} or proof.get('proved') is not True:return False
    if proof['schema']!='omega-u16-ring-proof-v1' or proof['left_sha256']!=_hash(a) or proof['right_sha256']!=_hash(b) or proof['domain_size']!=2**32 or proof['reason']!='equal modular polynomial':return False
    def check(p,trace):
        from collections import Counter
        if type(trace) is not list or len(trace)!=p.size:raise ValueError('witness size')
        index=0;work=0
        def walk(t):
            nonlocal index,work
            op=t[0]
            if op=='x':expected={(1,0):1}
            elif op=='y':expected={(0,1):1}
            elif op=='lit':expected={(0,0):t[1]}
            elif op in ('add','sub','mul'):
                x,y=walk(t[1]),walk(t[2]);result=Counter()
                work+=len(x)*len(y) if op=='mul' else len(x)+len(y)
                if work>MAX_WORK:raise ValueError('witness work cap')
                if op=='mul':
                    for key1,v1 in x.items():
                        for key2,v2 in y.items():result[tuple(map(sum,zip(key1,key2)))]+=v1*v2
                else:
                    result.update(x)
                    for key,v in y.items():result[key]+=v if op=='add' else -v
                expected=dict(result)
            else:raise ValueError('unsupported operation')
            expected={key:v%65536 for key,v in expected.items() if v%65536}
            row=trace[index];index+=1
            if type(row) is not list or len(row)>MAX_TERMS or len(expected)>MAX_TERMS:raise ValueError('witness cap')
            if any(type(v) is not list or len(v)!=3 or any(type(k) is not int for k in v) for v in row):raise ValueError('witness type')
            if row!=[[i,j,v] for (i,j),v in sorted(expected.items())]:raise ValueError('invalid witness step')
            return expected
        return walk(p.tree)
    try:return check(a,proof['left'])==check(b,proof['right'])
    except (TypeError,ValueError,ArithmeticError,IndexError):return False

def lean_source(a,b):
    from .lean_native import lean_source as source
    return source(a,b,extensional=False)


def check_lean(a,b,*,timeout=30):
    from .lean_native import check_lean as native_check
    return native_check(a,b,timeout=timeout,extensional=False)


def optimize(reference,*,require_lean=False):
    """Generate smaller subtrees, prove before empirical check/admission."""
    if not isinstance(reference,Program) or type(require_lean) is not bool:raise ValueError('optimizer contract')
    def subtrees(t):
        yield t
        if len(t)==3:
            yield from subtrees(t[1]);yield from subtrees(t[2])
    pool=set(subtrees(reference.tree))|{('lit',0),('lit',1),('x',),('y',)}
    candidates=sorted((Program(t) for t in pool),key=lambda p:(p.size,repr(p.tree)))
    attempts=0;verified=0;chosen=reference;proof=certify(reference,reference);lean=None
    rng=random.Random(42);points=[(0,0),(MASK,MASK),(MASK,1)]+[(rng.randrange(65536),rng.randrange(65536)) for _ in range(32)]
    for p in candidates:
        if p.size>=reference.size:continue
        attempts+=1;c=certify(reference,p)
        if not verify_certificate(reference,p,c):continue
        if require_lean:
            lean=check_lean(reference,p)
            if not lean['proved']:continue
        verified+=1
        if all(evaluate(reference,x,y)==evaluate(p,x,y) for x,y in points):chosen=p;proof=c;break
    return {'selected':json.loads(json.dumps(chosen.tree)),'selected_nodes':chosen.size,'reference_nodes':reference.size,'attempts':attempts,'proved_candidates':verified,'promoted':chosen!=reference,'proof':proof,'lean':lean,'empirical_points':len(points) if chosen!=reference else 0}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--left',default='["sub",["add",["x"],["y"]],["y"]]');p.add_argument('--right');p.add_argument('--lean',action='store_true');a=p.parse_args()
    if len(a.left)+len(a.right or '')>16384:p.error('input cap')
    l=_program(json.loads(a.left));r=_program(json.loads(a.right)) if a.right else None
    out=({'certificate':certify(l,r),**({'lean':check_lean(l,r)} if a.lean else {})} if r else optimize(l,require_lean=a.lean));print(json.dumps(out,indent=2))
if __name__=='__main__':main()
