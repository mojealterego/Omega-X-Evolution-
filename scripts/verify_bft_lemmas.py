#!/usr/bin/env python3
"""Check the fixed arithmetic BFT obligations and actual leader rotation.

Run only the repository-owned query; no caller-supplied SMT source.
"""
from pathlib import Path
import ctypes as C
import ctypes.util
import hashlib
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from omega_x_evolution.bft import leader, MAX_ROUND, MAX_HEIGHT
    name=ctypes.util.find_library('z3')
    if not name:
        raise RuntimeError('libz3 required')
    z=C.CDLL(name);ptr=C.c_void_p
    for n,args,ret in [('Z3_mk_config',[],ptr),('Z3_mk_context',[ptr],ptr),('Z3_del_config',[ptr],None),('Z3_del_context',[ptr],None),('Z3_eval_smtlib2_string',[ptr,C.c_char_p],C.c_char_p)]:
        f=getattr(z,n);f.argtypes=args;f.restype=ret
    cfg=z.Z3_mk_config()
    if not cfg:raise RuntimeError('Z3 configuration failed')
    ctx=z.Z3_mk_context(cfg);z.Z3_del_config(cfg)
    if not ctx:raise RuntimeError('Z3 context failed')
    try:
        q=(ROOT/'docs/omega/BFT_LEMMAS_V36.smt2').read_bytes()
        result=z.Z3_eval_smtlib2_string(ctx,q)
        if result is None:raise RuntimeError('missing solver output')
        r=result.decode('ascii').split()
        print('libz3',name,'query SHA256',hashlib.sha256(q).hexdigest(),'results',r)
        if r!=['unsat','unsat']:raise RuntimeError('incomplete BFT lemma proof')
    finally:z.Z3_del_context(ctx)
    cases=0
    for n in range(1,17):
        for f in range((n-1)//3+1):
            for h in range(1,MAX_HEIGHT+1):
                for start in range(MAX_ROUND-f):
                    state={'members':list(range(n)),'height':h}
                    rot=[leader(state,start+j) for j in range(f+1)]
                    if len(set(rot))!=f+1:raise RuntimeError('non-distinct leader rotation')
                    cases+=1
    print('actual leader() distinct-rotation cases:',cases)


if __name__=='__main__':
    main()
