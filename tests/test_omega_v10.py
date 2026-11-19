import asyncio
import pytest
from omega_x_evolution.engine import Config
from omega_x_evolution.checkpoint import CheckpointStore, CheckpointError
from omega_x_evolution.recursive import improve

CFG=Config(generations=1,islands=2,workers=2,budget=30)

def test_replay_and_fresh_gates(tmp_path):
    kw=dict(rounds=3,population=3,seed=901)
    a=asyncio.run(improve(CFG,**kw))
    assert a==asyncio.run(improve(CFG,**kw))
    assert len(a['history'])==3
    seen=[]
    for r in a['history']:
        seen+=r['train_seeds']+r['validation_seeds']
        if r['promoted']:
            assert r['active']==r['challenger']
        else:
            assert r['active']==r['incumbent']
    assert len(seen)==len(set(seen))
    assert a['runs']<=a['run_bound']
    ck=CheckpointStore(tmp_path/'outer.db',b'k'*32)
    asyncio.run(improve(CFG,**kw,checkpoint=ck,stop_after=1))
    assert a==asyncio.run(improve(CFG,**kw,checkpoint=ck,resume=True))
    with pytest.raises(CheckpointError):
        asyncio.run(improve(CFG,**{**kw,'seed':902},checkpoint=ck,resume=True))

def test_limits_and_resume(tmp_path):
    with pytest.raises(ValueError): asyncio.run(improve(CFG,rounds=100))
    with pytest.raises(ValueError): asyncio.run(improve(CFG,resume=True))
    with pytest.raises(ValueError): asyncio.run(improve(CFG,stop_after=0))
    with pytest.raises(ValueError): asyncio.run(improve(Config(generations=100,islands=16,workers=16),rounds=8,population=8))

def test_tampered_outer_checkpoint_fails_closed(tmp_path):
    import sqlite3
    path=tmp_path/'outer.db'; store=CheckpointStore(path,b'k'*32)
    asyncio.run(improve(CFG,rounds=2,population=2,checkpoint=store,stop_after=1))
    with sqlite3.connect(path) as db:
        db.execute("UPDATE checkpoint SET payload=?",(b'{}',))
    with pytest.raises(CheckpointError):
        asyncio.run(improve(CFG,rounds=2,population=2,checkpoint=store,resume=True))


def test_failed_formal_gate_prevents_checkpoint_creation(tmp_path,monkeypatch):
    from omega_x_evolution import recursive
    monkeypatch.setattr(recursive,'prove_rules',lambda: {'invalid':'unknown'})
    path=tmp_path/'outer.db'
    with pytest.raises(RuntimeError,match='formal gate'):
        asyncio.run(improve(CFG,checkpoint=CheckpointStore(path,b'k'*32)))
    assert not path.exists()
