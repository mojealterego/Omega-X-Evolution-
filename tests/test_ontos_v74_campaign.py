"""Frozen campaign cardinality, missing-run accounting and paired inference."""
from dataclasses import replace

import pytest

from omega_x_evolution.ontos_v74_campaign import (
    Configuration, CampaignPlan, Run, analyze_campaign, paired_statistics, holm_adjust,
)


def plan():
    configs = tuple(Configuration(f'c{i:02}', 'ABCD'[i%4],
                    'PRIMARY' if i<36 else 'ABLATION', 'L12', 10, f'{i:064x}')
                    for i in range(60))
    return CampaignPlan(tuple(range(30)),configs,(('c04','c00'),('c08','c00')),123,'a'*64)


def rows(p):
    return tuple(Run(c.name,seed,'COMPLETED',10 if c.name=='c04' else 5,'b'*64)
                 for c in p.configurations for seed in p.seeds)


def analyze(p, runs):
    return analyze_campaign(p,p.digest(),runs)


def test_grid_frozen_and_complete():
    p = plan(); r = analyze(p,rows(p))
    assert r['planned'] == {'PRIMARY':1080,'ABLATION':720}
    assert r['recorded'] == 1800 and r['missing'] == 0 and r['failed'] == 0
    assert r['configurations']['c04']['correct'] == 300
    assert r['configurations']['c00']['correct'] == 150
    assert r['comparisons'][0]['mean_difference'] == .5
    assert r['comparisons'][1]['mean_difference'] == 0
    assert r['comparisons'][0]['p_holm'] < .01
    assert r['comparisons'][1]['p_holm'] == 1
    assert r['release_authorized'] is False and r['source_reproduction_verified'] is False
    assert r == analyze(p,tuple(reversed(rows(p))))


def test_missing_and_failed_never_dropped():
    p = plan(); runs = list(rows(p)); runs.pop(0)
    runs[0] = replace(runs[0],status='FAILED',correct=0)
    r = analyze(p,tuple(runs))
    c = r['configurations']['c00']
    assert (r['missing'],r['failed']) == (1,1)
    assert c['planned_trials']==300 and c['correct']==140
    assert c['missing']==1 and c['failed']==1
    assert r['comparisons'][0]['n']==30
    assert r['all_runs_recorded'] is False


def test_unregistered_duplicate_and_overcount_fail_closed():
    p = plan(); r=rows(p); first=r[0]
    for extra in (first,replace(first,seed=99),replace(first,configuration='unknown'),replace(first,correct=11)):
        with pytest.raises(ValueError): analyze(p,r+(extra,))
    with pytest.raises(ValueError): analyze_campaign(p,'f'*64,r)
    with pytest.raises(ValueError): Run('c00',0,'FAILED',1,'b'*64)


@pytest.mark.parametrize('change', [
    lambda p:replace(p,seeds=p.seeds[:-1]),
    lambda p:replace(p,seeds=(0,)*30),
    lambda p:replace(p,configurations=p.configurations[:-1]),
    lambda p:replace(p,comparisons=(('c01','c00'),)),
    lambda p:replace(p,comparisons=(('c04','c00'),('c00','c04'))),
    lambda p:replace(p,configurations=p.configurations[:-1]+(p.configurations[0],)),
])
def test_invalid_preregistration(change):
    with pytest.raises(ValueError): change(plan())


def test_exact_sign_flip_and_bootstrap_reference():
    # Four identical paired improvements: only two of sixteen sign assignments
    # are as extreme as observed. Constant differences have a point interval.
    r = paired_statistics((5,5,5,5),10,seed=7,family_size=1)
    assert r['mean_difference']==.5 and r['p_raw']==.125
    assert r['ci_lower']==r['ci_upper']==.5
    assert r['permutations']==16 and r['permutation_method']=='EXACT'
    assert paired_statistics((0,0,0,0),10,seed=7,family_size=1)['p_raw']==1
    assert paired_statistics((1,-1,1,-1),10,seed=7,family_size=1)['p_raw']==1


def test_holm_and_deterministic_monte_carlo():
    assert holm_adjust((.01,.04,.03)) == pytest.approx((.03,.06,.06))
    r = paired_statistics((1,)*30,10,seed=9,family_size=2)
    assert r['permutation_method']=='MONTE_CARLO_PLUS_ONE'
    assert r['permutations']==8192 and r['p_raw']>=1/8193
    assert r==paired_statistics((1,)*30,10,seed=9,family_size=2)


def test_plan_digest_binds_protocol_and_analysis_choices():
    p=plan()
    assert p.digest()!=replace(p,analysis_seed=124).digest()
    assert p.digest()!=replace(p,protocol_sha256='f'*64).digest()
    assert p.digest()!=replace(p,comparisons=(('c04','c00'),)).digest()
