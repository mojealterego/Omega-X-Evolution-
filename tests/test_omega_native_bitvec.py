"""Native BitVec lemma route: no SAT, no replacement semantic definitions."""
import hashlib
import os
import shutil
import pytest
from omega_x_evolution import lean_native, higher_order
from omega_x_evolution.polyglot import Program

X,Y,Z,O=('x',),('y',),('lit',0),('lit',1)
CASES = [
    (('mul',X,O), X),
    (('mul',Z,Y), Z),
    (('mul',X,Y), ('mul',Y,X)),
    (('xor',X,X), Z),
    (('and',X,X), X),
    (('or',X,Z), X),
    (('xor',('or',X,Z),X), Z),
    (('mul',X,('add',Y,O)), ('add',('mul',X,Y),X)),
]

@pytest.mark.parametrize('left,right',CASES)
def test_bitvec_source_all_operators(left,right):
    src=lean_native.lean_bitvec_source(Program(left),Program(right))
    assert 'import Init.Data.BitVec.Basic' in src
    assert 'BitVec 16' in src and 'sorry' not in src and 'axiom ' not in src
    assert 'debug.skipKernelTC false' in src

@pytest.mark.parametrize('left,right',CASES)
def test_native_bitvec_when_requested(left,right):
    if os.environ.get('OMEGA_LEAN_BITVEC_NATIVE')!='1':
        pytest.skip('extended native runtime not requested')
    a,b=Program(left),Program(right)
    result=lean_native.check_lean(a,b,timeout=60)
    assert shutil.which('lean') and result['proved'] and result['strategy']=='bitvec-lemmas',result
    assert result['source_sha256']==hashlib.sha256(lean_native.lean_bitvec_source(a,b).encode()).hexdigest()

@pytest.mark.parametrize('left,right',[(('mul',X,Z),X),(('xor',X,Y),X),(('and',X,Y),('or',X,Y))])
def test_native_bitvec_false_equivalence(left,right):
    if os.environ.get('OMEGA_LEAN_BITVEC_NATIVE')!='1':pytest.skip('extended native runtime not requested')
    result=lean_native.check_lean(Program(left),Program(right),timeout=60)
    assert not result['proved']

def test_required_bitvec_gate():
    if os.environ.get('OMEGA_LEAN_BITVEC_NATIVE')!='1':pytest.skip('extended native runtime not requested')
    a,b=Program(('and',X,X)),Program(X)
    r=higher_order.prove(a,b,require_lean=True)
    assert r['proved'] and higher_order.verify(r)
