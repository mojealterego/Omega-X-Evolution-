import asyncio
from dataclasses import replace
import shutil

import pytest
from omega_x_evolution.checkpoint import CheckpointError
from omega_x_evolution.fenced_checkpoint import CheckpointPin, FencedCheckpointStore
from omega_x_evolution.engine import run
from test_engine_memory import fixture, bind, cfg

KEY = b'K'*32
RUN = b'R'*32


def store(path, pin=None, run_id=RUN):
    return FencedCheckpointStore(path, KEY, run_id=run_id, retained=pin)


def test_missing_independent_pin_cannot_resume(tmp_path):
    path=tmp_path/'run.db'; s=store(path); s.initialize({'n':0})
    assert s.pin.generation==0
    with pytest.raises(CheckpointError): store(path).load()
    assert store(path,s.pin).load()==(0,{'n':0})


def test_full_checkpoint_rollback(tmp_path):
    path=tmp_path/'run.db'; s=store(path); s.initialize({'n':0})
    old=s.pin; shutil.copy2(path,tmp_path/'old.db')
    s.save(1,{'n':1}); latest=s.pin
    shutil.copy2(tmp_path/'old.db',path)
    with pytest.raises(CheckpointError): store(path,latest).load()
    assert store(path,old).load()==(0,{'n':0})  # stale external pin is outside guarantee


def test_same_generation_fork_rejected(tmp_path):
    a,b=tmp_path/'a.db',tmp_path/'b.db'
    s=store(a); s.initialize({'n':0}); initial=s.pin
    shutil.copy2(a,b)
    t=store(b,initial); t.load(); t.save(1,{'n':2})
    s.save(1,{'n':1}); assert s.pin!=t.pin
    with pytest.raises(CheckpointError): store(b,s.pin).load()


def test_run_identity_domain_separation(tmp_path):
    path=tmp_path/'run.db'; s=store(path); s.initialize({'n':0})
    other=b'X'*32
    with pytest.raises(ValueError): store(path,s.pin,other)
    with pytest.raises(CheckpointError): store(path,replace(s.pin,run_id=other),other).load()


def test_failed_load_cannot_authorize_save(tmp_path):
    path=tmp_path/'run.db'; s=store(path); s.initialize({'n':0}); s.save(1,{'n':1})
    t=store(path,replace(s.pin,mac=b'Z'*32))
    with pytest.raises(CheckpointError): t.load()
    with pytest.raises(CheckpointError): t.save(2,{'n':2})


def test_stale_writer_cannot_advance_pin(tmp_path):
    path=tmp_path/'run.db'; s=store(path); s.initialize({'n':0}); pin=s.pin
    t=store(path,pin); t.load()
    s.save(1,{'n':1})
    with pytest.raises(CheckpointError): t.save(1,{'n':2})
    assert t.pin==pin and s.pin.generation==1


@pytest.mark.parametrize('changes',[{'generation':True},{'generation':-1},{'mac':b'x'},{'run_id':b'x'}])
def test_pin_validation(changes):
    with pytest.raises(ValueError): CheckpointPin(**({'run_id':RUN,'generation':0,'mac':b'M'*32}|changes))


def test_real_engine_resume_and_rollback(tmp_path):
    p,j,f,s,clock=fixture(tmp_path); adapter=bind(p,j,f,s,clock)
    path=tmp_path/'engine.db'; first=store(path)
    asyncio.run(run(cfg(1),adapter,checkpoint=first)); shutil.copy2(path,tmp_path/'old.db')
    second=store(path,first.pin)
    resumed=asyncio.run(run(cfg(2),adapter,checkpoint=second,resume=True))
    assert resumed==asyncio.run(run(cfg(2),adapter))
    assert second.pin.generation==2
    shutil.copy2(tmp_path/'old.db',path)
    with pytest.raises(CheckpointError): asyncio.run(run(cfg(2),adapter,checkpoint=store(path,second.pin),resume=True))


def test_pin_not_advanced_when_save_fails(tmp_path,monkeypatch):
    from omega_x_evolution.checkpoint import CheckpointStore
    s=store(tmp_path/'run.db'); s.initialize({'n':0}); pin=s.pin
    def fail(*args): raise OSError('injected before commit')
    monkeypatch.setattr(CheckpointStore,'save',fail)
    with pytest.raises(OSError): s.save(1,{'n':1})
    assert s.pin==pin


def test_integrated_source_revocation_and_checkpoint(tmp_path):
    from omega_x_evolution.fenced_checkpoint import run_fenced_memory
    from omega_x_evolution.ontos_epoch_journal_core import IntegrityError
    from test_engine_experience import setup, advance
    from test_ontos_sealed_otce import command
    p,j,f,clock,d,h,x,z,*_=setup(tmp_path)
    g,z=advance(d,h,x,z,f)
    learned=x.view(z,g.fence,source_fence=f.fence)
    assert learned.statistics.n==1
    adapter=replace(d.memory,selector=learned.trusted_active)
    s=store(tmp_path/'engine.db')
    asyncio.run(run_fenced_memory(cfg(1),adapter,source_fence=f.fence,checkpoint=s))
    a=j._journal.anchor; b=j._journal.segments/'segment-0000.db'
    shutil.copy2(a,tmp_path/'old-source-a'); shutil.copy2(b,tmp_path/'old-source-b')
    new=j.append(f.fence,command(p,f,'revoke',{'id':'a'})); assert new.status=='COMMITTED'
    assert d.active(g.fence,source_fence=new.fence) is None
    with pytest.raises(IntegrityError): x.view(z,g.fence,source_fence=new.fence)
    with pytest.raises(IntegrityError):
        asyncio.run(run_fenced_memory(cfg(2),adapter,source_fence=new.fence,checkpoint=store(s.path,s.pin),resume=True))
    shutil.copy2(tmp_path/'old-source-a',a); shutil.copy2(tmp_path/'old-source-b',b)
    with pytest.raises(IntegrityError):
        asyncio.run(run_fenced_memory(cfg(2),adapter,source_fence=new.fence,checkpoint=store(s.path,s.pin),resume=True))
    assert d.active(g.fence,source_fence=new.fence) is None
    with pytest.raises(IntegrityError): x.view(z,g.fence,source_fence=new.fence)


def test_integrated_entry_requires_fenced_store(tmp_path):
    from omega_x_evolution.fenced_checkpoint import run_fenced_memory
    from omega_x_evolution.checkpoint import CheckpointStore
    p,j,f,s,clock=fixture(tmp_path); adapter=bind(p,j,f,s,clock)
    with pytest.raises(ValueError):
        asyncio.run(run_fenced_memory(cfg(1),adapter,source_fence=f.fence,checkpoint=CheckpointStore(tmp_path/'legacy.db',KEY)))
