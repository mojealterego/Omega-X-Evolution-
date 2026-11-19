"""Independent whole-domain checker using exact rational endpoint arithmetic.
The trusted arithmetic interpreter accepts only binary64 expressions. This
checker does not use the interval generator, its transcript or mutable rules.
"""
from __future__ import annotations
import ast
from fractions import Fraction
import math


def check(code, rules, *, depth_limit=8):
    from .engine import Expression
    tree=Expression(code).tree
    def rounded(values):
        return (math.nextafter(float(min(values)),-math.inf),math.nextafter(float(max(values)),math.inf))
    def walk(n,box,records):
        if isinstance(n,ast.Constant):a=b=float(n.value)
        elif isinstance(n,ast.Name):a,b=box[n.id]
        elif isinstance(n,ast.UnaryOp):
            a,b=walk(n.operand,box,records)
            if isinstance(n.op,ast.USub):a,b=-b,-a
        elif isinstance(n,ast.Call):
            args=[walk(x,box,records) for x in n.args];a,b=args[0]
            if n.func.id=='abs':a,b=(0. if a<=0<=b else min(abs(a),abs(b))),max(abs(a),abs(b))
            elif n.func.id=='min':a,b=min(a,args[1][0]),min(b,args[1][1])
            elif n.func.id=='max':a,b=max(a,args[1][0]),max(b,args[1][1])
            else:raise ArithmeticError('unknown function')
        elif isinstance(n,ast.BinOp):
            l,r=walk(n.left,box,records),walk(n.right,box,records)
            u,v=map(Fraction,l); w,z=map(Fraction,r)
            if isinstance(n.op,ast.Add):a,b=rounded((u+w,v+z))
            elif isinstance(n.op,ast.Sub):a,b=rounded((u-z,v-w))
            elif isinstance(n.op,ast.Mult):a,b=rounded((u*w,u*z,v*w,v*z))
            elif isinstance(n.op,ast.Div):
                if w<=0<=z:raise ArithmeticError('zero denominator')
                records[('nonzero',ast.unparse(n.right))]=r
                a,b=rounded((u/w,u/z,v/w,v/z))
            else:raise ArithmeticError('unknown operator')
        else:raise ArithmeticError('unknown AST')
        if not math.isfinite(a) or not math.isfinite(b) or min(a,b)<-1e12 or max(a,b)>1e12:raise ArithmeticError('invalid range')
        records[('finite_bound',ast.unparse(n))]=(a,b)
        return a,b
    stack=[({'x':(0.,1.),'y':(0.,1.)},0)];bounds={};boxes=0
    while stack:
        box,d=stack.pop();records={}
        try:walk(tree,box,records)
        except (ArithmeticError,ValueError,OverflowError):
            if d==depth_limit:return False,boxes
            axis='xy'[d%2];lo,hi=box[axis];mid=(lo+hi)/2
            for span in ((mid,hi),(lo,mid)):stack.append(({**box,axis:span},d+1))
            continue
        boxes+=1
        for k,(a,b) in records.items():
            l,h=bounds.get(k,(a,b));bounds[k]=min(a,l),max(b,h)
    for r in rules:
        k=(r['kind'],r['expression']);bound=bounds.get(k)
        if bound is None or not r['lower']<=bound[0]<=bound[1]<=r['upper']:return False,boxes
        if r['kind']=='nonzero' and r['lower']<=0<=r['upper']:return False,boxes
    return True,boxes
