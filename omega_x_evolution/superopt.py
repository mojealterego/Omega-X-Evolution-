"""Conservative binary64 AST rewrites and hash-consed evaluation IR.

The contract is float inputs in [0,1], including signed zero. No reassociation,
zero annihilation or division cancellation. Formal verification is a later gate.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import json
import math
import struct

from .engine import Expression, BIN, FUN


@dataclass(frozen=True)
class Instruction:
    op: str
    args: tuple[int,...] = ()
    literal: float = 0.


@dataclass(frozen=True)
class IR:
    instructions: tuple[Instruction,...]
    operations: int

    def evaluate(self,x,y):
        if type(x) is not float or type(y) is not float or not all(math.isfinite(v) and 0<=v<=1 for v in (x,y)):
            raise ValueError('binary64 ratios outside domain')
        values=[]
        for ins in self.instructions:
            args=[values[i] for i in ins.args]; op=ins.op
            if op=='const': value=ins.literal
            elif op=='x': value=x
            elif op=='y': value=y
            elif op=='neg': value=-args[0]
            elif op=='pos': value=args[0]
            elif op in ('abs','min','max'): value=FUN[op][1](*args)
            elif op in _BIN: value=BIN[_BIN[op]](*args)
            else: raise ValueError('invalid IR instruction')
            if not math.isfinite(value) or abs(value)>1e12: raise ValueError('numeric bound exceeded')
            values.append(value)
        return values[-1]


_BIN={'add':ast.Add,'sub':ast.Sub,'mul':ast.Mult,'div':ast.Div}
_NAMES={cls:name for name,cls in _BIN.items()}


def compile_ir(source):
    expr=Expression(source); instructions=[]; memo={}
    def visit(n):
        if isinstance(n,ast.Constant): op='const'; args=(); literal=float(n.value)
        elif isinstance(n,ast.Name): op=n.id; args=(); literal=0.
        elif isinstance(n,ast.BinOp): op=_NAMES[type(n.op)]; args=(visit(n.left),visit(n.right)); literal=0.
        elif isinstance(n,ast.UnaryOp): op='neg' if isinstance(n.op,ast.USub) else 'pos'; args=(visit(n.operand),); literal=0.
        elif isinstance(n,ast.Call): op=n.func.id; args=tuple(visit(a) for a in n.args); literal=0.
        else: raise ValueError('unvalidated AST')
        # Include float bits (signed-zero) in the structural key.
        key=(op,args,struct.pack('>d',literal))
        if key not in memo:
            memo[key]=len(instructions);instructions.append(Instruction(op,args,literal))
        return memo[key]
    root=visit(expr.tree)
    # A root matching an earlier subexpression is impossible for finite ASTs,
    # but assert the internal topological/root invariant explicitly.
    if root!=len(instructions)-1: raise ValueError('invalid IR root')
    return IR(tuple(instructions),sum(i.op not in ('const','x','y') for i in instructions))


def one(node): return isinstance(node,ast.Constant) and type(node.value) in (int,float) and node.value==1


def negative_one(node): return isinstance(node,ast.UnaryOp) and isinstance(node.op,ast.USub) and one(node.operand)


class Rewrite(ast.NodeTransformer):
    def visit_UnaryOp(self,node):
        node=self.generic_visit(node)
        if isinstance(node.op,ast.UAdd): return node.operand
        if isinstance(node.op,ast.USub) and isinstance(node.operand,ast.UnaryOp) and isinstance(node.operand.op,ast.USub): return node.operand.operand
        return node
    def visit_BinOp(self,node):
        node=self.generic_visit(node)
        if isinstance(node.op,(ast.Mult,ast.Div)) and one(node.right): return node.left
        if isinstance(node.op,ast.Mult) and one(node.left): return node.right
        if isinstance(node.op,(ast.Mult,ast.Div)) and negative_one(node.right): return ast.UnaryOp(op=ast.USub(),operand=node.left)
        if isinstance(node.op,ast.Mult) and negative_one(node.left): return ast.UnaryOp(op=ast.USub(),operand=node.right)
        return node
    def visit_Call(self,node):
        node=self.generic_visit(node)
        if node.func.id=='abs' and isinstance(node.args[0],ast.Call) and node.args[0].func.id=='abs': return node.args[0]
        if node.func.id=='abs' and isinstance(node.args[0],ast.UnaryOp) and isinstance(node.args[0].op,ast.USub): return ast.Call(func=node.func,args=[node.args[0].operand],keywords=[])
        if node.func.id in ('min','max') and ast.dump(node.args[0])==ast.dump(node.args[1]): return node.args[0]
        return node


@dataclass(frozen=True)
class Optimization:
    source: str
    original_operations: int
    optimized_operations: int
    original_nodes: int
    optimized_nodes: int
    ir: IR


def optimize(source):
    original=Expression(source)
    tree=ast.parse(source,mode='eval')
    # Rewrites strictly decrease the validated cost when accepted. Iterate to
    # a bounded fixed point (a newly created unary node can expose another rule).
    for _ in range(32):
        before=ast.dump(tree)
        tree=Rewrite().visit(tree)
        if ast.dump(tree)==before: break
    rewritten=ast.unparse(ast.fix_missing_locations(tree))
    try: candidate=Expression(rewritten)
    except ValueError: candidate=original;rewritten=source
    if (candidate.operations,candidate.count)>=(original.operations,original.count): candidate=original;rewritten=source
    return Optimization(rewritten,original.operations,candidate.operations,original.count,candidate.count,compile_ir(rewritten))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('expression');a=p.parse_args();r=optimize(a.expression)
    print(json.dumps({'source':r.source,'original_operations':r.original_operations,'optimized_operations':r.optimized_operations,'original_nodes':r.original_nodes,'optimized_nodes':r.optimized_nodes,'ir_operations':r.ir.operations,'ir_instructions':len(r.ir.instructions)},indent=2))


if __name__=='__main__': main()
