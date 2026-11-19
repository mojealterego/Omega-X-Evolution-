import copy
import threading
import time
import pytest
from omega_x_evolution.axioms import discover, verify, classify, structures
from omega_x_evolution.polyglot import Program
from omega_x_evolution.plasticity import Plasticity, Policy, fixture, fit_adapter, validate_record
from omega_x_evolution.infrastructure import Orchestrator, Limits, Job


def test_axioms_discovery_and_replay():
    r=discover(seed=7,budget=256)
    assert r['proved'] and r['refuted'] and r['proposals']<=256
    assert verify(r)
    bad=copy.deepcopy(r);bad['proved'][0]['proof']['left'][-1]=[[0,0,12345]]
    assert not verify(bad)


def test_counterexample_and_unknown():
    x=Program(('x',)); y=Program(('y',))
    assert classify(x,y)['status']=='refuted'
    assert classify(Program(('xor',('x',),('x',))),Program(('lit',0)))['status']=='unknown'


def test_finite_algebra_exhaustive():
    r=structures(2)
    assert r['examined']==16 and r['groups']==2
    assert all(s['associative'] and s['identity'] is not None for s in r['models'] if s['group'])


def test_adapter_frozen_and_real_training():
    p=Policy(seed=42,rank=2,steps=80)
    t,v,r=fixture(42)
    result=fit_adapter(p,t,v,r)
    assert result['train_after']<result['train_before']
    assert result['base_sha256']==p.base_digest
    assert result['trainable_parameters']==24
    assert result['selected_validation']<=result['validation_before']


def test_trajectory_tampering_and_leakage():
    p=Policy();t,v,r=fixture(42);bad=copy.deepcopy(t[0]);bad['reward']+=.1
    with pytest.raises(ValueError):validate_record(bad)
    with pytest.raises(ValueError):fit_adapter(p,t,t,r)


def test_durable_plasticity_budget_rollback(tmp_path):
    p=Policy(steps=30,max_updates=2);t,v,r=fixture(42)
    s=Plasticity(tmp_path/'p.db',b'k'*32,p,create=True)
    with pytest.raises(PermissionError):s.update(t,v,r)
    a=s.update(t,v,r,authorized=True,request_id='one')
    assert s.update(t,v,r,authorized=True,request_id='one')==a
    s=Plasticity(tmp_path/'p.db',b'k'*32,p)
    assert s.inspect()['used_steps']==30
    s.update(t,v,r,authorized=True,request_id='two')
    with pytest.raises(ValueError):s.update(t,v,r,authorized=True,request_id='three')
    s.rollback(authorized=True)
    assert s.inspect()['used_steps']==60 and s.inspect()['active']==s.inspect()['initial']


def test_orchestration_real_execution_and_idempotent(tmp_path):
    p=Limits(total_cpu_seconds=10,max_jobs=2,max_wall_seconds=10)
    s=Orchestrator(tmp_path/'i.db',b'z'*32,p,create=True)
    j=Job('a','axioms',3,5,seed=7,budget=128)
    r=s.run(j,authorized=True)
    assert r['status']=='succeeded' and r['result']['proved']
    assert s.run(j,authorized=True)==r
    assert s.inspect()['reserved_cpu_seconds']==3
    with pytest.raises(ValueError):s.run(Job('a','axioms',3,5,seed=8),authorized=True)


def test_orchestration_denies_and_stop(tmp_path):
    s=Orchestrator(tmp_path/'i.db',b'z'*32,Limits(total_cpu_seconds=2,max_jobs=1),create=True)
    with pytest.raises(PermissionError):s.run(Job('x','axioms',1,2))
    with pytest.raises(ValueError):Job('x','cloud',1,2)
    with pytest.raises(ValueError):s.run(Job('x','axioms',3,5),authorized=True)
    s.stop(authorized=True)
    with pytest.raises(ValueError):s.run(Job('x','axioms',1,2),authorized=True)


def test_discovery_graph_idempotent_and_smt(tmp_path):
    from omega_x_evolution.axioms import publish
    from omega_x_evolution.graph_memory import GraphMemory
    m=GraphMemory(tmp_path/'axioms.db',b'g'*32,'algebra')
    r=discover(seed=7,budget=64)
    ids=publish(m,r)
    assert ids and publish(m,r)==ids
    assert all(m.snapshot()[0][i]['kind']=='evidence' for i in ids)
    a=Program(('xor',('x',),('x',)));b=Program(('lit',0))
    assert classify(a,b,smt=True)['status']=='smt-proved'


def test_cluster_trajectory_import(tmp_path):
    import asyncio
    from omega_x_evolution.cluster import ClusterConfig, Store, LocalBackend, run_cluster
    from omega_x_evolution.plasticity import collect_store
    cfg=ClusterConfig(seed=42,islands=2,rounds=2,batch=4,budget=16,parallelism=2,annealed=True,formal_safety=True)
    store=Store(tmp_path/'cluster.db',b'g'*32,cfg).initialize()
    with LocalBackend(cfg,processes=True) as backend:assert asyncio.run(run_cluster(store,backend))['complete']
    before=store.read(0)
    rows,info=collect_store(store,(0,1))
    assert rows and info['accepted']==len(rows) and all(validate_record(r)==r for r in rows)
    assert store.read(0)==before


