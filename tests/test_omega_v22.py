import asyncio
from dataclasses import replace
import json
import sqlite3
import pytest
from omega_x_evolution.cluster import ClusterConfig, IslandActor, Store, LocalBackend, run_cluster, initial_state, contract, ClusterError
from omega_x_evolution.performance import Policy, Latency


def test_config_limits():
    assert ClusterConfig(islands=512, rounds=1, batch=1, budget=512).islands == 512
    for kwargs in ({'islands':513}, {'batch':0}, {'parallelism':0}, {'islands':8,'budget':7}, {'seed':True}):
        with pytest.raises(ValueError): ClusterConfig(**kwargs)


def test_actor_retry_and_lineage():
    cfg=ClusterConfig(islands=2,rounds=2,batch=2,budget=12)
    state=initial_state(cfg,0)
    actor=IslandActor(cfg,0)
    a=actor.step(state,None,state['lineage'][0],False)
    b=actor.step(state,None,state['lineage'][0],False)
    assert a==b and a['round']==1 and a['attempts']==2
    assert all(x['id'].startswith('i0-') for x in a['lineage'])
    assert IslandActor(cfg,0).step(state,None,state['lineage'][0],False)==a


def test_store_authentication_and_cas(tmp_path):
    cfg=ClusterConfig(islands=2,rounds=2,batch=1,budget=4)
    path=tmp_path/'c.db'; store=Store(path,b'x'*32,cfg);store.initialize()
    rev,s=store.read(0); assert rev==0
    result=IslandActor(cfg,0).step(s,None,s['lineage'][0],False)
    store.commit(0,rev,result)
    with pytest.raises(ClusterError): store.commit(0,rev,result)
    with pytest.raises(ClusterError): Store(path,b'y'*32,cfg).open()
    with sqlite3.connect(path) as db: db.execute("UPDATE islands SET body='{}' WHERE id=0")
    with pytest.raises(ClusterError): store.read(0)


def test_async_migration_recovery(tmp_path):
    cfg=ClusterConfig(islands=8,rounds=3,batch=2,budget=48,parallelism=3,migration_interval=1)
    path=tmp_path/'c.db';store=Store(path,b'k'*32,cfg);store.initialize()
    backend=LocalBackend(cfg)
    r=asyncio.run(run_cluster(store,backend,stop_after=5))
    assert r['complete'] is False and r['commits']==5
    backend.close()
    with LocalBackend(cfg) as b:
        r=asyncio.run(run_cluster(Store(path,b'k'*32,cfg).open(),b))
        assert r['complete'] and r['attempts']==48 and r['migrations_seen']>=8
        assert r['occupied_cells']>=8 and r['champion_score']>=r['baseline_score']
        assert r==asyncio.run(run_cluster(Store(path,b'k'*32,cfg).open(),b))
    assert all(s['done'] for _,s in (store.read(i) for i in range(8)))


def test_real_process_transport(tmp_path):
    cfg=ClusterConfig(islands=3,rounds=2,batch=2,budget=12,parallelism=2)
    store=Store(tmp_path/'p.db',b'k'*32,cfg);store.initialize()
    with LocalBackend(cfg,processes=True) as b:
        r=asyncio.run(run_cluster(store,b))
        assert r['complete'] and r['attempts']==12 and r['migrations_seen']>=3
        assert b.worker_pids and all(p!=__import__('os').getpid() for p in b.worker_pids)


def test_gate_including_migrations(monkeypatch):
    from omega_x_evolution import performance
    a=Latency(100,120,150,192); b=Latency(300,360,450,192)
    monkeypatch.setattr(performance,'measure',lambda *x: ((a,)*3,(b,)*3))
    cfg=ClusterConfig(islands=2,rounds=1,batch=4,budget=8,policy=Policy())
    s=initial_state(cfg,0);other=initial_state(cfg,1)
    migrant={'source':1,'revision':1,'artifact':other['lineage'][0]}
    r=IslandActor(cfg,0).step(s,migrant,s['lineage'][0],False)
    assert r['migrations_seen']==1 and r['migrations_accepted']==0
    assert len(r['lineage'])==1 and r['rejections']==4
    assert r['performance_records'] and all(not x['accepted'] for x in r['performance_records'])


def test_malformed_migrant_and_wrong_contract():
    cfg=ClusterConfig(islands=3,rounds=1,budget=3,batch=1)
    s=initial_state(cfg,0)
    with pytest.raises(ValueError): IslandActor(cfg,0).step(s,{'source':1,'revision':1,'artifact':s['lineage'][0]},s['lineage'][0],False)
    with pytest.raises(ValueError): IslandActor(cfg,1).step(s,None,s['lineage'][0],False)


