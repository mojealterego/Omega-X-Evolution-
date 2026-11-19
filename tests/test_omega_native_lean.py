"""Native Lean checks (bootstrap core and full standard library)."""
import hashlib
import os
import shutil

import pytest

from omega_x_evolution import higher_order, proof_kernel
from omega_x_evolution.polyglot import Program

X, Y = ('x',), ('y',)
ZERO = ('lit', 0)
CASES = [
    (('sub', ('add', X, Y), Y), X),
    (('add', X, ZERO), X),
    (('sub', Y, Y), ZERO),
    (('add', X, ('add', ('lit', 65535), ('lit', 1))), ('add', X, ZERO)),
]

@pytest.mark.parametrize('left,right', CASES)
def test_core_source_uses_real_bitvec_and_extensional_theorem(left, right):
    source = higher_order.lean_core_source(Program(left), Program(right))
    assert 'import Init.Data.BitVec.BasicAux' in source
    assert 'theorem omega_extensional_equivalence' in source
    assert 'BitVec 16' in source and 'sorry' not in source and 'axiom ' not in source


def test_core_source_refuses_unsupported_operation():
    assert higher_order.lean_core_source(Program(('xor', X, Y)), Program(X)) is None


@pytest.mark.parametrize('left,right', CASES)
def test_native_lean_core_proof_when_requested(left, right):
    a, b = Program(left), Program(right)
    result = higher_order.check_lean(a, b)
    if os.environ.get('OMEGA_LEAN_CORE_NATIVE') == '1':
        assert shutil.which('lean'), 'native Lean requested but unavailable'
        assert result['proved'] and result['strategy'] == 'core-addsub', result
        assert result['source_sha256'] == hashlib.sha256(higher_order.lean_core_source(a,b).encode()).hexdigest()
        assert proof_kernel.check_lean(a,b)['proved']
    elif shutil.which('lean') is None:
        assert result['status'] == 'unavailable' and not result['proved']
    else:
        assert isinstance(result['proved'], bool)


def test_native_lean_rejects_false_equivalence():
    result = higher_order.check_lean(Program(X), Program(Y), core_only=True)
    assert not result['proved'], result
    if os.environ.get('OMEGA_LEAN_CORE_NATIVE') == '1':
        assert result['status'] == 'rejected' and result['strategy'] == 'core-addsub'


def test_native_source_binding_refuses_unchecked_kernel():
    from omega_x_evolution.simulation_contracts import check_source
    a, b = Program(CASES[0][0]), Program(X)
    source = higher_order.lean_source(a,b)
    assert check_source('lean', source, a,b)['proved']
    with pytest.raises(ValueError):
        check_source('lean', source.replace('debug.skipKernelTC false', 'debug.skipKernelTC true'), a,b)


def test_native_higher_order_required_gate():
    if os.environ.get('OMEGA_LEAN_CORE_NATIVE') == '1':
        a,b=Program(CASES[0][0]),Program(X)
        report=higher_order.prove(a,b,require_lean=True)
        assert report['proved'],report
        assert higher_order.verify(report)
