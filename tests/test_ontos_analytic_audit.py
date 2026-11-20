import math
import pytest
from omega_x_evolution.ontos_analytic_audit import analytic_audit, stopping_audit


@pytest.mark.parametrize('seed', [0, 42, 9274, 2**32-1])
def test_analytic_fit_reproduces_fixed_reference(seed):
    r = analytic_audit(seed)
    assert r == analytic_audit(seed)
    assert r['svd_reconstruction_error'] < 1e-12
    assert r['rls_batch_difference'] < 1e-10
    assert r['holdout_mse'] < 1e-10
    assert r['holdout_mse'] < r['persistence_mse']
    assert r['train_rows'] == 64 and r['holdout_rows'] == 32
    assert r['gradient_steps'] == 0


@pytest.mark.parametrize('seed', [-1, True, 2**32, 1.0])
def test_seed_boundary(seed):
    with pytest.raises(ValueError):
        analytic_audit(seed)


def test_optional_stopping_exact_null():
    r = stopping_audit()
    assert r['paths'] == 4096
    assert r['null_mass'] == 1
    assert r['terminal_mean'] == 1
    assert 0 < r['crossing_probability'] <= .05
    assert r['floor_terminal_mean'] > 1
    assert math.isclose(r['ville_bound'], .05)
