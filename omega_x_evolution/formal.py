"""Proof gate for conservative AST rewrites and ordered DAG compilation.

Trusted base: CPython binary64 operations under round-to-nearest ties-to-even,
restricted Expression semantics, Z3 IEEE-754 theory, and this small checker.
No equivalence is asserted for arbitrary algebraic rewrites.
"""
from __future__ import annotations

import argparse
import ast
import ctypes
import ctypes.util
from dataclasses import asdict, dataclass
from functools import lru_cache
import hashlib
import json
import struct
import subprocess
import sys

from .engine import Expression
from .superopt import IR, optimize

RULES = {
    'positive': '(= a a)',
    'double_negative': '(= (fp.neg (fp.neg a)) a)',
    'multiply_one': '(and (= (fp.mul RNE a one) a) (= (fp.mul RNE one a) a))',
    'divide_one': '(= (fp.div RNE a one) a)',
    'multiply_negative_one': '(and (= (fp.mul RNE a negone) (fp.neg a)) (= (fp.mul RNE negone a) (fp.neg a)))',
    'divide_negative_one': '(= (fp.div RNE a negone) (fp.neg a))',
    'absolute_idempotent': '(= (fp.abs (fp.abs a)) (fp.abs a))',
    'absolute_negative': '(= (fp.abs (fp.neg a)) (fp.abs a))',
    # Python min/max retain the first argument on equality (including zero).
    'identical_min_max': '(and (= (ite (fp.lt a a) a a) a) (= (ite (fp.gt a a) a a) a))',
}


def _query() -> str:
    head = '''(set-option :timeout 3000)
(declare-const a (_ FloatingPoint 11 53))
(define-fun one () (_ FloatingPoint 11 53) ((_ to_fp 11 53) #x3ff0000000000000))
(define-fun negone () (_ FloatingPoint 11 53) (fp.neg one))
(assert (and (not (fp.isNaN a)) (not (fp.isInfinite a))))
'''
    return '\n'.join(head + f'(assert (not {rule})) (check-sat) (reset)' for rule in RULES.values())


def _native_solver() -> None:
    # Run only fixed, module-authored SMT-LIB in an isolated child; no user SMT.
    name = ctypes.util.find_library('z3')
    if not name:
        raise RuntimeError('Z3 shared library required (libz3)')
    z = ctypes.CDLL(name)
    p = ctypes.c_void_p
    for n, args, ret in [('Z3_mk_config', [], p), ('Z3_mk_context', [p], p),
                         ('Z3_del_config', [p], None), ('Z3_del_context', [p], None),
                         ('Z3_eval_smtlib2_string', [p, ctypes.c_char_p], ctypes.c_char_p)]:
        fn = getattr(z, n); fn.argtypes = args; fn.restype = ret
    cfg = z.Z3_mk_config()
    if not cfg: raise RuntimeError('Z3 configuration failed')
    ctx = z.Z3_mk_context(cfg); z.Z3_del_config(cfg)
    if not ctx: raise RuntimeError('Z3 context failed')
    try:
        result = z.Z3_eval_smtlib2_string(ctx, _query().encode('ascii'))
        if result is None: raise RuntimeError('Z3 returned no result')
        print(result.decode('ascii'), end='')
    finally:
        z.Z3_del_context(ctx)


@lru_cache(maxsize=1)
def _rule_results() -> tuple[str, ...]:
    child = subprocess.run([sys.executable, '-m', __name__ if __name__ != '__main__' else 'omega_x_evolution.formal', '--internal-rules'],
                           check=True, text=True, capture_output=True, timeout=35)
    results = tuple(child.stdout.split())
    if len(results) != len(RULES) or any(r not in ('unsat', 'sat', 'unknown') for r in results):
        raise RuntimeError('invalid solver output')
    return results


def prove_rules() -> dict[str, str]:
    return dict(zip(RULES, _rule_results()))


