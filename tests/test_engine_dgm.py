import asyncio
from dataclasses import replace
import shutil

import pytest
from omega_x_evolution.engine import Config
from omega_x_evolution.engine_dgm import Selector, Plan, DGMJournal, BASE, mutations
from omega_x_evolution.ontos_epoch_journal_core import IntegrityError
from test_engine_memory import fixture, bind
from test_ontos_sealed_otce import command


def setup(tmp):
    p,j,f,s,clock=fixture(tmp)
    memory=bind(p,j,f,s,clock)
    plan=Plan(Config(seed=41,generations=1,islands=1,workers=2,budget=20),2,3,41)
    a,b=tmp/'dgm-anchor',tmp/'dgm-segments'
    a.mkdir(mode=0o700); b.mkdir(mode=0o700)
    d=DGMJournal(a/'floor.db',b,memory,plan,plan.pin(memory))
    return p,j,f,s,clock,memory,plan,d,d.initialize(source_fence=f.fence),a,b


def test_selector_and_mutations():
    assert BASE.seed('fast',123)==123
    assert BASE.seed('deep',123)==123
    assert mutations(BASE,3,41)==mutations(BASE,3,41)
    assert len(set(mutations(BASE,3,41)))==3
    assert mutations(BASE,3,41)[0]==BASE
    assert Selector(0,1,2).seed('deep',2**32-1)==2


@pytest.mark.parametrize('args',[(True,0,0),(4,0,0),(1,-1,0),(1,0,17)])
def test_invalid_selector(args):
    with pytest.raises(ValueError): Selector(*args)


def test_real_round_replay_and_lineage(tmp_path):
    p,j,f,s,clock,m,plan,d,h,a,b=setup(tmp_path)
    first=asyncio.run(d.step(h,source_fence=f.fence)); assert first.status=='COMMITTED'
    assert first.record['release_authorized'] is False
    assert first.record['parent']==[1,0,0]
    assert len(first.record['training'])==3
    other=DGMJournal(a/'floor.db',b,m,plan,plan.pin(m))
    assert other.active(first.fence,source_fence=f.fence)==first.active
    second=asyncio.run(other.step(first.fence,source_fence=f.fence)); assert second.status=='COMMITTED'
    assert second.record['parent']==first.record['active']
    assert other.active(second.fence,source_fence=f.fence)==second.active
    assert asyncio.run(other.step(second.fence,source_fence=f.fence)).status=='EXHAUSTED'
    with pytest.raises(IntegrityError): other.active(h,source_fence=f.fence)


def test_revoke_invalidates_research_state(tmp_path):
    p,j,f,s,clock,m,plan,d,h,*_=setup(tmp_path)
    first=asyncio.run(d.step(h,source_fence=f.fence))
    f=j.append(f.fence,command(p,f,'revoke',{'id':'a'})); assert f.status=='COMMITTED'
    assert d.active(first.fence,source_fence=f.fence) is None
    with pytest.raises(IntegrityError): asyncio.run(d.step(first.fence,source_fence=f.fence))


def test_source_mutation_during_evaluation(tmp_path,monkeypatch):
    import omega_x_evolution.engine_dgm as mod
    p,j,f,s,clock,m,plan,d,h,*_=setup(tmp_path)
    real=mod.run
    async def change(*args,**kwargs):
        out=await real(*args,**kwargs)
        g=j.append(f.fence,command(p,f,'revoke',{'id':'a'})); assert g.status=='COMMITTED'
        monkeypatch.setattr(mod,'run',real)
        return out
    monkeypatch.setattr(mod,'run',change)
    with pytest.raises(IntegrityError): asyncio.run(d.step(h,source_fence=f.fence))
    assert d._journal.read(h).state==()


def test_full_database_rollback_detected(tmp_path):
    p,j,f,s,clock,m,plan,d,h,a,b=setup(tmp_path)
    shutil.copy2(a/'floor.db',tmp_path/'old-a'); shutil.copy2(b/'segment-0000.db',tmp_path/'old-b')
    g=asyncio.run(d.step(h,source_fence=f.fence))
    shutil.copy2(tmp_path/'old-a',a/'floor.db'); shutil.copy2(tmp_path/'old-b',b/'segment-0000.db')
    with pytest.raises(IntegrityError): d.active(g.fence,source_fence=f.fence)


def test_clock_expiry_and_plan_binding(tmp_path):
    p,j,f,s,clock,m,plan,d,h,a,b=setup(tmp_path)
    with pytest.raises(ValueError): DGMJournal(a/'floor.db',b,m,replace(plan,seed=42),plan.pin(m))
    clock[0]=20
    assert d.active(h,source_fence=f.fence) is None
    with pytest.raises(IntegrityError): asyncio.run(d.step(h,source_fence=f.fence))


def test_selector_is_bound_to_actual_engine_contract(tmp_path):
    from omega_x_evolution.engine import run
    p,j,f,s,clock,m,plan,d,h,*_=setup(tmp_path)
    mutated=replace(m,selector=Selector(0,1,1))
    assert mutated.contract()!=m.contract()
    assert asyncio.run(mutated('fast','{"parent":"-(x+y)"}',0))==asyncio.run(mutated('fast','{"parent":"-(x+y)"}',123))
    report=asyncio.run(run(plan.config,mutated))
    assert report['mode']=='memory-guided-offline' and report['release_authorized'] is False
    assert report['memory_contract']==mutated.contract()
    with pytest.raises((IntegrityError,ValueError)): asyncio.run(run(plan.config,replace(m,selector=(0,1,1))))


