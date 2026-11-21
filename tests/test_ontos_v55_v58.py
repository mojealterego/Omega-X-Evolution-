"""ONTOS L8 v55-v58: independent finite-domain models and scorer-side tests."""
from fractions import Fraction as F
from itertools import product
import math
import random
import pytest

from omega_x_evolution.ontos_v55_scm import ResponseType, BinaryIVSCM, response_space
from omega_x_evolution.ontos_v56_bounds import iv_bounds
from omega_x_evolution.ontos_v57_causal_metrics import channel_measure, value_of_information, bound_summary
from omega_x_evolution.ontos_v58_ood import (
    vr_h0_deaths, fit_ood, score_ood, evaluate_ood, run_suite_c,
)


def model(*rows):
    return BinaryIVSCM(tuple(ResponseType(*r) for r in rows))


def table_from_model(m):
    return (m.observational(0), m.observational(1))


def test_v55_response_domain_enumerates_all_16_types():
    assert len(response_space()) == 16
    assert len(set(response_space())) == 16
    assert all(len(t) == 4 for t in response_space())


def test_v55_obs_vs_do_confounding_disagree():
    m = model((0, 0, 0, 0, F(1, 2)), (1, 1, 1, 1, F(1, 2)))
    assert m.observational(0) == (F(1, 2), F(0), F(0), F(1, 2))
    assert m.observational(1) == m.observational(0)
    assert m.intervene(0) == F(1, 2)
    assert m.intervene(1) == F(1, 2)
    assert m.average_treatment_effect() == 0
    assert m.observational_risk(0, 0) == 0
    assert m.observational_risk(0, 1) == 1


def test_v55_randomized_complier_identifies_causal_difference():
    m = model((0, 1, 0, 1, F(1)))
    assert m.observational(0) == (F(1), F(0), F(0), F(0))
    assert m.observational(1) == (F(0), F(0), F(0), F(1))
    assert m.intervene(0) == 0 and m.intervene(1) == 1
    assert m.average_treatment_effect() == 1
    assert m.harm_probability() == 0


def test_v55_no_observation_support_does_not_invent_conditional_probability():
    m = model((0, 0, 0, 1, F(1)))
    assert m.observational_risk(0, 1) is None
    assert m.intervene(1) == 1


@pytest.mark.parametrize('rows', [
    ((0,1,0,1,F(1,2)),),
    ((0,1,0,1,F(-1)),),
    ((0,1,0,1,F(1,2)), (1,1,1,1,F(1,3))),
    ((True,1,0,1,F(1)),),
    ((0,1,0,1,1.),),
])
def test_v55_invalid_weights_and_binary_types(rows):
    with pytest.raises(ValueError): model(*rows)


def test_v55_interventions_do_not_depend_on_instrument():
    m = model((0, 1, 0, 1, F(1, 3)), (1, 0, 1, 0, F(2, 3)))
    for z in (0,1):
        assert sum(m.observational(z)) == 1
    assert m.intervene(1) == F(1, 3)
    assert m.intervene(0) == F(2, 3)
    assert m.average_treatment_effect() == F(-1, 3)
    with pytest.raises(ValueError): m.observational(True)
    with pytest.raises(ValueError): m.intervene(2)


def test_v56_identification_under_full_compliance():
    m = model((0,1,0,1,F(1)))
    obs=table_from_model(m)
    r=iv_bounds(obs, target='ate')
    assert r['status'] == 'PASS'
    assert r['lower'] == pytest.approx(1)
    assert r['upper'] == pytest.approx(1)
    assert r['identified']
    assert r['primal_max_residual'] < 1e-8
    assert iv_bounds(obs, target='harm')['upper'] == pytest.approx(0)


def test_v56_missing_treatment_support_keeps_unknown_potential_outcome():
    always_untreated=model((0,0,0,0,F(1)))
    r=iv_bounds(table_from_model(always_untreated), target='y1')
    assert r['status']=='PASS'
    assert r['lower'] == pytest.approx(0)
    assert r['upper'] == pytest.approx(1)
    assert not r['identified']
    ate=iv_bounds(table_from_model(always_untreated),target='ate')
    assert ate['lower']==pytest.approx(0) and ate['upper']==pytest.approx(1)


