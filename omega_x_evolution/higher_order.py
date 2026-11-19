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
from .polyglot import Program, ATOMS, _validated_tree
from . import proof_kernel, bitproof, lrat


from .lean_native import lean_source, lean_core_source, check_lean


def isabelle_source(a,b):
    """Generate a closed HOL function equality; never accept supplied theory text."""
    a,b=Program(_validated_tree(a)),Program(_validated_tree(b))
    def emit(t):
        if t[0] in ('x','y'):return t[0]
        if t[0]=='lit':return f'({t[1]} :: 16 word)'
        op={'add':'+','sub':'-','mul':'*','xor':'XOR','and':'AND','or':'OR'}[t[0]]
        return f'({emit(t[1])} {op} {emit(t[2])})'
    return (r'''theory Omega_Proof
  imports "HOL-Library.Word"
begin
context includes bit_operations_syntax
begin
lemma omega_extensional_equivalence:
''' +
            f'  "(\\<lambda>(x::16 word) (y::16 word). {emit(a.tree)}) = (\\<lambda>(x::16 word) (y::16 word). {emit(b.tree)})"\n'
            '  apply (rule ext)+\n  by (simp add: algebra_simps; (smt (z3)))\nend\nend\n')


def check_isabelle(a,b,*,timeout=120):
    if type(timeout) is not int or not 1<=timeout<=600:raise ValueError('Isabelle timeout')
    src=isabelle_source(a,b);result={'backend':'isabelle','source_sha256':hashlib.sha256(src.encode()).hexdigest(),'proved':False}
    binary=shutil.which('isabelle')
    if not binary:return {**result,'status':'unavailable'}
    import os,signal
    with tempfile.TemporaryDirectory(prefix='omega-isabelle-') as temp:
        path=Path(temp);(path/'Omega_Proof.thy').write_text(src,encoding='ascii')
        (path/'ROOT').write_text('session Omega_Proof = "HOL-Library" +\n  options [document = false, quick_and_dirty = false]\n  theories Omega_Proof\n',encoding='ascii')
        try:
            version=subprocess.run([binary,'version'],capture_output=True,timeout=10,check=True).stdout.decode(errors='replace')[:256].strip()
            with (path/'build.log').open('wb') as out:
                cmd=[binary,'build','-D',temp,'-j','1','-o','threads=1','-o','quick_and_dirty=false']
                proc=subprocess.Popen(cmd,cwd=temp,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
                try:code=proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    try:os.killpg(proc.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    proc.wait();return {**result,'status':'timeout','version':version}
            with (path/'build.log').open('rb') as f:log=f.read(1_048_577)
            ok=code==0 and len(log)<=1_048_576
            return {**result,'status':'checked' if ok else 'rejected','proved':ok,'version':version}
        except (OSError,subprocess.SubprocessError):return {**result,'status':'failed-or-timeout'}


def prove(a,b,*,require_lean=False,require_isabelle=False,require_lrat=False):
    if any(type(flag) is not bool for flag in (require_lean,require_isabelle,require_lrat)):raise ValueError('proof input')
    a,b=Program(_validated_tree(a)),Program(_validated_tree(b))
    ring=proof_kernel.certify(a,b);checked=proof_kernel.verify_certificate(a,b,ring)
    try:solver=bitproof.prove(a,b)
    except (OSError,RuntimeError,subprocess.SubprocessError):solver={'status':'unavailable-or-timeout','proved':False}
    # SAT contradicts a native proof; fail closed even if a second proof passed.
    native=solver['status']!='sat' and (checked or solver['proved'])
    lean=check_lean(a,b) if require_lean else None
    isa=check_isabelle(a,b) if require_isabelle else None
    result={'schema':'omega-extensional-proof-v1','proved':native and (not require_lean or lean['proved']) and (not require_isabelle or isa['proved']),
            'left':json.loads(json.dumps(a.tree)),'right':json.loads(json.dumps(b.tree)),
            'ring_certificate':ring if checked else None,'solver':solver,'lean':lean,'require_lean':require_lean,
            'domain_size':2**32,'definition':'pure function equality over BitVec 16 × BitVec 16'}
    if require_isabelle:result.update(isabelle=isa,require_isabelle=True)
    if require_lrat:
        certificate=lrat.prove(a,b)
        result.update(lrat=certificate,require_lrat=True,proved=result['proved'] and certificate['proved'])
    return result


def optimize(reference,*,budget=16,require_lean=False,require_isabelle=False,require_lrat=False):
    if not isinstance(reference,Program) or type(budget) is not int or not 1<=budget<=32 or type(require_lean) is not bool or type(require_isabelle) is not bool or type(require_lrat) is not bool:raise ValueError('proof search bounds')
    reference=Program(_validated_tree(reference))
    def trees(t):
        yield t
        if len(t)==3:
            yield from trees(t[1]);yield from trees(t[2])
    pool=set(trees(reference.tree))|set(ATOMS)
    candidates=sorted((Program(t) for t in pool),key=lambda p:(p.size,repr(p.tree))); attempts=0
    for p in candidates:
        if p.size>=reference.size or attempts>=budget:break
        attempts+=1;proof=prove(reference,p,require_lean=require_lean,require_isabelle=require_isabelle,require_lrat=require_lrat)
        if proof['proved']:
            return {'promoted':True,'selected':json.loads(json.dumps(p.tree)),'attempts':attempts,'proof':proof}
    return {'promoted':False,'selected':json.loads(json.dumps(reference.tree)),'attempts':attempts,'proof':None}


def verify(report, *, require_lrat=False):
    """Replay evidence; external policy can require a native LRAT certificate."""
    if type(require_lrat) is not bool:raise ValueError('proof policy')
    try:
        if type(report) is not dict or report.get('proved') is not True:return False
        if require_lrat and report.get('require_lrat') is not True:return False
        a,b=bitproof._program(report['left']),bitproof._program(report['right'])
        fresh=prove(a,b,require_lean=report['require_lean'],require_isabelle=report.get('require_isabelle',False))
        if 'require_lrat' in report or 'lrat' in report:
            if report.get('require_lrat') is not True or not fresh['proved'] or not lrat.verify(a,b,report['lrat']):return False
            fresh.update(require_lrat=True,lrat=report['lrat'])
        return fresh==report
    except (ValueError,TypeError,KeyError,IndexError):return False
