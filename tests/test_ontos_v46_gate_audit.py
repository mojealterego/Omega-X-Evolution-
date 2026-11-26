from fractions import Fraction as F
from itertools import product

import pytest

from omega_x_evolution.ontos_v46_gate_audit import audit_gate, family_alpha_bound


def brute(p, win, loss, horizon, threshold):
    out = F(0)
    for path in product((False, True), repeat=horizon):
        wealth = F(1)
        hit = False
        for success in path:
            wealth *= win if success else loss
            hit |= wealth >= threshold
        if hit:
            out += p**sum(path)*(1-p)**(horizon-sum(path))
    return out


@pytest.mark.parametrize('p,win,loss', [(F(1,2),F(3,2),F(1,2)),(F(1,4),F(2),F(2,3)),(F(1,2),F(43,20),F(1,4)),(F(0),F(2),F(0)),(F(1),F(2),F(0))])
@pytest.mark.parametrize('horizon', [1,4,8])
def test_exact_crossing_matches_independent_enumeration(p,win,loss,horizon):
    result = audit_gate(p,win,loss,horizon=horizon,threshold=F(3))
    assert result.crossing_probability == brute(p,win,loss,horizon,F(3))
    assert result.terminal_expectation == (p*win+(1-p)*loss)**horizon
    assert result.mass == 1


def test_source_hopfield_multiplier_invalid_at_half_null():
    r = audit_gate(F(1,2),F(43,20),F(1,4),horizon=240)
    assert r.maximum_null == F(15,38)
    assert r.expected_multiplier == F(6,5)
    assert not r.conditional_supermartingale
    assert r.crossing_probability > F(1,20)
    assert r.ville_bound is None


def test_four_successes_cross_source_gate():
    r = audit_gate(F(1,2),F(43,20),F(1,4),horizon=4)
    assert r.crossing_probability == F(1,16)


def test_valid_gate_and_family_budget():
    r = audit_gate(F(1,2),F(3,2),F(1,2),horizon=240)
    assert r.conditional_supermartingale and r.ville_bound == F(1,20)
    assert r.crossing_probability <= r.ville_bound
    assert family_alpha_bound((F(1,600),)*30) == F(1,20)
    assert family_alpha_bound((F(1,20),)*30) == 1


@pytest.mark.parametrize('kwargs', [dict(horizon=0),dict(horizon=241),dict(horizon=True),dict(threshold=F(1)),dict(threshold=20),dict(threshold=F(1000001))])
def test_invalid_bounds(kwargs):
    opts = {'horizon': 4, **kwargs}
    with pytest.raises(ValueError):
        audit_gate(F(1,2),F(3,2),F(1,2),**opts)


@pytest.mark.parametrize('args', [(0.5,F(2),F(0)),(F(2),F(2),F(0)),(F(1,2),F(1),F(0)),(F(1,2),F(2),F(-1)),(F(1,2),F(2),F(2)),(F(1,10**10),F(2),F(0))])
def test_invalid_factors(args):
    with pytest.raises(ValueError):
        audit_gate(*args,horizon=4)


@pytest.mark.parametrize('values', [(),(F(-1),),(0.05,), (F(1,20),)*257])
def test_invalid_family(values):
    with pytest.raises(ValueError):
        family_alpha_bound(values)


def test_source_wealth_floor_is_not_a_supermartingale_even_under_fair_factors():
    from omega_x_evolution.ontos_v46_gate_audit import floored_step_expectation
    w = F(1,20)
    assert floored_step_expectation(w,F(1,2),F(3,2),F(1,2),floor=w) == F(1,16)
    assert floored_step_expectation(w,F(1,2),F(3,2),F(1,2),floor=F(0)) == w