def test_v56_unobserved_harm_interval_wide():
    m=model((0,0,1,1,F(1)))
    r=iv_bounds(table_from_model(m),target='harm')
    assert r['lower']==pytest.approx(0)
    assert r['upper']==pytest.approx(1)
    assert not r['identified']


def test_v56_inconsistent_instrument_exclusion_is_infeasible():
    table=((F(1),F(0),F(0),F(0)), (F(0),F(1),F(0),F(0)))
    r=iv_bounds(table,target='harm')
    assert r['status']=='INFEASIBLE'
    assert r['lower'] is None and r['upper'] is None


@pytest.mark.parametrize('bad', [
    ((F(1),F(0)),(F(1),F(0))),
    ((F(1),F(0),F(0),F(0)),),
    ((F(1,2),F(0),F(0),F(0)),(F(1),F(0),F(0),F(0))),
    ((F(-1),F(2),F(0),F(0)),(F(1),F(0),F(0),F(0))),
    ((.5,.5,0.,0.), (1.,0.,0.,0.)),
])
def test_v56_invalid_instrument_tables_fail_closed(bad):
    with pytest.raises(ValueError): iv_bounds(bad,target='harm')


def test_v56_invalid_effect_name():
    with pytest.raises(ValueError): iv_bounds(table_from_model(model((0,1,0,1,F(1)))),target='policy')


def test_v56_true_causal_effect_always_inside_computed_interval():
    rng=random.Random(143)
    types=response_space()
    for _ in range(8):
        weights=[rng.randrange(1,16) for t in types]
        total=sum(weights)
        m=BinaryIVSCM(tuple(ResponseType(*t,F(w,total)) for t,w in zip(types,weights)))
        table=table_from_model(m)
        for target,value in [('ate',m.average_treatment_effect()),('harm',m.harm_probability()),('y1',m.intervene(1))]:
            bounds=iv_bounds(table,target=target)
            assert bounds['status']=='PASS'
            assert bounds['lower']-1e-8 <= float(value) <= bounds['upper']+1e-8


def test_v56_sparse_p00_zero_is_not_promoted_to_false_certainty():
    m=model((0,1,1,0,F(1)))
    assert m.observational(0)[0]==0
    interval=iv_bounds(table_from_model(m),target='harm')
    assert interval['status']=='PASS'
    assert interval['lower'] >= 0 and interval['upper'] <= 1


def test_v57_identity_channel_has_one_bit_ei_and_empowerment():
    channel=((1.,0.),(0.,1.))
    metrics=channel_measure(channel,prior=(.5,.5))
    assert metrics['mutual_information_bits']==pytest.approx(1)
    assert metrics['effective_information_bits']==pytest.approx(1)
    assert metrics['empowerment_lower_bits']==pytest.approx(1)
    assert metrics['empowerment_upper_bits']==pytest.approx(1)


def test_v57_constant_channel_has_no_information():
    channel=((1.,0.),(1.,0.))
    r=channel_measure(channel,prior=(.9,.1))
    for k in ('mutual_information_bits','effective_information_bits','empowerment_lower_bits','empowerment_upper_bits'):
        assert r[k]==pytest.approx(0,abs=1e-10)


def test_v57_nonuniform_prior_differs_from_ei_and_capacity():
    channel=((1.,0.),(0.,1.))
    r=channel_measure(channel,prior=(.9,.1))
    assert r['mutual_information_bits'] < r['effective_information_bits']
    assert r['effective_information_bits']<=r['empowerment_lower_bits']+1e-9


