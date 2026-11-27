from dataclasses import replace

import pytest

from omega_x_evolution.ontos_observation_policy import ObservationPolicy, PolicyConfig, SensorFrame
from omega_x_evolution.ontos_paired_interventions import run_pair
from omega_x_evolution.ontos_ablation import (
    ARMS, DEV_SEEDS, VALIDATION_SEEDS, run_arm, run_ablation, run_selection,
)


def test_baseline_and_reset_exact_existing_paired_trace():
    old=run_pair(9216,horizon=120)
    for name,config in ARMS[:2]:
        r=run_arm(9216,config,horizon=120)
        assert all(r[k]==v for k,v in old[name].items())


@pytest.mark.parametrize('changes',[{'recurrent':1},{'floor':0},{'floor':.09},
    {'hazard':True},{'hazard':1.1},{'ood_limit':float('nan')},{'confidence_min':-.1}])
def test_config_bounds(changes):
    with pytest.raises(ValueError): replace(PolicyConfig(),**changes)


def test_confidence_and_contamination_veto_are_separate():
    frame=SensorFrame(1,(8.,)*6,0.)
    baseline=ObservationPolicy().decide(frame)
    open_=ObservationPolicy(PolicyConfig(ood_limit=1.,confidence_min=0.)).decide(frame)
    assert baseline.action==5 and open_.action in range(4)
    assert baseline.posterior==open_.posterior
    assert baseline.ood_probability==open_.ood_probability


def test_ablation_frozen_family_and_exact_accounting():
    r=run_ablation((1,2),horizon=40)
    assert r==run_ablation((1,2),horizon=40)
    assert len(r['rows'])==2*len(ARMS)
    assert len(r['comparisons'])==len(ARMS)-1
    for a in r['summary'].values():
        assert a['correct']+a['abstentions']+a['wrong']==80
        assert a['harm']==0
    for c in r['comparisons']:
        assert c['ci_family_size']==len(ARMS)-1 and c['p_raw']<=c['p_holm']<=1
    assert r['release_authorized'] is False
    assert r['source_reproduction_verified'] is False


@pytest.mark.parametrize('seeds,horizon',[((),120),((1,),120),((1,1),120),((True,2),120),([1,2],120),((1,2),241)])
def test_bad_campaign(seeds,horizon):
    with pytest.raises(ValueError): run_ablation(seeds,horizon=horizon)


def test_selection_is_dev_only_and_disjoint():
    assert not set(DEV_SEEDS)&set(VALIDATION_SEEDS)
    r=run_selection((1,2),(3,4),horizon=40)
    assert r==run_selection((1,2),(3,4),horizon=40)
    assert r['winner']==max(r['development'],key=lambda n:(r['development'][n]['correct'],-r['development'][n]['wrong'],n))
    assert r['validation']['candidate']['steps']==80
    assert r['validation']['baseline']['steps']==80
    assert r['independent_holdout_verified'] is False
    with pytest.raises(ValueError): run_selection((1,2),(2,3),horizon=40)


def test_guarded_selection_preserves_both_vetoes():
    from omega_x_evolution.ontos_ablation import run_guarded_selection
    r=run_guarded_selection((1,2),(3,4),horizon=40)
    assert r['config']['ood_limit']==.5 and r['config']['confidence_min']==.5
    assert r['selection_scope']=='GUARDED_CALIBRATION'
    assert r['validation']['candidate']['steps']==80
    assert not r['release_authorized']
    assert r['policy_changed'] is False
