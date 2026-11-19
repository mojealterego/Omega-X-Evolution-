"""Whole-domain SMT equivalence of validated, pure u16 programs."""
from __future__ import annotations
import argparse
import ctypes
import ctypes.util
import hashlib
import json
import subprocess
import sys
from .polyglot import Program

OPS={'add':'bvadd','sub':'bvsub','mul':'bvmul','xor':'bvxor','and':'bvand','or':'bvor'}


def _smt(t):
    if t[0] in ('x','y'):return t[0]
    if t[0]=='lit':return f'(_ bv{t[1]} 16)'
    return f'({OPS[t[0]]} {_smt(t[1])} {_smt(t[2])})'


def _query(a,b):
    if not isinstance(a,Program) or not isinstance(b,Program):raise ValueError('validated u16 programs required')
    return f'(set-logic QF_BV)\n(set-option :timeout 3000)\n(declare-const x (_ BitVec 16))\n(declare-const y (_ BitVec 16))\n(assert (distinct {_smt(a.tree)} {_smt(b.tree)}))\n(check-sat)\n'


def _program(v,depth=0):
    if depth>8 or type(v) is not list or not v or len(v)>3:raise ValueError('invalid program wire shape')
    return Program(_tree(v,depth))


def _tree(v,depth=0):
    if depth>8 or type(v) is not list or not v or len(v)>3:raise ValueError('invalid program wire shape')
    return tuple(_tree(x,depth+1) if isinstance(x,list) else x for x in v)


def _solve(a,b):
    name=ctypes.util.find_library('z3')
    if not name:raise RuntimeError('Z3 shared library required')
    z=ctypes.CDLL(name);p=ctypes.c_void_p
    for n,args,restype in [('Z3_mk_config',[],p),('Z3_mk_context',[p],p),('Z3_del_config',[p],None),('Z3_del_context',[p],None),('Z3_eval_smtlib2_string',[p,ctypes.c_char_p],ctypes.c_char_p)]:
        fn=getattr(z,n);fn.argtypes=args;fn.restype=restype
    cfg=z.Z3_mk_config()
    if not cfg:raise RuntimeError('Z3 configuration failed')
    ctx=z.Z3_mk_context(cfg);z.Z3_del_config(cfg)
    if not ctx:raise RuntimeError('Z3 context failed')
    try:
        result=z.Z3_eval_smtlib2_string(ctx,_query(a,b).encode('ascii'))
        if result is None:raise RuntimeError('Z3 output missing')
        return result.decode('ascii').strip()
    finally:z.Z3_del_context(ctx)


def prove(a:Program,b:Program):
    query=_query(a,b)
    child=subprocess.run([sys.executable,'-m','omega_x_evolution.bitproof','--worker'],input=json.dumps([a.tree,b.tree]),capture_output=True,text=True,check=True,timeout=10)
    status=child.stdout.strip()
    if status not in ('sat','unsat','unknown'):raise RuntimeError('invalid solver output')
    return {'status':status,'proved':status=='unsat','domain_size':2**32,'query_sha256':hashlib.sha256(query.encode()).hexdigest(),'semantics':'pure modular u16 IR, not compiler equivalence'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--worker',action='store_true');p.add_argument('--left');p.add_argument('--right');a=p.parse_args()
    if a.worker:
        raw=sys.stdin.read(16385)
        if len(raw)>16384:raise ValueError('wire size')
        l,r=json.loads(raw);print(_solve(_program(l),_program(r)));return
    if not a.left or not a.right or len(a.left)+len(a.right)>16384:p.error('two bounded JSON program trees required')
    print(json.dumps(prove(_program(json.loads(a.left)),_program(json.loads(a.right))),indent=2))


if __name__=='__main__':main()