def test_v57_voi_under_perfect_and_constant_observations():
    utility=((1.,0.),(0.,1.))
    perfect=value_of_information((.5,.5),((1.,0.),(0.,1.)),utility)
    none=value_of_information((.5,.5),((1.,0.),(1.,0.)),utility)
    assert perfect['before']==pytest.approx(.5)
    assert perfect['after']==pytest.approx(1)
    assert perfect['gain']==pytest.approx(.5)
    assert none['gain']==pytest.approx(0)


def test_v57_asymmetric_known_voi():
    r=value_of_information((.75,.25),((.6,.4),(.2,.8)),((1.,0.),(0.,1.)))
    assert r['before']==pytest.approx(.75)
    assert r['after']>=r['before']
    assert r['gain']>=-1e-12


def test_v57_distinguish_causal_and_observational_observables():
    m=model((0,0,0,0,F(1,2)),(1,1,1,1,F(1,2)))
    r=bound_summary(iv_bounds(table_from_model(m),target='ate'))
    assert not r['identified']
    assert r['width']>=0
    # Intervention estimand cannot be replaced by observed P(Y|X).
    assert m.average_treatment_effect()==0
    assert m.observational_risk(0,1)-m.observational_risk(0,0)==1


@pytest.mark.parametrize('bad', [
    ((.4,.4),(.5,.5)),
    ((-1.,2.),(0.,1.)),
    ((True,0.),(0.,1.)),
])
def test_v57_invalid_channel(bad):
    with pytest.raises(ValueError): channel_measure(bad,prior=(.5,.5))


def test_v58_h0_vietoris_rips_reference_and_symmetry():
    triangle=((0.,0.),(1.,0.),(0.,1.))
    assert vr_h0_deaths(triangle)==pytest.approx((1.,1.))
    square=((0.,0.),(0.,1.),(1.,0.),(1.,1.))
    assert vr_h0_deaths(square)==pytest.approx((1.,1.,1.))
    shifted=tuple((x+20.,y-10.) for x,y in triangle)
    assert vr_h0_deaths(shifted)==pytest.approx((1.,1.))


def test_v58_h0_two_points_distance():
    assert vr_h0_deaths(((0.,0.),(3.,4.)))==(5.,)
    assert vr_h0_deaths(((0.,0.),))==()


def test_v58_ood_calibration_holdout_and_fail_closed():
    ref=((0.,0.),(.1,0.),(0.,.1),(-.1,0.),(0.,-.1))
    dev=tuple((x*.7,y*.7) for x,y in ref)
    detector=fit_ood(ref,dev,fpr_target=.2)
    score=score_ood(detector,((0.,0.),(10.,10.)))
    assert score[1]>score[0]
    report=evaluate_ood(detector,((0.01,0.),(10.,10.)),(False,True))
    assert report['total']==2
    assert report['roc_auc']==pytest.approx(1)
    assert report['average_precision']==pytest.approx(1)
    assert report['status']=='EVALUATED_HOLDOUT'
    assert not report['release_approved']


def test_v58_norm_blindspot_explicitly_detected():
    # Same norm; separated geometry. A norm-only OOD detector is blind.
    norm=lambda p: math.hypot(*p)
    assert norm((1.,0.))==norm((0.,1.))
    detector=fit_ood(((1.,0.),(.9,.1),(1.1,-.1)),((1.,.01),(.99,0.)),fpr_target=.1)
    assert score_ood(detector,((0.,1.),))[0] > score_ood(detector,((1.,.01),))[0]


def test_v58_calibration_is_deterministic_and_tie_abstains():
    ref=((0.,0.),(2.,0.))
    model=fit_ood(ref,((1.,0.),(1.,0.)),fpr_target=.5)
    assert model==fit_ood(ref,((1.,0.),(1.,0.)),fpr_target=.5)
    report=evaluate_ood(model,((1.,0.),(1.,0.)),(False,True))
    assert report['abstentions']==2
    assert report['coverage']==0
    assert report['false_positive_rate'] is None


@pytest.mark.parametrize('points', [(),((float('nan'),0.),),((True,0.),),((0.,), (0.,0.))])
def test_v58_bad_geometry_rejected(points):
    with pytest.raises(ValueError): vr_h0_deaths(points)


