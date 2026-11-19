"""Function-extensional proof bridge for pure modular IR.
Native whole-domain SMT, optional real Lean kernel acceptance (fail closed).
No general HOL theorem prover or compiler-equivalence claim.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from .polyglot import Program, ATOMS
from . import proof_kernel, bitproof


def lean_source(a,b):
    if not isinstance(a,Program) or not isinstance(b,Program):raise ValueError('pure typed programs required')
    def emit(t):
        if t[0] in ('x','y'):return t[0]
        if t[0]=='lit':return f'({t[1]} : BitVec 16)'
        op={'add':'+','sub':'-','mul':'*','xor':'^^^','and':'&&&','or':'|||'}[t[0]]
        return f'({emit(t[1])} {op} {emit(t[2])})'
    return ('import Std.Tactic.BVDecide\nset_option maxHeartbeats 200000\n'
            'theorem omega_extensional_equivalence :\n'
            f'  (fun (x y : BitVec 16) => {emit(a.tree)}) =\n'
            f'  (fun (x y : BitVec 16) => {emit(b.tree)}) := by\n'
            '  funext x y\n  bv_decide\n')


def check_lean(a,b,*,timeout=30):
    if type(timeout) is not int or not 1<=timeout<=60:raise ValueError('Lean timeout')
    src=lean_source(a,b);result={'backend':'lean','source_sha256':hashlib.sha256(src.encode()).hexdigest(),'proved':False}
    binary=shutil.which('lean')
    if not binary:return {**result,'status':'unavailable'}
    with tempfile.TemporaryDirectory(prefix='omega-hol-') as temp:
        p=Path(temp)/'Proof.lean';p.write_text(src,encoding='ascii')
        try:
            v=subprocess.run([binary,'--version'],capture_output=True,timeout=5,check=True)
            r=subprocess.run([binary,str(p)],cwd=temp,capture_output=True,timeout=timeout)
        except (OSError,subprocess.SubprocessError):return {**result,'status':'failed-or-timeout'}
        ok=r.returncode==0 and not r.stdout.strip() and not r.stderr.strip()
        return {**result,'status':'checked' if ok else 'rejected','proved':ok,'version':v.stdout.decode(errors='replace')[:256].strip()}


def prove(a,b,*,require_lean=False):
    if not isinstance(a,Program) or not isinstance(b,Program) or type(require_lean) is not bool:raise ValueError('proof input')
    ring=proof_kernel.certify(a,b);checked=proof_kernel.verify_certificate(a,b,ring)
    try:solver=bitproof.prove(a,b)
    except (OSError,RuntimeError,subprocess.SubprocessError):solver={'status':'unavailable-or-timeout','proved':False}
    # SAT contradicts a native proof; fail closed even if a second proof passed.
    native=solver['status']!='sat' and (checked or solver['proved'])
    lean=check_lean(a,b) if require_lean else None
    return {'schema':'omega-extensional-proof-v1','proved':native and (not require_lean or lean['proved']),
            'left':json.loads(json.dumps(a.tree)),'right':json.loads(json.dumps(b.tree)),
            'ring_certificate':ring if checked else None,'solver':solver,'lean':lean,'require_lean':require_lean,
            'domain_size':2**32,'definition':'pure function equality over BitVec 16 × BitVec 16'}


def optimize(reference,*,budget=16,require_lean=False):
    if not isinstance(reference,Program) or type(budget) is not int or not 1<=budget<=32 or type(require_lean) is not bool:raise ValueError('proof search bounds')
    def trees(t):
        yield t
        if len(t)==3:
            yield from trees(t[1]);yield from trees(t[2])
    pool=set(trees(reference.tree))|set(ATOMS)
    candidates=sorted((Program(t) for t in pool),key=lambda p:(p.size,repr(p.tree))); attempts=0
    for p in candidates:
        if p.size>=reference.size or attempts>=budget:break
        attempts+=1;proof=prove(reference,p,require_lean=require_lean)
        if proof['proved']:
            return {'promoted':True,'selected':json.loads(json.dumps(p.tree)),'attempts':attempts,'proof':proof}
    return {'promoted':False,'selected':json.loads(json.dumps(reference.tree)),'attempts':attempts,'proof':None}


def verify(report):
    """Reconstruct a positive decision; arbitrary supplied evidence is not trusted."""
    try:
        if report.get('proved') is not True:return False
        fresh=prove(bitproof._program(report['left']),bitproof._program(report['right']),require_lean=report['require_lean'])
        return fresh==report
    except (ValueError,TypeError,KeyError,IndexError):return False