def test_replay_rejects_forged_promotion(tmp_path):
    from omega_x_evolution.ontos_v72_jcs import canonical_json
    p,j,f,s,clock,m,plan,d,h,*_=setup(tmp_path)
    g=asyncio.run(d.step(h,source_fence=f.fence))
    altered=dict(g.record,promoted=not g.record['promoted'])
    assert d._replay((),canonical_json(altered)) is None
    assert d._replay((),canonical_json(dict(g.record,release_authorized=True))) is None


def test_positive_promotion_and_inheritance(tmp_path):
    p,j,f,s,clock,m,plan,d,h,*_=setup(tmp_path)
    a,b=tmp_path/'other-a',tmp_path/'other-b'; a.mkdir(mode=0o700); b.mkdir(mode=0o700)
    plan=Plan(Config(generations=1,islands=1,workers=1,budget=20),2,5,41)
    d=DGMJournal(a/'floor.db',b,m,plan,plan.pin(m)); h=d.initialize(source_fence=f.fence)
    g=asyncio.run(d.step(h,source_fence=f.fence))
    assert g.record['promoted'] and g.active==Selector(0,0,0)
    assert g.record['after'][1][0]>g.record['before'][1][0]
    g2=asyncio.run(d.step(g.fence,source_fence=f.fence))
    assert g2.record['parent']==g.active.wire() and g2.active==g.active
    f=j.append(f.fence,command(p,f,'revoke',{'id':'a'})); assert f.status=='COMMITTED'
    assert d.active(g2.fence,source_fence=f.fence) is None


def test_reject_challenger_without_strict_validation_gain(tmp_path):
    p,j,f,s,clock,m,plan,d,h,*_=setup(tmp_path)
    a,b=tmp_path/'other-a',tmp_path/'other-b'; a.mkdir(mode=0o700); b.mkdir(mode=0o700)
    plan=Plan(Config(generations=1,islands=1,workers=1,budget=20),2,5,5)
    d=DGMJournal(a/'floor.db',b,m,plan,plan.pin(m))
    g=asyncio.run(d.step(d.initialize(source_fence=f.fence),source_fence=f.fence))
    assert g.record['challenger']==[0,0,0] and not g.record['promoted'] and g.active==BASE


def test_interrupted_round_recovery(tmp_path,monkeypatch):
    from omega_x_evolution.ontos_managed_journal import ManagedJournal
    p,j,f,s,clock,m,plan,d,h,a,b=setup(tmp_path)
    original=ManagedJournal._finish
    def crash(self,*args):
        if self is d._journal: raise RuntimeError('injected round commit crash')
        return original(self,*args)
    with monkeypatch.context() as patch:
        patch.setattr(ManagedJournal,'_finish',crash)
        with pytest.raises(RuntimeError,match='injected'): asyncio.run(d.step(h,source_fence=f.fence))
    d=DGMJournal(a/'floor.db',b,m,plan,plan.pin(m))
    with pytest.raises(IntegrityError): d.active(h,source_fence=f.fence)
    new=d.recover_from_anchor(source_fence=f.fence)
    assert len(d._journal.read(new).state)==1 and d.active(new,source_fence=f.fence) is not None


def test_native_parallel_round_matches_serial(tmp_path):
    p,j,f,s,clock,m,plan,d,h,*_=setup(tmp_path)
    a,b=tmp_path/'other-a',tmp_path/'other-b'; a.mkdir(mode=0o700); b.mkdir(mode=0o700)
    other=DGMJournal(a/'floor.db',b,m,plan,plan.pin(m)); h2=other.initialize(source_fence=f.fence)
    one=asyncio.run(d.step(h,source_fence=f.fence))
    two=asyncio.run(other.step(h2,source_fence=f.fence,evaluation_processes=2))
    assert one.record==two.record and one.active==two.active


def test_changed_selector_rejects_engine_checkpoint(tmp_path):
    from omega_x_evolution.engine import run
    from omega_x_evolution.checkpoint import CheckpointStore, CheckpointError
    p,j,f,s,clock,m,plan,d,h,*_=setup(tmp_path)
    checkpoint=CheckpointStore(tmp_path/'engine.db',b'k'*32)
    asyncio.run(run(plan.config,m,checkpoint=checkpoint))
    with pytest.raises(CheckpointError):
        asyncio.run(run(replace(plan.config,generations=2),replace(m,selector=Selector(0,0,0)),checkpoint=checkpoint,resume=True))


def test_source_rollback_cannot_reuse_old_adapter(tmp_path):
    p,j,f,s,clock,m,plan,d,h,*_=setup(tmp_path)
    anchor=j._journal.anchor; segment=j._journal.segments/'segment-0000.db'
    shutil.copy2(anchor,tmp_path/'old-source-a'); shutil.copy2(segment,tmp_path/'old-source-s')
    g=asyncio.run(d.step(h,source_fence=f.fence))
    new=j.append(f.fence,command(p,f,'revoke',{'id':'a'})); assert new.status=='COMMITTED'
    shutil.copy2(tmp_path/'old-source-a',anchor); shutil.copy2(tmp_path/'old-source-s',segment)
    assert d.active(g.fence,source_fence=new.fence) is None
    with pytest.raises(IntegrityError): asyncio.run(d.step(g.fence,source_fence=new.fence))
    with pytest.raises(TypeError): d.active(g.fence)
