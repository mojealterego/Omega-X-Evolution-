"""L11 v71: deterministic conservative comparison of operator-supplied scenarios."""
import itertools
import random

import pytest
from omega_x_evolution.ontos_v69_substrate import PowerComponents, SubstrateScenario
from omega_x_evolution.ontos_v71_energy_pareto import (
    Interval, Workload, Candidate, compare, robustly_dominates,
)

HASH = 'a' * 64
WORK = Workload(HASH, 350_000, 0.99, target_wall_j=15e-9)


def candidate(name, wall_j, time_s, correctness=(.999, .999), *, uncertainty=0.,
              tech='H100_FP8', operations=350_000, fingerprint=HASH, time_uncertainty=0.):
    # Explicit synthetic inputs; eta=1, all non-core rails declared as zero.
    scenario = SubstrateScenario(tech, time_s,
        PowerComponents(core_w=wall_j/time_s, memory_w=0., adc_w=0., dac_w=0.,
                        network_w=0., host_w=0., cooling_w=0., auxiliary_w=0.),
        psu_efficiency=1., uncertainty_rel=uncertainty)
    return Candidate(name, fingerprint, operations, scenario,
                     Interval(*correctness), runtime_uncertainty_rel=time_uncertainty)


def test_v71_source_scenario_report_keeps_physical_measurement_false():
    r = compare(WORK, (candidate('A', 10e-9, .01),))
    a = r['candidates'][0]
    assert a['energy_j']['upper'] == pytest.approx(10e-9)
    assert a['energy_target'] == 'PASS_SCENARIO'
    assert a['eligibility'] == 'PASS_SCENARIO'
    assert r['physical_measurement_verified'] is False
    assert r['source'] == 'OPERATOR_ASSUMED_SCENARIO'
    assert r['robust_frontier'] == ['A']


def test_v71_real_pareto_robust_dominance_three_objectives():
    better = candidate('better', 5e-9, .01, (.999, .999))
    worse = candidate('worse', 8e-9, .02, (.995, .995))
    assert robustly_dominates(better, worse) is True
    assert robustly_dominates(worse, better) is False
    r = compare(WORK, (worse, better))
    assert r['robust_frontier'] == ['better']
    assert r['robust_dominated'] == ['worse']


def test_v71_accuracy_tradeoff_must_not_be_dominated():
    fast = candidate('fast', 6e-9, .01, (.995, .995))
    correct = candidate('correct', 7e-9, .02, (.999, .999))
    r = compare(WORK, (correct, fast))
    assert r['robust_frontier'] == ['correct', 'fast']


def test_v71_overlap_cannot_claim_definitive_dominance():
    a = candidate('a', 10e-9, .01, (.999, .999), uncertainty=.2)
    b = candidate('b', 11e-9, .012, (.998, .998), uncertainty=.2)
    r = compare(WORK, (a,b))
    assert r['robust_frontier'] == ['a','b']
    assert ['a','b'] in r['energy_overlap_pairs']
    assert r['unique_robust_scenario_leader'] is False


def test_v71_equal_candidates_never_claim_unique_winner():
    r = compare(WORK, (candidate('a', 5e-9, .01), candidate('b', 5e-9, .01)))
    assert r['robust_frontier'] == ['a','b']
    assert r['unique_robust_scenario_leader'] is False


def test_v71_energy_target_three_valued_status():
    yes = candidate('yes', 10e-9, .01, uncertainty=.1)
    no = candidate('no', 30e-9, .01, uncertainty=.1)
    maybe = candidate('maybe', 15e-9, .01, uncertainty=.1)
    x = {y['id']: y for y in compare(WORK,(yes,no,maybe))['candidates']}
    assert x['yes']['energy_target'] == 'PASS_SCENARIO'
    assert x['no']['energy_target'] == 'FAIL_SCENARIO'
    assert x['maybe']['energy_target'] == 'UNKNOWN'


def test_v71_unknown_power_components_are_not_zero():
    p = PowerComponents(core_w=1.)
    incomplete = Candidate('incomplete', HASH, 350000,
                           SubstrateScenario('H100_FP8',1.,p,.9,.1), Interval(.999,.999))
    result = compare(WORK,(incomplete,))
    assert result['candidates'][0]['eligibility'] == 'UNKNOWN'
    assert result['candidates'][0]['energy_j'] is None
    assert result['robust_frontier'] == []
    assert result['unresolved'] == ['incomplete']


def test_v71_unknown_uncertainty_does_not_create_sensitivity_interval():
    p = PowerComponents(1.,0.,0.,0.,0.,0.,0.,0.)
    c = Candidate('no-uncert',HASH,350000,SubstrateScenario('H100_FP8',.01,p,1.,None),Interval(.999,.999))
    r=compare(WORK,(c,))
    assert r['candidates'][0]['energy_j'] is None
    assert r['unresolved'] == ['no-uncert']


