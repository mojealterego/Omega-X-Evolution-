import pytest

from omega_x_evolution.ontos_testbed import _episode, _SIGNATURES
from omega_x_evolution.ontos_paired_interventions import run_pair, campaign


def tape(seed, action):
    session=_episode(seed,240,paired=True)
    next(session)
    for _ in range(240):
        try: session.send(action)
        except StopIteration as stop: return stop.value
    raise AssertionError('unterminated episode')


def noise(row):
    o=row.observation; sig=_SIGNATURES[row.regime]
    sigma=2.30 if row.ood else .07+.35*o.damage
    return tuple((x-y-(.55 if j==o.discrete else 0.))/sigma for j,(x,y) in enumerate(zip(o.continuous,sig)))


def test_common_exogenous_noise_despite_divergent_actions_and_damage():
    left,right=tape(123,4),tape(123,5)
    assert any(a.observation.damage!=b.observation.damage for a,b in zip(left,right))
    for a,b in zip(left,right):
        assert (a.ood,a.observation.lure,a.observation.tamper)==(b.ood,b.observation.lure,b.observation.tamper)
        assert noise(a)==pytest.approx(noise(b),abs=1e-12)


def test_pair_is_reproducible_and_counts_all_steps():
    r=run_pair(42,horizon=240)
    assert r==run_pair(42,horizon=240)
    assert r['seed']==42 and r['steps']==240
    assert r['effect_correct']==r['recurrent']['correct']-r['memoryless']['correct']
    for name in ('recurrent','memoryless'):
        a=r[name]
        assert a['correct']+a['abstentions']+a['wrong']==240
        assert a['harm']==0
    assert r['recurrent']['ood']==r['memoryless']['ood']


def test_campaign_effect_is_paired_seed_average_and_not_release():
    r=campaign((1,2,3),horizon=120)
    assert r==campaign((1,2,3),horizon=120)
    assert r['steps_per_arm']==360
    assert r['paired_effect_accuracy']==sum(x['effect_correct'] for x in r['pairs'])/360
    assert r['bootstrap_ci95'][0]<=r['bootstrap_ci95'][1]
    assert not r['release_authorized'] and not r['external_causal_effect_verified']


@pytest.mark.parametrize('seeds,horizon',[((),240),((1,),240),((1,1),240),([1,2],240),((True,2),240),((1,2),0),((1,2),241),((1,2),True)])
def test_bounded_campaign(seeds,horizon):
    with pytest.raises(ValueError): campaign(seeds,horizon=horizon)


@pytest.mark.parametrize('seed,horizon',[(-1,240),(True,240),(2**32,240),(0,0),(0,241),(0,True)])
def test_pair_bounds(seed,horizon):
    with pytest.raises(ValueError): run_pair(seed,horizon=horizon)