def test_plasticity_reject_and_no_base_mutation():
    from omega_x_evolution.plasticity import choose, evaluate_adapter
    from omega_x_evolution.engine import BASELINE
    p=Policy(steps=400);t,v,r,test=fixture(42,groups=4);base=p.base_digest
    x=fit_adapter(p,t,v,r)
    assert p.base_digest==base and p.initial()['b']==[[0.]*6]*2
    assert evaluate_adapter(p,x['adapter'],test)['rows']==36
    assert validate_record(choose(p,x['adapter'],BASELINE,27))['proposal_seed'] is not None
    # Reversing the reward improvement criterion is not permitted: a validation regression keeps active.
    assert x['promoted'] or x['adapter']==p.initial()


def test_plasticity_interruption_consumes_reservation(tmp_path,monkeypatch):
    from omega_x_evolution import plasticity
    p=Policy(steps=5,max_updates=2);t,v,r=fixture();s=Plasticity(tmp_path/'p.db',b'k'*32,p,create=True)
    original=plasticity.fit_adapter
    def fail(*args,**kwargs):raise RuntimeError('injected crash after reservation')
    monkeypatch.setattr(plasticity,'fit_adapter',fail)
    with pytest.raises(RuntimeError):s.update(t,v,r,authorized=True,request_id='a')
    monkeypatch.setattr(plasticity,'fit_adapter',original)
    s=Plasticity(s.path,b'k'*32,p)
    with pytest.raises(ValueError):s.update(t,v,r,authorized=True,request_id='a')
    assert s.inspect()['used_steps']==5 and s.inspect()['updates']['a']['status']=='interrupted'
    s.update(t,v,r,authorized=True,request_id='b')
    assert s.inspect()['used_steps']==10


def test_orchestration_parallel_real_work_and_atomic_budget(tmp_path):
    limits=Limits(total_cpu_seconds=9,max_jobs=3,max_parallel=2)
    s=Orchestrator(tmp_path/'i.db',b'z'*32,limits,create=True)
    rows=s.run_batch((Job('x','axioms',3,10,budget=64),Job('y','scheduler',3,10,budget=32),Job('z','plasticity',3,10,budget=80)),authorized=True)
    assert [r['status'] for r in rows]==['succeeded']*3
    assert len({r['pid'] for r in rows})==3 and s.inspect()['last_peak_parallel']==2
    assert s.inspect()['reserved_cpu_seconds']==9
    with pytest.raises(ValueError):s.run(Job('more','axioms',1,2),authorized=True)


def test_orchestration_stop_running(tmp_path):
    import psutil
    limits=Limits(total_cpu_seconds=20,max_jobs=4,max_parallel=1)
    s=Orchestrator(tmp_path/'i.db',b'z'*32,limits,create=True)
    out=[];errors=[]
    def run():
        try:out.extend(s.run_batch(tuple(Job(str(i),'axioms',5,10,budget=1024) for i in range(4)),authorized=True))
        except BaseException as exc:errors.append(exc)
    thread=threading.Thread(target=run);thread.start()
    deadline=time.monotonic()+5
    while time.monotonic()<deadline and not psutil.Process().children():time.sleep(.005)
    assert psutil.Process().children()
    Orchestrator(s.path,b'z'*32,limits).stop(authorized=True)
    thread.join(10)
    assert not thread.is_alive() and not errors and len(out)==4
    assert any(r['status']=='cancelled' for r in out)
    assert all(r['status'] in ('succeeded','cancelled') for r in out)
    assert s.inspect()['reserved_cpu_seconds']==20 and s.inspect()['stopped']


def test_orchestrator_crash_recovery(tmp_path):
    import subprocess,sys,os,psutil
    limits=Limits(total_cpu_seconds=10,max_jobs=2,max_parallel=1)
    db=tmp_path/'i.db';s=Orchestrator(db,b'z'*32,limits,create=True)
    script='from omega_x_evolution.infrastructure import *; import sys; s=Orchestrator(sys.argv[1],b"z"*32,Limits(total_cpu_seconds=10,max_jobs=2,max_parallel=1)); s.run(Job("a","axioms",5,10,budget=1024),authorized=True)'
    proc=subprocess.Popen([sys.executable,'-c',script,str(db)])
    try:
        deadline=time.monotonic()+5;child=None
        while time.monotonic()<deadline and proc.poll() is None:
            children=psutil.Process(proc.pid).children()
            if children:child=children[0];break
            time.sleep(.005)
        assert child is not None
        proc.kill();proc.wait(timeout=5)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline and child.is_running() and child.status()!=psutil.STATUS_ZOMBIE:time.sleep(.01)
        assert not child.is_running() or child.status()==psutil.STATUS_ZOMBIE
        r=s.recover(authorized=True)
        assert r['jobs']['a']['status']=='interrupted' and r['reserved_cpu_seconds']==5
        assert s.run(Job('a','axioms',5,10,budget=1024),authorized=True)['status']=='interrupted'
        assert s.run(Job('b','axioms',5,10,budget=64),authorized=True)['status']=='succeeded'
    finally:
        if proc.poll() is None:proc.kill();proc.wait(timeout=5)
