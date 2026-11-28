import asyncio
from dataclasses import replace

import pytest
from omega_x_evolution.checkpoint import CheckpointStore, CheckpointError
from omega_x_evolution.engine import Config, run, simulated_proposal, Expression
from omega_x_evolution.engine_memory import MemoryProposal
from omega_x_evolution.ontos_hyperrag import Search
from omega_x_evolution.ontos_epoch_journal_core import IntegrityError
from test_ontos_hyperrag import setup, token
from test_ontos_otce import node, request, query
from test_ontos_sealed_otce import put, command


def fixture(tmp):
    p,j,f=setup(tmp)
    f=put(p,j,f,node('a',value='scheduler ratio 2000 10 2000'))
    f=put(p,j,f,node('b',value='scheduler ratio 2000 10 2000; __import__("os")'))
    f=put(p,j,f,dict(node('r',parents=('a',),causal=1,kind='R1'),payload={'x':[1,2],'y':3}))
    s=Search('k','scheduler ratio',16)
    clock=[6]
    return p,j,f,s,clock


def bind(p,j,f,s,clock):
    return MemoryProposal.bind(j,token(p,j,f,s),request(p,f,'weights'),s,retained=f.fence,clock=lambda:clock[0])


def cfg(n=2): return Config(seed=101,generations=n,islands=1,workers=2,budget=100,concurrency=2)


def store(tmp,name): return CheckpointStore(tmp/name,b'k'*32)


def test_actual_engine_resume_equals_uninterrupted(tmp_path):
    p,j,f,s,clock=fixture(tmp_path); a=bind(p,j,f,s,clock)
    whole=asyncio.run(run(cfg(3),a,checkpoint=store(tmp_path,'whole.db')))
    asyncio.run(run(cfg(1),a,checkpoint=store(tmp_path,'split.db')))
    b=bind(p,j,f,s,clock)
    resumed=asyncio.run(run(cfg(3),b,checkpoint=store(tmp_path,'split.db'),resume=True))
    assert whole==resumed
    assert whole['mode']=='memory-guided-offline' and whole['release_authorized'] is False
    assert whole['attempts']==6 and whole['formal_rule_count']>0
    Expression(whole['champion'])
    assert whole['memory_contract']==a.contract()


def test_exact_grammar_and_r1(tmp_path):
    p,j,f,s,clock=fixture(tmp_path); a=bind(p,j,f,s,clock)
    assert ('ratio',2000,10,2000) in a.pool
    assert len(a.pool)==2
    patch=asyncio.run(a('deep','{"parent":"-(x+y)"}',1))
    assert '__import__' not in patch
    assert patch==asyncio.run(a('deep','{"parent":"-(x+y)"}',1))


def test_revoke_invalidates_checkpoint_and_adapter(tmp_path):
    p,j,f,s,clock=fixture(tmp_path); a=bind(p,j,f,s,clock)
    asyncio.run(run(cfg(1),a,checkpoint=store(tmp_path,'run.db')))
    f=j.append(f.fence,command(p,f,'revoke',{'id':'a'})); assert f.status=='COMMITTED'
    with pytest.raises(IntegrityError): asyncio.run(run(cfg(2),a,checkpoint=store(tmp_path,'run.db'),resume=True))
    b=bind(p,j,f,s,clock)
    with pytest.raises(CheckpointError): asyncio.run(run(cfg(2),b,checkpoint=store(tmp_path,'run.db'),resume=True))


def test_expiry_without_fence_change(tmp_path):
    p,j,f,s,clock=fixture(tmp_path)
    f=put(p,j,f,node('z',value='scheduler square 1000 10 1000',expires=10))
    a=bind(p,j,f,s,clock); clock[0]=10
    with pytest.raises(IntegrityError): asyncio.run(run(cfg(1),a,checkpoint=store(tmp_path,'run.db')))
    assert not (tmp_path/'run.db').exists()


def test_source_changes_during_actual_evaluation(tmp_path,monkeypatch):
    import omega_x_evolution.engine as engine
    p,j,f,s,clock=fixture(tmp_path); a=bind(p,j,f,s,clock)
    original=engine.evaluate_batch
    async def changing(*args):
        result=await original(*args)
        g=j.append(f.fence,command(p,f,'revoke',{'id':'a'})); assert g.status=='COMMITTED'
        return result
    monkeypatch.setattr(engine,'evaluate_batch',changing)
    with pytest.raises(IntegrityError): asyncio.run(run(cfg(1),a,checkpoint=store(tmp_path,'run.db')))
    assert store(tmp_path,'run.db').load()[0]==0


