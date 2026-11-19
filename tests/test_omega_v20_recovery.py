import asyncio
import json
import pytest
from omega_x_evolution.checkpoint import CheckpointStore, CheckpointError
from omega_x_evolution.engine import Config
from omega_x_evolution.multilevel import evolve_teams
from omega_x_evolution.team_recovery import evolve_durable
from omega_x_evolution.polyglot import Program
from omega_x_evolution.bitproof import prove


def test_population_checkpoint_matches_original(tmp_path):
    cfg=Config(generations=1,islands=2,workers=2,budget=30)
    kw=dict(train_seeds=(41,42),validation_seeds=(51,52),demes=2,population=3,rounds=2,seed=7)
    baseline=json.loads(json.dumps(asyncio.run(evolve_teams(cfg,**kw))))
    ck=CheckpointStore(tmp_path/'team.db',b't'*32)
    partial=asyncio.run(evolve_durable(cfg,checkpoint=ck,stop_after=1,**kw))
    assert partial['completed_rounds']==1 and not partial['complete']
    final=asyncio.run(evolve_durable(cfg,checkpoint=CheckpointStore(ck.path,b't'*32),resume=True,**kw))
    assert final==baseline
    assert asyncio.run(evolve_durable(cfg,checkpoint=CheckpointStore(ck.path,b't'*32),resume=True,**kw))==baseline
    with pytest.raises(CheckpointError): asyncio.run(evolve_durable(cfg,checkpoint=ck,resume=True,**{**kw,'seed':8}))


def test_bitvector_equivalence_and_counterexample():
    a=Program(('sub',('add',('x',),('y',)),('y',)))
    x=Program(('x',))
    result=prove(a,x)
    assert result['status']=='unsat' and result['proved'] and result['domain_size']==2**32
    assert prove(a,Program(('y',)))['status']=='sat'
    with pytest.raises(ValueError): prove(('exec',),x)
