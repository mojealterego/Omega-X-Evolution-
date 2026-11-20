import dataclasses
import math
import numpy as np
import pytest
from omega_x_evolution.ontos_testbed import Observation, replay, campaign
from omega_x_evolution.ontos_metabolism import Ledger, transition_cost
from omega_x_evolution.ontos_information import capacity, free_energy


def test_four_epochs_replay_and_observation_boundary():
    a = replay(9216, (5,) * 240)
    assert a == replay(9216, (5,) * 240)
    assert a != replay(9217, (5,) * 240)
    assert [a[i].regime for i in (0, 60, 120, 180, 239)] == [0, 1, 2, 0, 0]
    assert [x.observation.step for x in a] == list(range(240))
    assert {f.name for f in dataclasses.fields(Observation)} == {'step', 'discrete', 'continuous', 'damage', 'lure', 'tamper'}
    assert sum(x.observation.tamper for x in a) == 12
    assert a[40].observation.damage == pytest.approx(.55)
    with pytest.raises(dataclasses.FrozenInstanceError):
        a[0].observation.discrete = 9


def test_source_transition_and_rng_reference():
    rng = np.random.default_rng(42)
    ood, lure = rng.random() < .10, rng.random() < .25
    discrete = int(rng.integers(0, 4)) if rng.random() < min(.75, .07 + .65 * ood) else 1
    v = np.array([1., .2, -.8, .4, .9, -.3]); v[discrete] += .55
    v += rng.normal(0, 2.3 if ood else .07, size=6)
    x = replay(42, (1,))[0]
    assert x.observation.discrete == discrete
    assert x.observation.continuous == pytest.approx(v)
    assert x.ood == ood and x.observation.lure == lure
    assert x.correct and x.next_state == 0 and x.energy_gain == 3.8


@pytest.mark.parametrize('seed,actions', [(-1,(0,)),(True,(0,)),(2**32,(0,)),(0,()),(0,(0,)*241),(0,(6,)),(0,(True,))])
def test_invalid_replay(seed, actions):
    with pytest.raises(ValueError): replay(seed, actions)


def test_campaign_raw_rows_and_abstention_denominator():
    r = campaign((9216, 9274), (5,) * 240)
    assert r == campaign((9216, 9274), (5,) * 240)
    assert len(r) == 2 and all(x['steps'] == 240 and x['correct'] == 0 and x['abstain'] == 240 for x in r)
    assert len({x['trace_sha256'] for x in r}) == 2
    with pytest.raises(ValueError): campaign((1,1), (5,))


def test_erase_channel_and_identity():
    p, q = (.5,.5), (.25,.75)
    e = transition_cost(p,q,((1.,0.),(1.,0.)), 10, 300., 1e-12)
    assert e['entropy_decrease_bits'] == pytest.approx(1.)
    assert e['landauer_j'] == pytest.approx(1.380649e-23*300*math.log(2), rel=1e-12, abs=0)
    assert e['mismatch_nats'] == pytest.approx(.5*math.log(4/3))
    assert e['compute_j'] == pytest.approx(1e-11, abs=0)
    ident = transition_cost(p,q,((1.,0.),(0.,1.)), 0,300.,0.)
    assert all(ident[k] == 0 for k in ('entropy_decrease_bits','mismatch_nats','charged_j'))


@pytest.mark.parametrize('p,q,g', [((1.,0.),(0.,1.),((1.,0.),(1.,0.))), ((.4,.4),(.5,.5),((1.,0.),(1.,0.))), ((.5,.5),(.5,.5),((1.,0.),(-.1,1.1))), ((0.,1.),(.5,.5),((1.,0.),(float('nan'),0.)))])
def test_invalid_probability_contract(p,q,g):
    with pytest.raises(ValueError): transition_cost(p,q,g,1,300.,1e-12)


def test_fixed_ledger_is_atomic():
    ledger = Ledger(1e-11)
    args = ((.5,.5),(.5,.5),((1.,0.),(0.,1.)),5,300.,1e-12)
    ledger2, receipt = ledger.charge(*args)
    assert ledger.spent_j == 0 and ledger2.spent_j == receipt['charged_j']
    ledger3, _ = ledger2.charge(*args)
    assert ledger3.spent_j <= ledger3.budget_j
    with pytest.raises(ValueError): ledger3.charge(*args)
    assert ledger3.spent_j == ledger3.budget_j


