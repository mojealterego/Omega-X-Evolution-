"""HYP-CP focused tests: known-source conformal math and safe compute-budget routing."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json
import math

import pytest

from omega_x_evolution.hyperion_conformal import (
    Calibration,
    BudgetPolicy,
    calibrate,
    route_budget,
    export_jsonl,
)


def test_hcp_001_unweighted_exact_finite_quantile():
    c = calibrate(tuple(float(i) for i in range(1, 20)), alpha=0.1)
    assert c.threshold == 18.0
    assert c.effective_n == 19.0
    assert c.claim == "CONDITIONAL_EXCHANGEABILITY"
    assert c.release_authorized is False


def test_hcp_002_small_calibration_returns_infinite_quantile():
    c = calibrate(tuple(float(i) for i in range(1, 5)), alpha=0.1)
    assert math.isinf(c.threshold)
    assert c.status == 'UNBOUNDED'


def test_hcp_003_quantile_matches_explicit_rank():
    c = calibrate((9., 1., 7., 2., 3., 5., 4., 6., 8.), alpha=.2)
    assert c.threshold == 8.


def test_hcp_004_duplicate_scores_and_ties():
    c = calibrate((.5, .5, .5, .5, .5, .5, .5, .5, .5, .5), alpha=.2)
    assert c.threshold == .5


def test_hcp_005_weighted_known_ratio_quantile():
    c = calibrate((1., 2., 3.), alpha=.25,
                  weights=(1., 4., 3.), test_weight=1.,
                  ratio_source='known_ratio', source_id='reference-1')
    assert c.threshold == 3.
    assert c.claim == 'CONDITIONAL_KNOWN_RATIO'
    assert not c.assumptions_attested


def test_hcp_006_large_test_weight_forces_unbounded():
    c = calibrate((1., 2., 3.), alpha=.25, weights=(1., 1., 1.),
                  test_weight=10., ratio_source='known_ratio', source_id='pinned')
    assert math.isinf(c.threshold)
    assert c.status == 'UNBOUNDED'


def test_hcp_007_estimated_weights_cannot_claim_guarantee():
    c = calibrate((1., 2., 3., 4.), alpha=.3,
                  weights=(1., 1., 1., 1.), test_weight=1.,
                  ratio_source='estimated_ratio', source_id='estimated')
    assert c.claim == 'ESTIMATED_WEIGHTS_NO_FINITE_SAMPLE_CLAIM'
    assert not c.assumptions_attested


def test_hcp_008_zero_calibration_weight_is_permitted():
    c = calibrate((1., 2., 3., 4.), alpha=.25,
                  weights=(0., 2., 2., 2.), test_weight=1.,
                  ratio_source='known_ratio', source_id='s1')
    assert c.threshold == 4.
    assert c.effective_n == 3.


def test_hcp_009_kish_ess_detects_weight_collapse():
    c = calibrate((1., 2., 3., 4.), alpha=.2,
                  weights=(100., .01, .01, .01), test_weight=1.,
                  ratio_source='known_ratio', source_id='s1')
    assert 1 <= c.effective_n < 1.001


@pytest.mark.parametrize('scores', [(), (1., float('nan')), (1., float('inf')),
                                    (1., -1.), (1., True), ('1', 2.),
                                    (1.,)*4097, [1., 2.], (0., 1e13)])
def test_hcp_010_invalid_scores_rejected(scores):
    with pytest.raises(ValueError):
        calibrate(scores, alpha=.1)


@pytest.mark.parametrize('alpha', [0., 1., -.1, float('nan'), float('inf'), True, .0001])
def test_hcp_011_invalid_alpha_rejected(alpha):
    with pytest.raises(ValueError):
        calibrate((1., 2.), alpha=alpha)


@pytest.mark.parametrize('kwargs', [
    {'weights':(1., 2.)},
    {'weights':(1.,), 'ratio_source':'known_ratio', 'source_id':'s'},
    {'weights':(1., 2.), 'ratio_source':'unweighted'},
    {'weights':(1., 2.), 'ratio_source':'known_ratio'},
    {'weights':(1., 2.), 'ratio_source':'known_ratio', 'source_id':'../../../x'},
    {'weights':(0., 0.), 'ratio_source':'known_ratio', 'source_id':'s'},
    {'weights':(-1., 2.), 'ratio_source':'known_ratio', 'source_id':'s'},
    {'weights':(1., float('nan')), 'ratio_source':'known_ratio', 'source_id':'s'},
    {'weights':(True, 2.), 'ratio_source':'known_ratio', 'source_id':'s'},
    {'weights':(1., 2.), 'test_weight':0, 'ratio_source':'known_ratio', 'source_id':'s'},
    {'weights':(1., 2.), 'test_weight':float('inf'), 'ratio_source':'known_ratio', 'source_id':'s'},
    {'weights':(1., 2.), 'ratio_source':'estimated_ratio', 'source_id':'line\ninjection'},
])
def test_hcp_012_invalid_weights_or_provenance(kwargs):
    with pytest.raises(ValueError):
        calibrate((1., 2.), alpha=.2, **kwargs)


def test_hcp_013_score_order_does_not_change_digest_or_threshold():
    a = calibrate((3., 1., 2., 4.), alpha=.25)
    b = calibrate((1., 2., 3., 4.), alpha=.25)
    assert a.threshold == b.threshold
    assert a.digest == b.digest


def test_hcp_014_weight_mapping_cannot_be_reordered_without_digest_change():
    a = calibrate((3., 1., 2.), alpha=.25, weights=(9., 1., 1.),
                  ratio_source='known_ratio', source_id='one')
    b = calibrate((1., 2., 3.), alpha=.25, weights=(9., 1., 1.),
                  ratio_source='known_ratio', source_id='one')
    assert a.digest != b.digest


def test_hcp_015_route_fast_only_advisory():
    c = calibrate((.1,)*19, alpha=.1)
    d = route_budget(c, BudgetPolicy(base_steps=16, verify_steps=64,
                                      max_width=.2), expected_digest=c.digest)
    assert d.action == 'BASELINE_COMPUTE'
    assert d.steps == 16
    assert d.release_authorized is False


def test_hcp_016_route_wide_uncertainty_increases_verification_budget():
    c = calibrate((.9,)*19, alpha=.1)
    d = route_budget(c, BudgetPolicy(16, 64, .2), expected_digest=c.digest)
    assert d.action == 'EXTENDED_VERIFICATION'
    assert d.steps == 64


def test_hcp_017_route_unknown_returns_abstain():
    c = calibrate((.1,)*3, alpha=.1)
    d = route_budget(c, BudgetPolicy(16, 64, .2), expected_digest=c.digest)
    assert d.action == 'ABSTAIN_INSUFFICIENT_CALIBRATION'
    assert d.steps == 0


def test_hcp_018_estimated_ratio_does_not_get_fast_path():
    c = calibrate((.1,)*19, alpha=.1, weights=(1.,)*19,
                  ratio_source='estimated_ratio', source_id='model_v1')
    d = route_budget(c, BudgetPolicy(16, 64, .2), expected_digest=c.digest)
    assert d.action == 'EXTENDED_VERIFICATION'


def test_hcp_019_wrong_digest_fails_closed():
    c = calibrate((.1,)*19, alpha=.1)
    with pytest.raises(ValueError):
        route_budget(c, BudgetPolicy(16, 64, .2), expected_digest='0'*64)


def test_hcp_021_policy_invalid_inputs():
    for kw in [dict(base_steps=8,verify_steps=4,max_width=.1),
               dict(base_steps=1,verify_steps=10000000,max_width=.2),
               dict(base_steps=True,verify_steps=16,max_width=.1),
               dict(base_steps=8,verify_steps=16,max_width=float('nan'))]:
        with pytest.raises(ValueError): BudgetPolicy(**kw)


def test_hcp_022_jsonl_contract_no_input_payload():
    c = calibrate((.1,)*19, alpha=.1)
    d = route_budget(c, BudgetPolicy(16, 64, .2), expected_digest=c.digest)
    raw = export_jsonl(c, d)
    assert raw.endswith('\n') and raw.count('\n') == 1
    obj = json.loads(raw)
    assert obj['schema'] == 'omega-hyperion-conformal-v1'
    assert obj['release_authorized'] is False
    assert 'scores' not in raw and 'weights' not in obj
    assert 'physical_measurement_verified' not in obj


def test_hcp_023_tamper_frozen_result_detected():
    c = calibrate((.1,)*19, alpha=.1)
    with pytest.raises(FrozenInstanceError): c.threshold = 0.
    poisoned = replace(c, threshold=0.)
    with pytest.raises(ValueError):
        route_budget(poisoned, BudgetPolicy(16, 64, .2), expected_digest=c.digest)


def test_hcp_024_tamper_digest_detected():
    c = calibrate((.1,)*19, alpha=.1)
    poisoned = replace(c, digest='0'*64)
    with pytest.raises(ValueError):
        route_budget(poisoned, BudgetPolicy(16, 64, .2), expected_digest=c.digest)


def test_hcp_025_no_confidence_guarantee_from_operator_string():
    c = calibrate((.1,)*19, alpha=.1, weights=(1.,)*19,
                  ratio_source='known_ratio', source_id='self_claimed_known')
    assert not c.assumptions_attested
    assert c.claim == 'CONDITIONAL_KNOWN_RATIO'


def test_hcp_026_threshold_boundary_is_inclusive():
    c=calibrate((.2,)*19,alpha=.1)
    assert route_budget(c, BudgetPolicy(16,64,.2),expected_digest=c.digest).action=='BASELINE_COMPUTE'


def test_hcp_027_export_rejects_wrong_result_pair():
    a=calibrate((.1,)*19,alpha=.1)
    b=calibrate((.2,)*19,alpha=.1)
    decision=route_budget(a,BudgetPolicy(16,64,.3),expected_digest=a.digest)
    with pytest.raises(ValueError): export_jsonl(b,decision)


def test_hcp_028_extreme_alpha_is_unbounded_not_overconfident():
    c = calibrate((0.,)*32, alpha=.001)
    assert c.status == 'UNBOUNDED'


def test_hcp_029_derived_properties_are_monotonic_alpha():
    scores=tuple(float(i) for i in range(20))
    a=calibrate(scores,alpha=.05)
    b=calibrate(scores,alpha=.2)
    assert a.threshold >= b.threshold


def test_hcp_030_ratio_source_requires_test_weight_for_shift():
    c=calibrate((1.,)*19,alpha=.1,weights=(1.,)*19,
                ratio_source='known_ratio',source_id='operator-v1')
    assert c.test_weight == 1.


def test_hcp_031_budget_policy_max_width_cannot_be_negative():
    with pytest.raises(ValueError):BudgetPolicy(16,64,-1)


def test_hcp_032_provenance_not_attestation():
    a=calibrate((.1,)*19,alpha=.1)
    assert a.assumptions_attested is False
    assert a.release_authorized is False

@pytest.mark.parametrize('ratio_source', ['incorrect', None, 3])
def test_hcp_033_unsupported_ratio_source_fails_closed(ratio_source):
    with pytest.raises(ValueError):
        calibrate((1., 2.), alpha=.2, ratio_source=ratio_source)


def test_hcp_034_untagged_evidence_rejected():
    with pytest.raises(ValueError):
        route_budget({'threshold':0}, BudgetPolicy(4, 16, .1), expected_digest='0'*64)


def test_hcp_035_caller_cannot_attest_own_guarantee():
    c=calibrate((.1,)*19, alpha=.1)
    for poisoned in (replace(c, assumptions_attested=True),
                     replace(c, release_authorized=True)):
        with pytest.raises(ValueError):
            route_budget(poisoned, BudgetPolicy(4,16,.2), expected_digest=c.digest)


def test_hcp_036_invalid_policy_type_rejected():
    c=calibrate((.1,)*19,alpha=.1)
    with pytest.raises(ValueError):
        route_budget(c, {'base_steps':4}, expected_digest=c.digest)


def test_hcp_037_invalid_export_decision_type():
    c=calibrate((.1,)*19,alpha=.1)
    with pytest.raises(ValueError):
        export_jsonl(c, {'action':'BASELINE_COMPUTE'})


def test_hcp_038_modified_action_in_export_rejected():
    c=calibrate((.1,)*19,alpha=.1)
    d=route_budget(c,BudgetPolicy(4,16,.2),expected_digest=c.digest)
    with pytest.raises(ValueError):
        export_jsonl(c,replace(d,action='ABSTAIN_INSUFFICIENT_CALIBRATION'))


def test_hcp_039_simulated_exchangeability_coverage_reference():
    """Empirical sanity check only: not proof of finite-sample coverage."""
    import random
    rng=random.Random(240519)
    n=99
    trials=500
    covered=0
    for _ in range(trials):
        scores=tuple(rng.random() for _ in range(n))
        threshold=calibrate(scores,alpha=.1).threshold
        covered += rng.random() <= threshold
    assert .85 <= covered/trials <= .95


def test_hcp_040_simulated_known_shift_coverage_reference():
    """Discrete known covariate ratio; conditional score mechanism held fixed."""
    import random
    rng=random.Random(20261122)
    covered=0
    trials=500
    for _ in range(trials):
        xs=[int(rng.random()<.2) for i in range(99)]
        scores=tuple((1+x)*rng.random() for x in xs)
        weights=tuple(3.5 if x else .375 for x in xs)
        xt=int(rng.random()<.7)
        wt=3.5 if xt else .375
        q=calibrate(scores,alpha=.1,weights=weights,test_weight=wt,
                    ratio_source='known_ratio',source_id='fixed-bernoulli-model').threshold
        test_score=(1+xt)*rng.random()
        covered += test_score <= q
    assert .85 <= covered/trials <= .96