def test_v71_correctness_threshold_boundary_and_unknown():
    c1 = candidate('pass', 5e-9,.01, (.99,.991))
    c2 = candidate('fail', 5e-9,.01, (.98,.989))
    c3 = candidate('uncertain', 5e-9,.01, (.98,.999))
    d={x['id']:x for x in compare(WORK,(c1,c2,c3))['candidates']}
    assert d['pass']['correctness_threshold']=='PASS_SCENARIO'
    assert d['fail']['correctness_threshold']=='FAIL_SCENARIO'
    assert d['uncertain']['correctness_threshold']=='UNKNOWN'
    assert d['uncertain']['eligibility']=='UNKNOWN'
    assert d['fail']['eligibility']=='FAIL_SCENARIO'


def test_v71_explicit_equal_workload_mandatory():
    with pytest.raises(ValueError,match='workload'):
        compare(WORK,(candidate('wrong',10e-9,.01,fingerprint='b'*64),))
    with pytest.raises(ValueError,match='operations'):
        compare(WORK,(candidate('wrong',10e-9,.01,operations=349999),))


@pytest.mark.parametrize('bad', [True, -1, 2, float('nan'), float('inf'), 10**400])
def test_v71_accuracy_rejects_invalid(bad):
    with pytest.raises(ValueError): Interval(bad, .99)


@pytest.mark.parametrize('bad', [True, -1, float('inf'), float('nan'), 1000, 10**400])
def test_v71_uncertainty_rejects_invalid(bad):
    with pytest.raises(ValueError):
        Candidate('a',HASH,350000, candidate('temp',10e-9,.01).scenario,
                  Interval(.99,.99),runtime_uncertainty_rel=bad)


def test_v71_reject_duplicate_ids_and_nonempty_bound():
    with pytest.raises(ValueError,match='duplicate'):
        compare(WORK, (candidate('x',5e-9,.01),candidate('x',6e-9,.01)))
    with pytest.raises(ValueError): compare(WORK,())
    with pytest.raises(ValueError): compare(WORK, tuple(candidate(f'x{i}',5e-9,.01) for i in range(65)))


def test_v71_total_energy_not_core_energy():
    p = PowerComponents(1.,2.,3.,4.,5.,6.,7.,8.)
    c = Candidate('whole', HASH,350000,SubstrateScenario('H100_FP8', .1,p,.8,.1),Interval(.999,.999))
    r = compare(WORK,(c,))['candidates'][0]
    assert r['energy_j']['central'] == pytest.approx(((1+2+3+4+5+6)/.8+7+8)*.1)
    assert r['energy_j']['central'] != pytest.approx(.1)


def test_v71_runtime_uncertainty_propagated():
    c = candidate('c', 10e-9, .01,time_uncertainty=.1)
    r = compare(WORK,(c,))['candidates'][0]
    assert r['duration_s']['lower'] == pytest.approx(.009)
    assert r['duration_s']['upper'] == pytest.approx(.011)


def test_v71_input_permutation_invariance_seeded():
    rng = random.Random(71)
    cases = [candidate(f'c{i}',(3+i)*1e-9,(1+i)*.01,(.99+i*.001, .99+i*.001)) for i in range(7)]
    reference=compare(WORK,tuple(cases))
    for _ in range(50):
        shuffled=cases.copy(); rng.shuffle(shuffled)
        actual=compare(WORK,tuple(shuffled))
        assert actual == reference


def test_v71_bound_validation_and_mutation_tampering_fail_closed():
    with pytest.raises(ValueError): Interval(.6, .5)
    with pytest.raises(ValueError): Interval(-1., .5)
    c = candidate('c',10e-9,.01)
    object.__setattr__(c,'operations',350001)
    with pytest.raises(ValueError): compare(WORK,(c,))


def test_v71_actual_large_int_input_rejected_before_float_cast():
    huge = 10 ** 400
    with pytest.raises(ValueError): Workload(HASH, huge, .99)
    with pytest.raises(ValueError): Workload(HASH, 350000, huge)
    with pytest.raises(ValueError): Workload(HASH, 350000, .99, huge)


def test_v71_indeterminate_correctness_cannot_dominate_other_candidate():
    borderline = candidate('borderline', 1e-9, .001, (.98, 1.))
    ordinary = candidate('ordinary', 5e-9, .01, (.991, .991))
    r = compare(WORK, (borderline, ordinary))
    assert r['robust_frontier'] == ['ordinary']
    assert r['unresolved'] == ['borderline']
    assert r['unique_robust_scenario_leader'] is False


def test_v71_interval_strictness_prevents_invented_winner():
    a = candidate('a', 8e-9, .01, (.999, .999), uncertainty=.2)
    b = candidate('b', 8.5e-9, .01, (.999, .999), uncertainty=.2)
    assert robustly_dominates(a,b) is False
    assert robustly_dominates(b,a) is False
    assert compare(WORK,(a,b))['unique_robust_scenario_leader'] is False
