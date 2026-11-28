import asyncio
import shutil
from concurrent.futures import ThreadPoolExecutor

import pytest
from omega_x_evolution.checkpoint import CheckpointError
from omega_x_evolution.durable_checkpoint import DurableCheckpointStore
from omega_x_evolution.engine import run
from test_engine_memory import fixture, bind, cfg


def setup(tmp):
    a,b=tmp/'checkpoint-anchor',tmp/'checkpoint-data'
    a.mkdir(mode=0o700); b.mkdir(mode=0o700)
    def store(): return DurableCheckpointStore(b/'state.db',b'K'*32,anchor=a/'floor.db',anchor_key=b'A'*32,run_id=b'R'*32)
    s=store(); s.provision(); return s,store


def test_durable_reopen_and_stable_rollback(tmp_path):
    s,open_store=setup(tmp_path); s.initialize({'n':0}); shutil.copy2(s.path,tmp_path/'old')
    s.save(1,{'n':1}); assert open_store().load()==(1,{'n':1})
    shutil.copy2(tmp_path/'old',s.path)
    with pytest.raises(CheckpointError): open_store().load()


@pytest.mark.parametrize('phase',['_apply','_finish'])
@pytest.mark.parametrize('genesis',[True,False])
def test_recover_prepared_commit(tmp_path,monkeypatch,phase,genesis):
    s,open_store=setup(tmp_path)
    if not genesis: s.initialize({'n':0})
    def crash(*args): raise RuntimeError('injected')
    with monkeypatch.context() as m:
        m.setattr(s,phase,crash)
        with pytest.raises(RuntimeError):
            if genesis: s.initialize({'n':0})
            else: s.save(1,{'n':1})
    t=open_store(); n=0 if genesis else 1
    assert t.load()==(n,{'n':n})
    assert open_store().load()==(n,{'n':n})


def test_pending_old_snapshot_is_rolled_forward(tmp_path,monkeypatch):
    s,open_store=setup(tmp_path); s.initialize({'n':0}); shutil.copy2(s.path,tmp_path/'old')
    def crash(*args): raise RuntimeError('injected')
    monkeypatch.setattr(s,'_finish',crash)
    with pytest.raises(RuntimeError): s.save(1,{'n':1})
    shutil.copy2(tmp_path/'old',s.path)
    assert open_store().load()==(1,{'n':1})


def test_concurrent_writer_cas(tmp_path):
    s,open_store=setup(tmp_path); s.initialize({'n':0}); t=open_store(); t.load()
    def save(store,n):
        try: store.save(1,{'n':n}); return True
        except CheckpointError: return False
    with ThreadPoolExecutor(2) as pool:
        a,b=pool.submit(save,s,1),pool.submit(save,t,2)
        assert sum((a.result(),b.result()))==1
    assert open_store().load()[0]==1


def test_anchor_tamper_and_wrong_key(tmp_path):
    import sqlite3
    s,open_store=setup(tmp_path); s.initialize({'n':0})
    wrong=DurableCheckpointStore(s.path,b'K'*32,anchor=s.anchor,anchor_key=b'B'*32,run_id=b'R'*32)
    with pytest.raises(CheckpointError): wrong.load()
    with sqlite3.connect(s.anchor) as db: db.execute('UPDATE floor SET generation=7')
    with pytest.raises(CheckpointError): open_store().load()


def test_missing_anchor_and_duplicate_provision(tmp_path):
    s,open_store=setup(tmp_path); s.initialize({'n':0})
    with pytest.raises(CheckpointError): s.provision()
    s.anchor.unlink()
    with pytest.raises(CheckpointError): open_store().load()
    with pytest.raises(CheckpointError): open_store().provision()


def test_real_engine_resume(tmp_path):
    p,j,f,search,clock=fixture(tmp_path); adapter=bind(p,j,f,search,clock)
    s,open_store=setup(tmp_path)
    asyncio.run(run(cfg(1),adapter,checkpoint=s))
    assert asyncio.run(run(cfg(2),adapter,checkpoint=open_store(),resume=True))==asyncio.run(run(cfg(2),adapter))


def test_intent_encrypted_and_tamper_fails_closed(tmp_path,monkeypatch):
    import sqlite3
    s,open_store=setup(tmp_path); s.initialize({'n':0})
    secret='secret-intent-32819abc'
    def crash(*args): raise RuntimeError('injected')
    monkeypatch.setattr(s,'_apply',crash)
    with pytest.raises(RuntimeError): s.save(1,{'text':secret})
    assert secret.encode() not in s.anchor.read_bytes()
    with sqlite3.connect(s.anchor) as db:
        blob=db.execute('SELECT intent FROM floor').fetchone()[0]
        db.execute('UPDATE floor SET intent=?',(bytes([blob[0]^1])+blob[1:],))
    with pytest.raises(CheckpointError): open_store().load()


def test_invalid_state_never_prepared(tmp_path):
    s,open_store=setup(tmp_path); s.initialize({'n':0})
    with pytest.raises(CheckpointError): s.save(1,[])
    assert open_store().load()==(0,{'n':0})


def test_dual_fenced_entry(tmp_path):
    from omega_x_evolution.fenced_checkpoint import run_fenced_memory
    from omega_x_evolution.ontos_epoch_journal_core import IntegrityError
    from test_ontos_sealed_otce import command
    p,j,f,search,clock=fixture(tmp_path); adapter=bind(p,j,f,search,clock)
    s,open_store=setup(tmp_path)
    asyncio.run(run_fenced_memory(cfg(1),adapter,source_fence=f.fence,checkpoint=s))
    assert asyncio.run(run_fenced_memory(cfg(2),adapter,source_fence=f.fence,checkpoint=open_store(),resume=True))==asyncio.run(run(cfg(2),adapter))
    new=j.append(f.fence,command(p,f,'revoke',{'id':'a'})); assert new.status=='COMMITTED'
    with pytest.raises(IntegrityError):
        asyncio.run(run_fenced_memory(cfg(3),adapter,source_fence=new.fence,checkpoint=open_store(),resume=True))


@pytest.mark.parametrize('phase',['_apply','_finish'])
def test_real_process_exit_during_commit(tmp_path,phase):
    import subprocess,sys
    s,open_store=setup(tmp_path); s.initialize({'n':0})
    script='''import os,sys
from omega_x_evolution.durable_checkpoint import DurableCheckpointStore
s=DurableCheckpointStore(sys.argv[1],b'K'*32,anchor=sys.argv[2],anchor_key=b'A'*32,run_id=b'R'*32)
s.load()
setattr(s,sys.argv[3],lambda *args:os._exit(77))
s.save(1,{'n':1})
'''
    got=subprocess.run([sys.executable,'-c',script,str(s.path),str(s.anchor),phase],timeout=10)
    assert got.returncode==77
    assert open_store().load()==(1,{'n':1})
