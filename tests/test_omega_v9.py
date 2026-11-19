import asyncio
import pytest
from omega_x_evolution.multilevel import Team, evolve_teams
from omega_x_evolution.meta import Workflow
from omega_x_evolution.engine import Config, Expression, apply_patch
import json

def test_role_routing_and_validation():
    t=Team(Workflow(('ratio',)),Workflow(('refine',)))
    p=json.dumps({'parent':'-(x+y)'})
    a=asyncio.run(t.proposal()('fast',p,9)); b=asyncio.run(t.proposal()('deep',p,9))
    assert a!=b
    Expression(apply_patch('-(x+y)',a)); Expression(apply_patch('-(x+y)',b))
    with pytest.raises(ValueError): asyncio.run(t.proposal()('unknown',p,9))

def test_population_migration_and_replay():
    cfg=Config(generations=1,islands=2,workers=2,budget=30)
    kw=dict(train_seeds=(41,42),validation_seeds=(51,52),demes=2,population=3,rounds=2,seed=7)
    a=asyncio.run(evolve_teams(cfg,**kw)); b=asyncio.run(evolve_teams(cfg,**kw))
    assert a==b and len(a['migrations'])==2
    assert a['runs']<=a['run_bound'] and len(a['validation_candidate'])==2
    assert (a['selected'] is not None)==a['promoted']

def test_no_leakage_or_runaway_budget():
    cfg=Config(generations=100,islands=16,workers=16)
    with pytest.raises(ValueError): asyncio.run(evolve_teams(cfg))
    with pytest.raises(ValueError): asyncio.run(evolve_teams(Config(),train_seeds=(5,),validation_seeds=(5,)))
