import asyncio
import json
from dataclasses import replace

import pytest
from omega_x_evolution.engine import Config, run, apply_patch, Expression
from omega_x_evolution.meta import Workflow, evolve, proposal_for, promotion


def test_genome_is_bounded_and_cannot_modify_gate():
    for operators in [(), ('exec',), ('sample',)*9, ('disable_gate',)]:
        with pytest.raises(ValueError): Workflow(operators)
    with pytest.raises(ValueError): Workflow(('sample',), 0)


def test_proposal_is_replayable_and_validated():
    prop=proposal_for(Workflow(('refine','ratio','sample'),2))
    prompt=json.dumps({'parent':'-(x+y)'})
    a=asyncio.run(prop('deep',prompt,5)); b=asyncio.run(prop('deep',prompt,5))
    assert a==b
    Expression(apply_patch('-(x+y)',a))


def test_promotion_requires_all_heldout_seeds_and_budgets():
    baseline=[(.5,.5,10),(.6,.6,10)]
    assert promotion(baseline,[(.6,.6,9),(.7,.7,10)],10)
    assert not promotion(baseline,[(.6,.6,9),(.5,.9,9)],10)
    assert not promotion(baseline,[(.6,.6,11),(.7,.7,10)],10)
    assert not promotion(baseline,[(.6,.4,9),(.7,.7,10)],10)


def test_meta_search_reproducible_and_separate_validation():
    cfg=Config(generations=2,islands=1,workers=2,budget=20)
    kwargs=dict(train_seeds=(5,7), validation_seeds=(11,13), rounds=2,population=3,seed=42)
    a=asyncio.run(evolve(cfg,**kwargs)); b=asyncio.run(evolve(cfg,**kwargs))
    assert a==b
    assert a['training_seeds']==[5,7] and a['validation_seeds']==[11,13]
    assert len(a['history'])<=6 and a['evaluated_workflows']<=6
    assert a['selected'] is None or a['promoted']
    assert a['total_run_budget_bound'] == (6*2+2*2)*cfg.budget
    with pytest.raises(ValueError): asyncio.run(evolve(cfg,train_seeds=(5,),validation_seeds=(5,)))


def test_invalid_holdout_cannot_be_promoted():
    assert not promotion([(.5,-1.,10)],[(.6,-1.,9)],10)


def test_simplification_operator_integrates_v6():
    p='-(x*1+y/1)'
    result=asyncio.run(proposal_for(Workflow(('simplify',)))('fast',json.dumps({'parent':p}),1))
    rewritten=apply_patch(p,result)
    assert Expression(rewritten).operations<Expression(p).operations
