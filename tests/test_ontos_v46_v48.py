"""Offline TDD: finite statistics, typed IR, and fixed-budget paired campaign."""
from fractions import Fraction
from itertools import product
import json
import math
import pytest

from omega_x_evolution.ontos_v46_statistics import enumerate_null, ood_confusion
from omega_x_evolution.ontos_v47_pure_ir import PureIR, evaluate, compare, render_mlir_subset
from omega_x_evolution.ontos_v48_campaign import run_campaign, SEEDS, ACTION_COUNT


def test_v46_optional_stopping_null_exact():
    result = enumerate_null(Fraction(1,4), Fraction(1,2), horizon=12, threshold=20)
    assert result['paths'] == 4096
    assert result['probability_mass'] == Fraction(1)
    assert result['terminal_expectation'] == Fraction(1)
    assert result['crossing_probability'] <= Fraction(1,20)
    assert result['crossing_probability'] > 0


def test_v46_floored_wealth_is_not_valid_null_e_process():
    result = enumerate_null(Fraction(1,4), Fraction(1,2), horizon=12, threshold=20, floor=Fraction(1))
    assert result['terminal_expectation'] > 1
    assert result['valid_e_process_at_horizon'] is False
    assert result['threshold'] == Fraction(20)


@pytest.mark.parametrize('p,q,horizon,threshold', [
    (Fraction(0),Fraction(1,2),1,2),
    (Fraction(1,2),Fraction(1),1,2),
    (Fraction(1,2),Fraction(1,2),0,2),
    (Fraction(1,2),Fraction(1,3),13,2),
    (Fraction(1,2),Fraction(1,3),3,0),
    (True,Fraction(1,3),3,2),
])
def test_v46_null_fails_closed(p,q,horizon,threshold):
    with pytest.raises(ValueError):
        enumerate_null(p,q,horizon=horizon,threshold=threshold)


def test_v46_ood_confusion_with_abstentions():
    result = ood_confusion((True,False,True,False,True), (True,False,None,True,False))
    assert result['tp'] == 1 and result['tn'] == 1
    assert result['fn'] == 1 and result['fp'] == 1 and result['abstentions'] == 1
    assert result['coverage'] == pytest.approx(.8)
    assert result['recall'] == pytest.approx(.5)
    assert result['false_positive_rate'] == pytest.approx(.5)
    assert ood_confusion((False,False), (None,None))['false_positive_rate'] is None


@pytest.mark.parametrize('truth,prediction', [((True,), (True,False)), ((1,), (True,)), ((True,), (1,)), ((),()), ((True,)*1025,(True,)*1025)])
def test_v46_ood_invalid(truth,prediction):
    with pytest.raises(ValueError):
        ood_confusion(truth,prediction)


def test_v47_i4_wraparound_and_type_checked():
    a = PureIR(('add', ('lit', 15), ('x',)))
    b = PureIR(('sub', ('x',), ('lit', 1)))
    assert evaluate(a, 0, 0) == 15
    assert evaluate(a, 1, 0) == 0
    assert compare(a,b)['verdict'] == 'PASS_EXHAUSTIVE'
    assert compare(a,b)['domain_cases'] == 256


def test_v47_known_counterexample_and_exact_wire_digest():
    a = PureIR(('add', ('x',), ('y',)))
    b = PureIR(('xor', ('x',), ('y',)))
    result = compare(a,b)
    assert result['verdict'] == 'FAIL_COUNTEREXAMPLE'
    x,y = result['counterexample']
    assert evaluate(a,x,y) != evaluate(b,x,y)
    assert result['left_sha256'] != result['right_sha256']
    assert len(result['left_sha256']) == 64
    assert compare(a,b) == compare(a,b)


def test_v47_truncated_search_not_a_proof():
    a = PureIR(('add', ('x',), ('y',)))
    b = PureIR(('xor', ('x',), ('y',)))
    r = compare(a,b,max_cases=1)
    assert r['verdict'] == 'UNKNOWN_BOUND'
    assert r['domain_cases'] == 1


@pytest.mark.parametrize('tree', [
    ('div', ('x',), ('y',)),
    ('lit',16),
    ('lit',True),
    ('add', ('x',)),
    ('add', ('x',), ('y',), ('x',)),
    ('add', ('x',), ('lit',-1)),
    ('x',1),
    ['x'],
    ('mul', ('x',), ('mul', ('x',), ('mul', ('x',), ('mul', ('x',), ('mul', ('x',), ('mul', ('x',), ('mul', ('x',), ('x',)))))))),
])
def test_v47_invalid_ir(tree):
    with pytest.raises(ValueError):
        PureIR(tree)


def test_v47_emitted_mlir_is_bounded_and_deterministic():
    prog = PureIR(('sub', ('mul', ('x',), ('lit',2)), ('y',)))
    out = render_mlir_subset(prog)
    assert 'arith.muli' in out and 'arith.subi' in out
    assert 'func.func' in out and 'arith.constant' in out
    assert out == render_mlir_subset(prog)
    assert '"' not in out