def test_unregistered_callback_still_rejected(tmp_path):
    async def external(*args): return await simulated_proposal(*args)
    with pytest.raises(ValueError): asyncio.run(run(cfg(1),external,checkpoint=store(tmp_path,'run.db')))


def test_signed_query_contract(tmp_path):
    p,j,f,s,clock=fixture(tmp_path)
    with pytest.raises(ValueError): MemoryProposal.bind(j,token(p,j,f,s),request(p,f,'weights',q=query(known=1)),s,retained=f.fence,clock=lambda:6)
    with pytest.raises(ValueError): MemoryProposal.bind(j,token(p,j,f,s),request(p,f,'weights'),Search('k','different'),retained=f.fence,clock=lambda:6)


def test_parallel_replay_and_no_raw_memory_in_checkpoint(tmp_path):
    p,j,f,s,clock=fixture(tmp_path); a=bind(p,j,f,s,clock)
    whole=asyncio.run(run(cfg(2),a))
    asyncio.run(run(cfg(1),a,checkpoint=store(tmp_path,'parallel.db')))
    resumed=asyncio.run(run(cfg(2),bind(p,j,f,s,clock),checkpoint=store(tmp_path,'parallel.db'),resume=True,evaluation_processes=2))
    assert whole==resumed
    raw=(tmp_path/'parallel.db').read_bytes()
    assert b'scheduler ratio 2000 10 2000' not in raw and b'__import__' not in raw


def test_rotation_and_runtime_change_fail_closed(tmp_path):
    from test_ontos_otce import V,pub
    p,j,f,s,clock=fixture(tmp_path); a=bind(p,j,f,s,clock)
    with pytest.raises(IntegrityError): asyncio.run(run(cfg(1),replace(a,runtime='f'*64)))
    f=j.append(f.fence,command(p,f,'rotate',{'epoch':2,'reader':pub(V).hex()})); assert f.status=='COMMITTED'
    with pytest.raises(IntegrityError): asyncio.run(run(cfg(1),a))
    b=MemoryProposal.bind(j,token(p,j,f,s,key=V,epoch=2),request(p,f,'weights',key=V,epoch=2),s,retained=f.fence,clock=lambda:6)
    assert a.contract()!=b.contract()


def test_r1_zero_weight_expiry_changes_provenance(tmp_path):
    p,j,f,s,clock=fixture(tmp_path)
    f=put(p,j,f,dict(node('z',parents=('a',),causal=1,kind='R1',expires=10),payload={'x':[0,0],'y':0}))
    a=bind(p,j,f,s,clock); clock[0]=10
    b=bind(p,j,f,s,clock)
    assert a.pool==b.pool and a.contract()!=b.contract()
    with pytest.raises(IntegrityError): asyncio.run(run(cfg(1),a))


def test_expired_token_rejected_but_fresh_same_view_resumes(tmp_path):
    from omega_x_evolution.ontos_otce import read_bytes
    from test_ontos_otce import U
    p,j,f,s,clock=fixture(tmp_path); a=bind(p,j,f,s,clock)
    asyncio.run(run(cfg(1),a,checkpoint=store(tmp_path,'renew.db')))
    clock[0]=20
    with pytest.raises(IntegrityError): asyncio.run(run(cfg(2),a,checkpoint=store(tmp_path,'renew.db'),resume=True))
    def renew(r):
        r=replace(r,issued=20,expires=30,signature=b'\0'*64)
        return replace(r,signature=U.sign(read_bytes(p,r)))
    b=MemoryProposal.bind(j,renew(a.retrieval),renew(a.weights),s,retained=f.fence,clock=lambda:20)
    assert a.contract()==b.contract()
    assert asyncio.run(run(cfg(2),b,checkpoint=store(tmp_path,'renew.db'),resume=True))==asyncio.run(run(cfg(2),b))


def test_wall_clock_gate_disallowed_for_deterministic_checkpoint(tmp_path):
    from omega_x_evolution.performance import Policy
    p,j,f,s,clock=fixture(tmp_path); a=bind(p,j,f,s,clock)
    with pytest.raises(ValueError,match='wall-clock'):
        asyncio.run(run(cfg(1),a,checkpoint=store(tmp_path,'run.db'),performance_policy=Policy()))
    assert not (tmp_path/'run.db').exists()


def test_final_guard_without_checkpoint(tmp_path,monkeypatch):
    import omega_x_evolution.engine as engine
    p,j,f,s,clock=fixture(tmp_path); a=bind(p,j,f,s,clock)
    original=engine.Cascade.heldout
    def expire(self,code):
        clock[0]=20
        return original(self,code)
    monkeypatch.setattr(engine.Cascade,'heldout',expire)
    with pytest.raises(IntegrityError): asyncio.run(run(cfg(1),a))
