import asyncio
from dataclasses import replace
import sqlite3
import pytest
from shinka.omega.engine import Config, run
from shinka.omega.checkpoint import CheckpointStore, CheckpointError

KEY = b'k' * 32
CFG = Config(seed=5, generations=5, islands=2, workers=2)

def execute(cfg, store=None, resume=False):
    return asyncio.run(run(cfg, checkpoint=store, resume=resume))

def test_resume_matches_uninterrupted_run(tmp_path):
    s = CheckpointStore(tmp_path/'state.db', KEY)
    execute(replace(CFG, generations=2), s)
    assert execute(CFG, s, True) == execute(CFG)
    assert execute(CFG, s, True) == execute(CFG)

@pytest.mark.parametrize('budget', [0, 1, 8])
def test_exhausted_budget_resume_matches_full(tmp_path, budget):
    cfg = replace(CFG, budget=budget)
    s = CheckpointStore(tmp_path/'s.db', KEY)
    execute(replace(cfg, generations=1), s)
    assert execute(cfg,s,True) == execute(cfg)

def test_wrong_key_and_tampering_are_rejected(tmp_path):
    s=CheckpointStore(tmp_path/'s.db',KEY)
    execute(replace(CFG,generations=1),s)
    with pytest.raises(CheckpointError): execute(CFG,CheckpointStore(s.path,b'z'*32),True)
    with sqlite3.connect(s.path) as conn:
        conn.execute("UPDATE checkpoint SET payload = ?",(b'{}',))
    with pytest.raises(CheckpointError): execute(CFG,s,True)

def test_incompatible_config_and_existing_file_rejected(tmp_path):
    s=CheckpointStore(tmp_path/'s.db',KEY)
    execute(replace(CFG,generations=2),s)
    with pytest.raises(CheckpointError): execute(replace(CFG,seed=6),s,True)
    with pytest.raises(CheckpointError): execute(replace(CFG,generations=1),s,True)
    with pytest.raises(CheckpointError): execute(CFG,s)

def test_interrupted_generation_replays_from_last_commit(tmp_path,monkeypatch):
    s=CheckpointStore(tmp_path/'s.db',KEY)
    original=s.save
    def fail(generation,state):
        if generation==3: raise OSError('simulated interruption before commit')
        return original(generation,state)
    monkeypatch.setattr(s,'save',fail)
    with pytest.raises(OSError): execute(CFG,s)
    monkeypatch.setattr(s,'save',original)
    assert s.load()[0]==2
    assert execute(CFG,s,True)==execute(CFG)

def test_stale_writer_cannot_overwrite_newer_state(tmp_path):
    s=CheckpointStore(tmp_path/'s.db',KEY)
    s.initialize({'counter':0})
    s.save(1,{'counter':1})
    with pytest.raises(CheckpointError): s.save(1,{'counter':999})
    assert s.load()==(1,{'counter':1})

def test_external_provider_cannot_use_offline_checkpoint(tmp_path):
    async def external(*args): return ''
    with pytest.raises(ValueError):
        asyncio.run(run(CFG,external,checkpoint=CheckpointStore(tmp_path/'s.db',KEY)))
    assert not (tmp_path/'s.db').exists()


def test_concurrent_stale_writer_is_rejected(tmp_path):
    path=tmp_path/'s.db'
    first=CheckpointStore(path,KEY); second=CheckpointStore(path,KEY)
    first.initialize({'counter':0})
    assert second.load()==(0,{'counter':0})
    first.save(1,{'counter':1})
    with pytest.raises(CheckpointError,match='concurrently'):
        second.save(1,{'counter':2})
    assert second.load()==(1,{'counter':1})


def test_process_exit_during_transaction_preserves_checkpoint(tmp_path):
    import subprocess
    import sys
    s=CheckpointStore(tmp_path/'s.db',KEY)
    execute(replace(CFG,generations=2),s)
    before=s.load()
    proc=subprocess.run([sys.executable,'-c',
        'import sqlite3,sys,os; c=sqlite3.connect(sys.argv[1]); '
        'c.execute("BEGIN IMMEDIATE"); c.execute("UPDATE checkpoint SET payload = ?",(b\'corruption\',)); os._exit(77)',str(s.path)], timeout=10)
    assert proc.returncode==77
    assert s.load()==before
    assert execute(CFG,s,True)==execute(CFG)


def test_cli_resume_across_processes(tmp_path):
    import json
    import subprocess
    import sys
    path=tmp_path/'state.db'; key=tmp_path/'key'; key.write_bytes(KEY)
    command=[sys.executable,'-m','shinka.omega','--seed','5','--islands','2','--workers','2']
    options=['--checkpoint',str(path),'--checkpoint-key-file',str(key)]
    subprocess.run(command+['--generations','2']+options,check=True,capture_output=True,timeout=15)
    resumed=subprocess.run(command+['--generations','5','--resume']+options,check=True,capture_output=True,timeout=15)
    assert json.loads(resumed.stdout)==json.loads(json.dumps(execute(CFG)))


def test_missing_db_cannot_be_created_by_resume(tmp_path):
    path=tmp_path/'missing.db'
    with pytest.raises(CheckpointError): execute(CFG,CheckpointStore(path,KEY),True)
    assert not path.exists()