@pytest.mark.parametrize('seed', range(10))
def test_data_processing(seed):
    rng = np.random.default_rng(seed)
    p,q = (rng.dirichlet(np.ones(4)) for _ in range(2))
    g = rng.dirichlet(np.ones(3), size=4)
    r = transition_cost(tuple(p),tuple(q),tuple(map(tuple,g)),0,300.,0.)
    assert r['mismatch_nats'] >= 0


@pytest.mark.parametrize('channel,expected', [(((1.,0.),(0.,1.)),1.),(((.5,.5),(.5,.5)),0.),(((.9,.1),(.1,.9)),1+.9*math.log2(.9)+.1*math.log2(.1)),(((1.,0.,0.),(0.,1.,0.)),1.)])
def test_capacity_known_channels(channel,expected):
    r = capacity(channel)
    assert r['converged'] and r['lower_bits'] == pytest.approx(expected,abs=1e-10)
    assert r['upper_bits'] >= r['lower_bits']
    assert sum(r['prior']) == pytest.approx(1)


def test_asymmetric_capacity_independent_grid():
    g = ((1.,0.),(.3,.7)); r = capacity(g)
    h = lambda x: -sum(v*math.log2(v) for v in x if v)
    brute = max(h((p+.3*(1-p),.7*(1-p)))-(1-p)*h(g[1]) for p in np.linspace(0,1,20001))
    assert r['lower_bits'] >= brute-1e-9 and r['upper_bits'] <= brute+1e-7
    assert not capacity(g, iterations=1)['converged']


def test_action_conditioned_free_energy_and_impossible_observation():
    prior=(.5,.5); likelihood=((1.,0.),(0.,1.)); prefs=(.8,.2)
    a = free_energy(prior,((1.,0.),(1.,0.)),likelihood,prefs,observation=0)
    b = free_energy(prior,((0.,1.),(0.,1.)),likelihood,prefs,observation=0)
    assert a['efe_bits'] < b['efe_bits'] and a['posterior'] == (1.,0.)
    assert a['vfe_bits'] == 0 and b['abstain'] and b['vfe_bits'] is None
    c = free_energy(prior,likelihood,likelihood,prefs,observation=1)
    assert c['information_gain_bits'] == pytest.approx(1) and c['vfe_bits'] == pytest.approx(1)
    assert c['posterior'] == (0.,1.)


@pytest.mark.parametrize('channel', [(), ((.5,.5),(.5,)), ((True,0.),), ((np.bool_(True),0.),), ((.2,.2),), ((float('inf'),0.),)])
def test_channel_validation(channel):
    with pytest.raises(ValueError): capacity(channel)


def test_capacity_resource_bounds_and_unreachable_output():
    g = tuple((1.,)+(0.,)*63 for _ in range(64))
    with pytest.raises(ValueError): capacity(g, iterations=4096)
    result = capacity(g, iterations=1)
    assert result['converged'] and result['lower_bits'] == 0
    with pytest.raises(ValueError): capacity(((1.,),),iterations=True)


def test_nonfinite_cost_and_unrepresentable_debit():
    args=((1.,),(1.,),((1.,),),1,300.,1e-30)
    with pytest.raises(ValueError): Ledger(100.,50.).charge(*args)
    with pytest.raises(ValueError): transition_cost(*args[:-1],float('inf'))
    with pytest.raises(ValueError): Ledger(float('nan'))


def test_simulated_harm_is_visible_to_scorer():
    row = replay(42,(4,))[0]
    assert row.harm and not row.correct and row.energy_gain == -6.5
    assert row.next_state == 2
    assert not hasattr(row.observation,'true_state')


def test_three_stage_offline_integration():
    rows=replay(42,(0,1,2,3)*60)
    # Independent replay scorer creates a finite empirical transition table.
    counts=np.ones((4,4),dtype=int)
    for row in rows:
        counts[row.true_state,row.next_state]+=1
    g=tuple(tuple(map(float,row/row.sum())) for row in counts)
    p=(.25,)*4
    ledger, receipt=Ledger(1e-6).charge(p,p,g,240,300.,1e-12)
    result=capacity(g)
    diag=free_energy(p,g,tuple(tuple(float(i==j) for j in range(4)) for i in range(4)),p,observation=0)
    assert ledger.spent_j==receipt['charged_j'] and 0<=ledger.spent_j<=ledger.budget_j
    assert 0<=result['lower_bits']<=result['upper_bits']<=2+1e-9
    assert sum(diag['posterior'])==pytest.approx(1) and math.isfinite(diag['efe_bits'])