def test_forged_worker_metrics_and_missing_gate(monkeypatch):
    from omega_x_evolution.cluster import verify_transition
    from omega_x_evolution import performance
    p=Latency(100,120,150,192)
    monkeypatch.setattr(performance,'measure',lambda *x: ((p,)*3,(p,)*3))
    cfg=ClusterConfig(islands=1,rounds=1,batch=4,budget=4,policy=Policy())
    s=initial_state(cfg,0);champ=s['elite'];n=IslandActor(cfg,0).step(s,None,champ,False)
    assert len(n['lineage'])>1
    verify_transition(cfg,s,n,None,champ,False)
    forged=json.loads(json.dumps(n));forged['lineage'][-1]['metrics'][0]=1.
    with pytest.raises(ClusterError):verify_transition(cfg,s,forged,None,champ,False)
    forged=json.loads(json.dumps(n));forged['performance_records']=[]
    with pytest.raises(ClusterError):verify_transition(cfg,s,forged,None,champ,False)


def test_lost_actor_response_recovery(tmp_path):
    cfg=ClusterConfig(islands=3,rounds=2,batch=2,budget=12,parallelism=1,migration_interval=1)
    path=tmp_path/'failure.db';store=Store(path,b'k'*32,cfg).initialize()
    with LocalBackend(cfg) as backend:
        orig=backend.call; calls=0
        async def fail(i,*args):
            nonlocal calls
            result=await orig(i,*args);calls+=1
            if calls==2:raise RuntimeError('injected lost actor response')
            return result
        backend.call=fail
        with pytest.raises(RuntimeError,match='lost actor'):asyncio.run(run_cluster(store,backend))
    assert sum(store.read(i)[0] for i in range(3))==1
    with LocalBackend(cfg) as backend:
        report=asyncio.run(run_cluster(Store(path,b'k'*32,cfg).open(),backend))
    assert report['complete'] and report['commits']==9 and report['attempts']==12


def test_async_no_global_round_barrier(tmp_path):
    cfg=ClusterConfig(islands=3,rounds=3,batch=1,budget=9,parallelism=2,migration_interval=1)
    store=Store(tmp_path/'async.db',b'k'*32,cfg).initialize()
    async def scenario():
        with LocalBackend(cfg) as backend:
            original=backend.call;started=asyncio.Event();release=asyncio.Event();saw=[]
            async def delay(i,old,*args):
                if i==0 and old['round']==0:
                    started.set();await asyncio.wait_for(release.wait(),5)
                else:
                    await started.wait()
                    if old['round']==1:saw.append(i);release.set()
                return await original(i,old,*args)
            backend.call=delay
            r=await run_cluster(store,backend)
            assert r['complete'] and saw
    asyncio.run(scenario())


def test_large_logical_archipelago(tmp_path):
    cfg=ClusterConfig(islands=256,rounds=1,batch=1,budget=256,parallelism=16,migration_interval=1)
    store=Store(tmp_path/'scale.db',b'k'*32,cfg).initialize()
    with LocalBackend(cfg) as backend:
        r=asyncio.run(run_cluster(store,backend))
    assert r['complete'] and r['commits']==512 and r['attempts']==256
    assert r['migrations_seen']==256 and r['occupied_cells']>=256


def test_ray_unavailable_is_not_implicit_simulation(monkeypatch):
    import sys
    from omega_x_evolution.cluster import RayBackend
    monkeypatch.setitem(sys.modules,'ray',None)
    with pytest.raises(ClusterError,match='ray extra'):RayBackend(ClusterConfig(),address='local')


def test_actual_worker_process_death(tmp_path):
    import os
    from concurrent.futures.process import BrokenProcessPool
    cfg=ClusterConfig(islands=2,rounds=2,batch=1,budget=4,parallelism=1)
    path=tmp_path/'worker.db'; store=Store(path,b'k'*32,cfg).initialize()
    with LocalBackend(cfg,processes=True) as backend:
        assert asyncio.run(run_cluster(store,backend,stop_after=1))['commits']==1
        with pytest.raises(BrokenProcessPool):backend.pool.submit(os._exit,17).result(timeout=10)
        with pytest.raises(BrokenProcessPool):asyncio.run(run_cluster(store,backend))
    assert sum(store.read(i)[0] for i in range(2))==1
    with LocalBackend(cfg,processes=True) as backend:
        r=asyncio.run(run_cluster(Store(path,b'k'*32,cfg).open(),backend))
    assert r['complete'] and r['attempts']==4 and r['commits']==6


def test_mandatory_challenge_cannot_be_removed():
    from omega_x_evolution.cluster import verify_transition
    cfg=ClusterConfig(islands=1,rounds=1,batch=1,budget=1)
    state=initial_state(cfg,0);r=IslandActor(cfg,0).step(state,None,state['elite'],False)
    r['challenge']=[p for p in r['challenge'] if p[0]!=[0.,0.]]
    with pytest.raises(ClusterError):verify_transition(cfg,state,r,None,state['elite'],False)