def test_v47_full_small_domain_against_python_reference():
    expr = PureIR(('sub', ('mul', ('x',), ('lit',7)), ('add', ('y',), ('lit',3))))
    for x,y in product(range(16),repeat=2):
        assert evaluate(expr,x,y) == ((x*7)-(y+3))%16


def test_v48_campaign_replay_and_complete_budget():
    r = run_campaign(SEEDS)
    assert r == run_campaign(SEEDS)
    assert r['number_of_seeds'] == 30
    assert r['steps_per_seed'] == 240
    assert r['policies'] == ('cycle','constant','abstain','offset_cycle')
    assert r['total_steps'] == 30*240*4
    assert r['per_seed'] and len(r['per_seed']) == 30
    assert len({x['seed'] for x in r['per_seed']}) == 30
    assert all(x['per_policy'][p]['steps'] == ACTION_COUNT for x in r['per_seed'] for p in r['policies'])
    assert all(x['per_policy'][p]['harm'] == 0 for x in r['per_seed'] for p in r['policies'])
    assert r['holdout_size'] == 10
    assert r['dev_size'] == 20
    assert r['observational_only'] is True
    assert all(x['per_policy']['abstain']['coverage']==0 for x in r['per_seed'])


def test_v48_campaign_paired_statistics_preserve_unfavorable_scores():
    r = run_campaign(SEEDS)
    assert 'paired_differences' in r
    for p,c in r['paired_differences'].items():
        assert p != 'cycle'
        assert c['lower'] <= c['mean'] <= c['upper']
        assert c['n'] == 30
    assert all('trace_sha256' in v for x in r['per_seed'] for v in x['per_policy'].values())
    serialized = json.dumps(r,sort_keys=True,allow_nan=False)
    assert 'NaN' not in serialized
    assert r['summary']['abstain']['unconditional_accuracy'] == 0
    assert r['summary']['abstain']['conditional_accuracy'] is None


@pytest.mark.parametrize('seeds', [(),(1,1), (True,2), (2**32,), tuple(range(65)), [1,2]])
def test_v48_campaign_rejects_invalid_seeds(seeds):
    with pytest.raises(ValueError): run_campaign(seeds)


def test_v48_source_scorer_is_not_consulted_for_actions(monkeypatch):
    import omega_x_evolution.ontos_v48_campaign as mod
    records=[]
    original=mod.replay
    def spy(seed,tape):
        records.append((seed,tape))
        return original(seed,tape)
    monkeypatch.setattr(mod,'replay',spy)
    output=mod.run_campaign((11,13))
    assert len(records) == 8
    assert all(type(tape) is tuple and len(tape)==240 and all(a in range(6) for a in tape) for _,tape in records)
    assert output['number_of_seeds']==2
    assert output['total_steps']==2*240*4


def test_v47_revalidate_even_frozen_ir_against_post_init_tampering():
    original = PureIR(('x',))
    object.__setattr__(original, 'tree', ('div', ('x',), ('y',)))
    with pytest.raises(ValueError):
        evaluate(original,1,1)
    with pytest.raises(ValueError):
        compare(original,PureIR(('x',)))
    with pytest.raises(ValueError):
        render_mlir_subset(original)


def test_v48_matches_pinned_v37_campaign_trace_contract():
    """Check prior published v37-campaign.json, Git blob 77c6788469ae91530c75831fc5f7407eb8c6aaef."""
    report = run_campaign(SEEDS)
    assert report['summary']['cycle']['correct'] == 1788
    assert report['summary']['cycle']['ood'] == 678
    expected = (
        'cff2e2a3574c70ff20bee5ae65bbf918e21c7cf728d0fae1baf338f718ae1ac6',
        'b39f21eed885c15c51373547e299d2eda4140502015618bb20bcd7084fb48234',
        '5bf0e83458cd61edbc8f682fcaee18323b5afeae844629cdc47e2f1c58749aec',
    )
    assert tuple(x['per_policy']['cycle']['trace_sha256'] for x in report['per_seed'][:3]) == expected


def test_v48_real_holdout_and_development_summaries():
    r = run_campaign(SEEDS)
    assert r['splits']['dev']['seed_count'] == 20
    assert r['splits']['holdout']['seed_count'] == 10
    for name in r['policies']:
        dev = r['splits']['dev']['summary'][name]
        held = r['splits']['holdout']['summary'][name]
        full = r['summary'][name]
        assert dev['steps'] == 4800
        assert held['steps'] == 2400
        for key in ('correct', 'harm', 'abstain', 'ood', 'steps'):
            assert dev[key] + held[key] == full[key]
        assert 0 <= held['coverage'] <= 1
    assert r['splits']['holdout']['summary']['abstain']['conditional_accuracy'] is None
