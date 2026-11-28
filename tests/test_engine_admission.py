import asyncio
import json
import subprocess
import sys
from dataclasses import replace

import pytest
from omega_x_evolution.engine import run
from omega_x_evolution.checkpoint import CheckpointStore
from omega_x_evolution.ontos_epoch_journal_core import IntegrityError
from test_engine_memory import fixture, bind, cfg
from test_durable_checkpoint import setup
from test_ontos_sealed_otce import command


def test_memory_requires_independent_fence(tmp_path):
    p,j,f,s,clock=fixture(tmp_path); a=bind(p,j,f,s,clock)
    with pytest.raises(IntegrityError): asyncio.run(run(cfg(1),a))
    assert asyncio.run(run(cfg(1),a,source_fence=f.fence))['release_authorized'] is False


def test_memory_rejects_legacy_even_with_opt_in(tmp_path):
    p,j,f,s,clock=fixture(tmp_path); a=bind(p,j,f,s,clock)
    path=tmp_path/'legacy.db'
    for legacy in (False,True):
        with pytest.raises(ValueError): asyncio.run(run(cfg(1),a,source_fence=f.fence,checkpoint=CheckpointStore(path,b'k'*32),legacy_research=legacy))
    assert not path.exists()


def test_offline_legacy_requires_explicit_research(tmp_path):
    path=tmp_path/'legacy.db'; s=CheckpointStore(path,b'k'*32)
    with pytest.raises(ValueError): asyncio.run(run(cfg(1),checkpoint=s))
    assert not path.exists()
    assert asyncio.run(run(cfg(1),checkpoint=s,legacy_research=True))==asyncio.run(run(cfg(1)))


def test_direct_memory_rollback_refused_with_current_fence(tmp_path):
    import shutil
    p,j,f,s,clock=fixture(tmp_path); a=bind(p,j,f,s,clock)
    anchor=j._journal.anchor; segment=j._journal.segments/'segment-0000.db'
    shutil.copy2(anchor,tmp_path/'a'); shutil.copy2(segment,tmp_path/'b')
    new=j.append(f.fence,command(p,f,'revoke',{'id':'a'})); assert new.status=='COMMITTED'
    shutil.copy2(tmp_path/'a',anchor); shutil.copy2(tmp_path/'b',segment)
    with pytest.raises(IntegrityError): asyncio.run(run(cfg(1),a,source_fence=new.fence))


def test_durable_direct_and_parallel_resume(tmp_path):
    p,j,f,s,clock=fixture(tmp_path); a=bind(p,j,f,s,clock)
    store,reopen=setup(tmp_path)
    asyncio.run(run(cfg(1),a,checkpoint=store,source_fence=f.fence))
    result=asyncio.run(run(cfg(2),a,checkpoint=reopen(),resume=True,source_fence=f.fence,evaluation_processes=2))
    assert result==asyncio.run(run(cfg(2),a,source_fence=f.fence))


def test_cli_durable_across_processes(tmp_path):
    a,b=tmp_path/'anchor',tmp_path/'data'; a.mkdir(mode=0o700); b.mkdir(mode=0o700)
    key,ak,rid=[tmp_path/x for x in ('key','anchor-key','run-id')]
    for path,value in ((key,b'k'*32),(ak,b'a'*32),(rid,b'r'*32)): path.write_bytes(value); path.chmod(0o600)
    cmd=[sys.executable,'-m','shinka.omega','--seed','101','--islands','1','--workers','2','--budget','100','--concurrency','2','--checkpoint',str(b/'db'),'--checkpoint-key-file',str(key)]
    def invoke(extra): return subprocess.run(cmd+extra,capture_output=True,text=True,timeout=15)
    assert invoke(['--generations','1']).returncode!=0
    flags=['--checkpoint-anchor',str(a/'floor'),'--anchor-key-file',str(ak),'--run-id-file',str(rid)]
    first=invoke(flags+['--generations','1','--provision-anchor']); assert first.returncode==0,first.stderr
    resumed=invoke(flags+['--generations','2','--resume']); assert resumed.returncode==0,resumed.stderr
    assert json.loads(resumed.stdout)==json.loads(json.dumps(asyncio.run(run(cfg(2)))))