def test_v58_full_suite_c_frozen_split_and_heldout_truth():
    r=run_suite_c()
    assert r==run_suite_c()
    assert r['dev_reference_seeds']==10
    assert r['dev_calibration_seeds']==10
    assert r['holdout_seeds']==10
    assert r['holdout_rows']==2400
    assert r['status']=='EVALUATED_HOLDOUT'
    assert r['release_approved'] is False
    assert r['meets_70_recall_5_fpr_target'] == (
        r['holdout_recall'] is not None and r['holdout_fpr'] is not None
        and r['holdout_recall'] >= .70 and r['holdout_fpr'] <= .05
    )
    assert 0<=r['roc_auc']<=1 and 0<=r['average_precision']<=1
    assert r['holdout_positive']>0 and r['holdout_negative']>0
    assert r['threshold']>=0


def test_v58_suite_c_split_is_disjoint_and_pinned():
    r=run_suite_c()
    assert r['dev_reference_sha256'] != r['holdout_sha256']
    assert len(r['holdout_sha256'])==64
    assert r['selection_rule']=='first 10 dev-reference, next 10 dev-calibration, final 10 holdout; fixed before scoring'


def test_v58_statistical_intervals_and_ood_counts():
    r=run_suite_c()
    assert r['recall_wilson_95'] is not None
    assert r['fpr_wilson_95'] is not None
    assert r['recall_wilson_95'][0]<=r['holdout_recall']<=r['recall_wilson_95'][1]
    assert r['fpr_wilson_95'][0]<=r['holdout_fpr']<=r['fpr_wilson_95'][1]
    assert r['confusion']['tp']+r['confusion']['fn']+r['confusion']['positive_abstain']==r['holdout_positive']
    assert r['confusion']['tn']+r['confusion']['fp']+r['confusion']['negative_abstain']==r['holdout_negative']


def test_v58_confidence_gate_is_stricter_than_point_estimate():
    r=run_suite_c()
    assert r['meets_70_recall_5_fpr_target']
    assert not r['confidence_gate_95_passed']
    assert r['fpr_wilson_95'][1] > .05
    assert r['recall_wilson_95'][0] > .70
    assert not r['release_approved']


def test_v58_h0_actual_bounded_cohorts_in_campaign():
    r=run_suite_c()
    assert r['h0_cohort_subset_size']==32
    for key in ('dev_reference','holdout'):
        assert r['h0_cohort_diagnostics'][key]['finite_deaths']==31
        assert r['h0_cohort_diagnostics'][key]['max_death'] >= 0
        assert r['h0_cohort_diagnostics'][key]['total_persistence'] >= r['h0_cohort_diagnostics'][key]['max_death']


def test_v58_model_must_revalidate_after_tampering():
    detector=fit_ood(((0.,0.),(1.,0.)),((.1,0.),(.9,0.)),fpr_target=.05)
    object.__setattr__(detector,'threshold',float('nan'))
    with pytest.raises(ValueError): score_ood(detector,((0.,.1),))


def test_v56_all_deterministic_latent_types_contained():
    for case in response_space():
        m=BinaryIVSCM((ResponseType(*case,F(1)),))
        table=table_from_model(m)
        for target,actual in (('y1',m.intervene(1)),('harm',m.harm_probability())):
            out=iv_bounds(table,target=target)
            assert out['status']=='PASS'
            assert out['lower']-1e-9 <= float(actual) <= out['upper']+1e-9


def test_v57_empowerment_is_upper_bound_on_uneven_prior_mi():
    channel=((.8,.1,.1),(.2,.5,.3),(.1,.2,.7))
    r=channel_measure(channel,prior=(.9,.05,.05))
    assert r['capacity_converged']
    assert r['mutual_information_bits'] <= r['empowerment_upper_bits']+1e-8
    assert r['effective_information_bits'] <= r['empowerment_upper_bits']+1e-8
    assert r['empowerment_lower_bits'] <= r['empowerment_upper_bits']