_OPS = {ast.Add:'add', ast.Sub:'sub', ast.Mult:'mul', ast.Div:'div', ast.UAdd:'pos', ast.USub:'neg'}
_ONE = ('const', struct.pack('>d',1.).hex())
_NEG_ONE = ('neg', _ONE)


def _term(node: ast.AST) -> tuple:
    if isinstance(node, ast.Constant): return ('const', struct.pack('>d', float(node.value)).hex())
    if isinstance(node, ast.Name): return (node.id,)
    if isinstance(node, ast.BinOp): return (_OPS[type(node.op)], _term(node.left), _term(node.right))
    if isinstance(node, ast.UnaryOp): return (_OPS[type(node.op)], _term(node.operand))
    if isinstance(node, ast.Call): return (node.func.id, *(_term(a) for a in node.args))
    raise ValueError('unsupported term')


def _normal(term: tuple) -> tuple:
    op = term[0]
    if op in ('const','x','y'): return term
    a = _normal(term[1]); b = _normal(term[2]) if len(term)==3 else None
    if op == 'pos': return a
    if op == 'neg' and a[0]=='neg': return a[1]
    if op in ('mul','div') and b==_ONE: return a
    if op=='mul' and a==_ONE: return b
    if op in ('mul','div') and b==_NEG_ONE: return _normal(('neg',a))
    if op=='mul' and a==_NEG_ONE: return _normal(('neg',b))
    if op=='abs':
        if a[0]=='abs': return a
        if a[0]=='neg': return _normal(('abs',a[1]))
    if op in ('min','max') and a==b: return a
    return (op,a,b) if b is not None else (op,a)


@dataclass(frozen=True)
class Certificate:
    proved: bool
    source_sha256: str
    target_sha256: str
    rule_digest: str
    reason: str


def certify(source: str, target: str) -> Certificate:
    left = _normal(_term(Expression(source).tree)); right = _normal(_term(Expression(target).tree))
    rules = prove_rules()
    passed = set(rules)==set(RULES) and all(r=='unsat' for r in rules.values()) and left==right
    digest = lambda s: hashlib.sha256(s.encode()).hexdigest()
    return Certificate(passed,digest(source),digest(target),digest(_query()),
                       'same proved normal form' if passed else 'not proved by the bounded rule system')


def verify_ir(source: str, ir: IR) -> bool:
    """Check exact ordered first-occurrence postorder CSE, including literal bits."""
    if not isinstance(ir,IR): return False
    def visit(t):
        if t in indices: return indices[t]
        args = () if t[0] in ('const','x','y') else tuple(visit(x) for x in t[1:])
        index = len(expected); indices[t]=index
        expected.append((t[0],args,t[1] if t[0]=='const' else '0000000000000000'))
        return index
    indices = {}; expected = []
    root = visit(_term(Expression(source).tree))
    try:
        actual = [(i.op,i.args,struct.pack('>d',i.literal).hex()) for i in ir.instructions]
        return root==len(expected)-1 and actual==expected and ir.operations==sum(t[0] not in ('const','x','y') for t in expected)
    except (AttributeError,TypeError,ValueError,OverflowError,struct.error): return False


class ProofError(RuntimeError):
    """An optimization could not satisfy the formal gate."""


def verified_optimize(source: str):
    result=optimize(source)
    if not certify(source,result.source).proved or not verify_ir(result.source,result.ir):
        raise ProofError("optimizer certificate rejected")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',nargs='?'); parser.add_argument('--target'); parser.add_argument('--rules',action='store_true')
    parser.add_argument('--internal-rules',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.internal_rules: _native_solver(); return
    if args.rules: print(json.dumps(prove_rules(),indent=2)); return
    if args.source is None: parser.error('source is required')
    opt=optimize(args.source); target=args.target if args.target is not None else opt.source
    from .superopt import compile_ir
    result=asdict(certify(args.source,target)); result['ir_verified']=verify_ir(target,compile_ir(target))
    print(json.dumps(result,indent=2))
    if not result['proved'] or not result['ir_verified']: raise SystemExit(1)


if __name__=='__main__': main()
