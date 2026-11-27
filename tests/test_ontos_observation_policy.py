import hashlib
import json
import math
from dataclasses import fields

import pytest

from omega_x_evolution.ontos_testbed import replay, campaign
from omega_x_evolution.ontos_observation_policy import (
    SensorFrame, ObservationPolicy, run_observation_episode, run_campaign,
)

SEEDS=tuple(9100+29*i for i in range(30))


def test_legacy_trace_digests_unchanged_for_28800_steps():
    tapes={'cycle':(0,1,2,3)*60,'offset':(1,2,3,0)*60,'abstain':(5,)*240,'harm':(4,)*240}
    raw=json.dumps({k:campaign(SEEDS,v) for k,v in tapes.items()},sort_keys=True,separators=(',',':'))+'\n'
    assert hashlib.sha256(raw.encode()).hexdigest()=='4c3f8b02e8d3749f680913c7175ecc639ec429e86d9064da85ff808da760bc74'


def test_sensor_interface_contains_no_evaluator_labels_or_clock():
    assert {f.name for f in fields(SensorFrame)}=={'discrete','continuous','damage'}
    f=SensorFrame(2,(-.7,.9,.85,-.8,.2,.8),0.)
    result=ObservationPolicy().decide(f)
    assert result.action==3 and result.ood_probability<.01
    assert math.isclose(sum(result.posterior),1.)
    assert min(result.posterior)>=.004-1e-15


def test_ood_abstains_without_label_and_recovers():
    p=ObservationPolicy()
    bad=p.decide(SensorFrame(1,(8.,)*6,0.))
    assert bad.action==5 and bad.ood_probability>.99
    for _ in range(10):
        good=p.decide(SensorFrame(0,(1.55,.2,-.8,.4,.9,-.3),0.))
    assert good.action==0
    assert min(good.posterior)>=.004-1e-15


@pytest.mark.parametrize('args',[(True,(0.,)*6,0.),(4,(0.,)*6,0.),(0,(0.,)*5,0.),(0,(float('nan'),)*6,0.),(0,(1e100,)*6,0.),(0,(0.,)*6,-.1),(0,(0.,)*6,1.)])
def test_invalid_sensor_input(args):
    with pytest.raises(ValueError): SensorFrame(*args)


def test_bounded_policy_stops_after_limit():
    p=ObservationPolicy(); f=SensorFrame(0,(1.55,.2,-.8,.4,.9,-.3),0.)
    for _ in range(240): p.decide(f)
    with pytest.raises(ValueError): p.decide(f)


@pytest.mark.parametrize('seed',[9216,9274,9651])
def test_adaptive_actions_replay_exactly_in_actual_environment(seed):
    a=run_observation_episode(seed)
    assert a==run_observation_episode(seed)
    actions=tuple(x.action for x in a)
    assert len(a)==240 and all(x in (0,1,2,3,5) for x in actions)
    assert a==replay(seed,actions)


def test_campaign_uses_scorer_only_after_policy_and_counts_abstentions():
    report=run_campaign((9216,9274,9651))
    assert report==run_campaign((9216,9274,9651))
    assert report['steps']==720
    assert report['correct']+report['abstentions']+report['wrong']==720
    assert report['unconditional_accuracy']==report['correct']/720
    assert report['conditional_accuracy']==report['correct']/(720-report['abstentions'])
    assert report['release_authorized'] is False
    assert report['process_isolation_verified'] is False
    assert report['source_v2_reproduced'] is False
    assert report['survival_measured'] is False


@pytest.mark.parametrize('seed,horizon',[(-1,240),(True,240),(0,0),(0,241),(0,True)])
def test_invalid_episode_bounds(seed,horizon):
    with pytest.raises(ValueError): run_observation_episode(seed,horizon=horizon)


@pytest.mark.parametrize('seeds',[(),(1,1),[1],(True,),tuple(range(31))])
def test_campaign_bounds(seeds):
    with pytest.raises(ValueError): run_campaign(seeds)
