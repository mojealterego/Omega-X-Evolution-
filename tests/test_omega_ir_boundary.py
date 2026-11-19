"""Regression: reject invalid IR at the point of evaluation/code generation."""
import pytest
from omega_x_evolution.polyglot import Program, evaluate, emit, verify_backends, LANGUAGES


def forged(tree):
    program = Program(('x',))
    object.__setattr__(program, 'tree', tree)
    return program


@pytest.mark.parametrize('language', LANGUAGES)
def test_omega_ir_001_reject_source_literal(language):
    with pytest.raises(ValueError):
        emit(forged(('lit', 'x')), language)


@pytest.mark.parametrize('tree', [('lit', True), ('lit', -1), ('lit', 65536),
                                  ('x', 'extra'), ('add', ('x',), ('lit', '1'))])
def test_omega_ir_002_reject_invalid_evaluation(tree):
    with pytest.raises(ValueError):
        evaluate(forged(tree), 0, 0)


def test_omega_ir_003_reject_validation_bypassing_subclass():
    class Unchecked(Program):
        def __post_init__(self):
            pass
    with pytest.raises(ValueError):
        emit(Unchecked(('lit', 'x')), 'python')


def test_omega_ir_004_reject_before_compiler_start(monkeypatch):
    # This sentinel detects attempted compiler discovery, not a simulated result.
    def forbidden(*args, **kwargs):
        pytest.fail('invalid IR reached compiler discovery')
    monkeypatch.setattr('omega_x_evolution.polyglot.shutil.which', forbidden)
    with pytest.raises(ValueError):
        verify_backends(forged(('lit', '0')), ((0, 0),))


def test_omega_ir_005_reject_excess_depth():
    tree = ('x',)
    for _ in range(9):
        tree = ('add', tree, ('lit', 1))
    with pytest.raises(ValueError):
        emit(forged(tree), 'python')
