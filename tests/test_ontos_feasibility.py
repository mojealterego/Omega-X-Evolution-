from fractions import Fraction
from itertools import product

import pytest

from omega_x_evolution.ontos_feasibility import feasibility, replay_audit


def test_validation_conflict_exact():
    r = feasibility(7200, 751, target=Fraction(91,100), recall=Fraction(99,100))
    assert r['required_correct'] == 6552
    assert r['required_ood_abstentions'] == 744
    assert r['max_correct'] == 6456
    assert r['shortfall'] == 96
    assert r['status'] == 'INCOMPATIBLE'
    assert not r['release_authorized']


def test_bound_matches_exhaustive_count_model():
    for n in range(1,9):
        for ood in range(n+1):
            for target, recall in product((Fraction(0),Fraction(1,2),Fraction(1)),repeat=2):
                r = feasibility(n,ood,target=target,recall=recall)
                candidates = [c for a in range(ood+1) for c in range(n-a+1) if a >= recall*ood]
                assert r['max_correct'] == max(candidates)
                assert (r['status'] == 'COUNT_FEASIBLE') == any(c >= target*n for c in candidates)


@pytest.mark.parametrize('n,o,t,r', [(0,0,Fraction(1),Fraction(1)),(5,6,Fraction(1),Fraction(1)),(True,0,Fraction(1),Fraction(1)),(5,True,Fraction(1),Fraction(1)),(5,0,1.,Fraction(1)),(5,0,Fraction(2),Fraction(1)),(5,1,Fraction(1),Fraction(-1)),(10**9,0,Fraction(1),Fraction(1))])
def test_invalid_counts_and_targets(n,o,t,r):
    with pytest.raises(ValueError): feasibility(n,o,target=t,recall=r)


def test_actual_replay_audit_exact_counts_and_reproducibility():
    r=replay_audit((30000,30073),horizon=120)
    assert r==replay_audit((30000,30073),horizon=120)
    assert not r['release_authorized']
    for arm in r['arms'].values():
        clean,ood=arm['clean'],arm['ood']
        assert sum(clean.values())+sum(ood.values())==240
        assert clean['harm']==ood['harm']==0
        assert arm['observed_accuracy_ceiling']['denominator']==240
        assert arm['observed_accuracy_ceiling']['numerator']==240-clean['abstain']-ood['abstain']
    assert r['arms']['baseline']['ood_total']==r['arms']['guarded']['ood_total']


@pytest.mark.parametrize('seeds,horizon', [((1,1),240),((True,2),240),([],240),((1,2),0),((1,2),241)])
def test_replay_bounds(seeds,horizon):
    with pytest.raises(ValueError): replay_audit(seeds,horizon=horizon)
