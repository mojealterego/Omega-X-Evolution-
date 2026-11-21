"""Offline finite i4 IR certificate generation and independent truth-table verification.

Full proof is only over two four-bit inputs (16**2=256 cases). A digest is
not an external signature or Lean/SMT certificate. Other semantics are UNKNOWN.
No source code execution, compiler, network, or safety-token issuance.
"""
from __future__ import annotations

import hashlib
import json
from .ontos_v47_pure_ir import PureIR, evaluate

_SCHEMA = 'ontos-i4-exhaustive-certificate-v1'
_SEMANTICS = 'ontos-pure-i4-v1'


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True, allow_nan=False).encode('ascii')).hexdigest()


def _nodes(t: tuple) -> int:
    op=t[0]
    return 1 if op in ('x','y','lit') else 1+_nodes(t[1])+_nodes(t[2])


def _oracle(tree: tuple, x: int, y: int) -> int:
    """Independent i4 interpreter using Python's native modular operators."""
    op = tree[0]
    if op=='x':return x
    if op=='y':return y
    if op=='lit':return tree[1]
    p=_oracle(tree[1],x,y);q=_oracle(tree[2],x,y)
    return {
        'add': lambda: (p+q)%16,
        'sub': lambda: (p-q)%16,
        'mul': lambda: (p*q)%16,
        'xor': lambda: p^q,
        'and': lambda: p&q,
        'or': lambda: p|q,
    }[op]()


def _inputs():
    return ((x,y) for x in range(16) for y in range(16))


def certify(left: PureIR, right: PureIR, *, max_cases: int = 256,
            semantics: str = _SEMANTICS) -> dict:
    if (type(left) is not PureIR or type(right) is not PureIR
            or type(max_cases) is not int or not 1<=max_cases<=256
            or type(semantics) is not str or not 1<=len(semantics)<=64):
        raise ValueError('bounded certificate inputs')
    # PureIR is frozen, but object.__setattr__ permits explicit tampering.
    left.__post_init__();right.__post_init__()
    base={'schema':_SCHEMA,'semantics':semantics,
          'left_sha256':_sha(left.tree),'right_sha256':_sha(right.tree),
          'mdl_nodes_before':_nodes(left.tree),'mdl_nodes_after':_nodes(right.tree),
          'cases':0,'counterexample':None,'truth_sha256':None}
    if semantics != _SEMANTICS:
        result={**base,'status':'UNKNOWN_SEMANTICS'}
    else:
        transcript=[];counterexample=None
        for i,(x,y) in enumerate(_inputs()):
            if i>=max_cases:break
            left_value=evaluate(left,x,y)
            right_value=evaluate(right,x,y)
            transcript.append((x,y,left_value,right_value))
            if left_value!=right_value:
                counterexample=(x,y)
                break
        tested=len(transcript)
        if counterexample is not None:
            status='FAIL_COUNTEREXAMPLE'
        elif tested==256:
            status='PASS_EXHAUSTIVE'
        else:
            status='UNKNOWN_BOUND'
        result={**base,'cases':tested,'status':status,
                'counterexample':counterexample,'truth_sha256':_sha(transcript)}
    return {**result,'certificate_sha256':_sha(result)}


def verify_certificate(left: PureIR, right: PureIR, certificate: dict) -> bool:
    """Recompute from immutable semantics, never trust a candidate's PASS flag."""
    try:
        if (type(left) is not PureIR or type(right) is not PureIR
                or type(certificate) is not dict
                or set(certificate) != {
                    'schema','semantics','left_sha256','right_sha256',
                    'mdl_nodes_before','mdl_nodes_after','cases',
                    'counterexample','truth_sha256','status','certificate_sha256'}
                or certificate.get('status')!='PASS_EXHAUSTIVE'
                or certificate.get('schema')!=_SCHEMA
                or certificate.get('semantics')!=_SEMANTICS
                or type(certificate.get('cases')) is not int or certificate['cases']!=256):
            return False
        left.__post_init__();right.__post_init__()
        # Independently verify the witness against a separate interpreter.
        if any(_oracle(left.tree,x,y)!=evaluate(left,x,y) or
               _oracle(right.tree,x,y)!=evaluate(right,x,y) or
               _oracle(left.tree,x,y)!=_oracle(right.tree,x,y)
               for x,y in _inputs()):
            return False
        transcript=[(x,y,_oracle(left.tree,x,y),_oracle(right.tree,x,y)) for x,y in _inputs()]
        expected={'schema':_SCHEMA,'semantics':_SEMANTICS,
                  'left_sha256':_sha(left.tree),'right_sha256':_sha(right.tree),
                  'mdl_nodes_before':_nodes(left.tree),'mdl_nodes_after':_nodes(right.tree),
                  'cases':256,'counterexample':None,'truth_sha256':_sha(transcript),
                  'status':'PASS_EXHAUSTIVE'}
        return certificate == {**expected,'certificate_sha256':_sha(expected)}
    except (ValueError,TypeError,KeyError,IndexError,RecursionError):
        return False
