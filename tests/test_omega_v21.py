import asyncio
import math
from dataclasses import replace
import pytest
from omega_x_evolution import performance as perf
from omega_x_evolution.engine import Config, Cascade, run, BASELINE
from omega_x_evolution.checkpoint import CheckpointStore, CheckpointError


def profile(p50=100.,p95=120.,p99=150.):
    return perf.Latency(p50,p95,p99,192)


def pair(ratio=1.,tail=None,correctness=.5,baseline=.5):
    return perf.Comparison('parent','id',baseline,correctness,
        tuple(profile() for _ in range(3)),
        tuple(profile(100*ratio,120*(tail or ratio),150*(tail or ratio)) for _ in range(3)))

@pytest.mark.parametrize('ratio,tail,correctness,allowed',[(1.049,None,.5,True),(1.05,None,.5,True),(1.06,None,.5,False),(1.,1.2,.5,False),(1.1,None,.55,True),(1.1,None,.519,False),(1.3,None,.99,False)])
def test_policy_relative_threshold_and_correctness(ratio,tail,correctness,allowed):
    assert perf.decide(pair(ratio,tail,correctness),perf.Policy()).accepted is allowed


def test_noise_and_validation():
    p=pair(1.)
    p=replace(p,candidate=(profile(300,400,500),profile(),profile()))
    assert perf.decide(p,perf.Policy()).accepted
    with pytest.raises(ValueError): perf.Latency(0,1,2,192)
    with pytest.raises(ValueError): perf.Latency(1,2,math.nan,192)
    with pytest.raises(ValueError): perf.Policy(threshold=float('nan'))
    with pytest.raises(ValueError): perf.Latency(3,2,1,192)


def test_real_paired_profile():
    r=perf.measure(BASELINE,'-(x+y+abs(x-y))',Cascade(7).grid)
    assert len(r[0])==len(r[1])==3
    assert all(x.samples==192 and 0<x.p50_ns<=x.p95_ns<=x.p99_ns for x in (*r[0],*r[1]))


def test_stage3_gate_rejects_before_archive(tmp_path,monkeypatch):
    monkeypatch.setattr(perf,'measure',lambda *a: (tuple(profile() for _ in range(3)),tuple(profile(300,360,450) for _ in range(3))))
    async def proposal(model,prompt,seed):
        import json
        p=json.loads(prompt)['parent']
        return f'<<<<<<< SEARCH\n{p}\n=======\n-(x+y+1)\n>>>>>>> REPLACE'
    report=asyncio.run(run(Config(generations=1,islands=1,workers=1),proposal,performance_policy=perf.Policy()))
    assert report['champion']==BASELINE and report['rejections']==1
    assert report['performance_regression']['rejected']==1
    r=report['performance_regression']['records'][0]
    assert not r['accepted'] and r['comparisons'][0]['decision']['reason']=='hard latency cap'
    assert not report['sft']


def test_checkpoint_history_and_policy_binding(tmp_path,monkeypatch):
    monkeypatch.setattr(perf,'measure',lambda *a: (tuple(profile() for _ in range(3)),tuple(profile() for _ in range(3))))
    cfg=Config(seed=5,generations=2,islands=2,workers=2)
    path=tmp_path/'state.db'; ck=CheckpointStore(path,b'k'*32)
    first=asyncio.run(run(replace(cfg,generations=1),checkpoint=ck,performance_policy=perf.Policy()))
    r=asyncio.run(run(cfg,checkpoint=ck,resume=True,performance_policy=perf.Policy()))
    old=first['performance_regression']['records']; assert old and r['performance_regression']['records'][:len(old)]==old
    assert r==asyncio.run(run(cfg,checkpoint=ck,resume=True,performance_policy=perf.Policy()))
    with pytest.raises(CheckpointError): asyncio.run(run(cfg,checkpoint=ck,resume=True))
    with pytest.raises(CheckpointError): asyncio.run(run(cfg,checkpoint=ck,resume=True,performance_policy=perf.Policy(threshold=.06)))


def test_invalid_ast_never_profiled(monkeypatch):
    def bad(*args): pytest.fail('invalid candidate reached timing')
    monkeypatch.setattr(perf,'measure',bad)
    async def proposal(model,prompt,seed): return f'<<<<<<< SEARCH\n{BASELINE}\n=======\n__import__("os")\n>>>>>>> REPLACE'
    r=asyncio.run(run(Config(generations=1,islands=1,workers=1),proposal,performance_policy=perf.Policy()))
    assert r['performance_regression']['records']==[] and r['rejections']==1


def test_cell_champion_and_parent_references(monkeypatch):
    from omega_x_evolution.engine import Archive, Artifact, Genome
    archive=Archive(1);g=Genome();grid=Cascade(1).grid
    parent=Artifact('parent',None,0,0,BASELINE,g,(.4,.9,.9,1.))
    elite=Artifact('elite',parent.id,0,1,'-(x+y+abs(x-y))',g,(.9,.8,.8,1.))
    archive.add(parent);archive.add(elite)
    refs=[]
    def measured(baseline,candidate,grid):
        refs.append(baseline)
        return tuple(profile() for _ in range(3)), tuple(profile() for _ in range(3))
    monkeypatch.setattr(perf,'measure',measured)
    r=perf.check_candidate('new','-(x+y+abs(y-x))',.9,.8,parent,archive,grid,perf.Policy())
    assert r['accepted'] and refs==[parent.code,elite.code]
    assert [c['role'] for c in r['comparisons']]==['parent','cell']
    refs.clear()
    r=perf.check_candidate('new','-(x+y+(x-y)*(x-y)+1)',.9,.8,parent,archive,grid,perf.Policy())
    assert r['comparisons'][1]['role']=='champion' and refs==[parent.code,elite.code]


def test_failed_profiler_rejects_and_json_roundtrip(monkeypatch):
    from omega_x_evolution.engine import Archive,Artifact,Genome
    import json
    a=Archive(1); parent=Artifact('p',None,0,0,BASELINE,Genome(),(.4,.9,.9,1.));a.add(parent)
    elite=Artifact('e','p',0,1,'-(x+y+abs(x-y))',Genome(),(.9,.8,.8,1.));a.add(elite)
    def bad(baseline,*args):
        if baseline==elite.code: raise ValueError('low clock resolution')
        return tuple(profile() for _ in range(3)),tuple(profile() for _ in range(3))
    monkeypatch.setattr(perf,'measure',bad)
    r=perf.check_candidate('new','-(x+y+abs(y-x))',.9,.8,parent,a,Cascade(1).grid,perf.Policy())
    assert not r['accepted'] and 'profiling failed' in r['error']
    assert r==json.loads(json.dumps(r))


def test_gate_on_local_process_pool(monkeypatch):
    monkeypatch.setattr(perf,'measure',lambda *a: (tuple(profile() for _ in range(3)),tuple(profile(300,360,450) for _ in range(3))))
    cfg=Config(seed=5,generations=2,islands=1,workers=2)
    r=asyncio.run(run(cfg,evaluation_processes=2,performance_policy=perf.Policy()))
    assert r['performance_regression']['profiled']>0
    assert r['performance_regression']['rejected']==r['performance_regression']['profiled']
    assert r['champion']==BASELINE


def test_profiling_budget_cap():
    with pytest.raises(ValueError,match='profiling attempt cap'):
        asyncio.run(run(Config(generations=100,islands=16,workers=16,budget=2000),performance_policy=perf.Policy()))


def test_remote_verified_workers_cannot_bypass_coordinator_gate(tmp_path,monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from omega_x_evolution.distributed import Queue, serve, work_once, run_remote
    monkeypatch.setattr(perf,'measure',lambda *a: (tuple(profile() for _ in range(3)),tuple(profile(300,360,450) for _ in range(3))))
    queue=Queue(tmp_path/'queue.db'); stop=threading.Event()
    with serve(queue,{'a':'a'*32}) as url, ThreadPoolExecutor(1) as pool:
        def worker():
            while not stop.is_set():
                if not work_once(url,'a','a'*32): stop.wait(.01)
        future=pool.submit(worker)
        try:
            r=asyncio.run(run_remote(Config(seed=5,generations=2,islands=1,workers=2),queue,timeout=10,performance_policy=perf.Policy()))
            assert r['performance_regression']['profiled']>0
            assert r['performance_regression']['rejected']==r['performance_regression']['profiled']
            assert r['champion']==BASELINE
        finally: stop.set()
        future.result(timeout=3)


def test_correctness_exception_promotes_candidate(monkeypatch):
    monkeypatch.setattr(perf,'measure',lambda *a: (tuple(profile() for _ in range(3)),tuple(profile(110,132,165) for _ in range(3))))
    async def proposal(model,prompt,seed):
        return f'<<<<<<< SEARCH\n{BASELINE}\n=======\n-(x+y+2)\n>>>>>>> REPLACE'
    r=asyncio.run(run(Config(seed=5,generations=1,islands=1,workers=1),proposal,performance_policy=perf.Policy()))
    record=r['performance_regression']['records'][0]
    assert record['accepted'] and record['comparisons'][0]['decision']['reason']=='correctness tradeoff'
    assert r['rejections']==0 and r['champion']=='-(x+y+2)'
    assert r['sft']


def test_second_baseline_can_veto(monkeypatch):
    from omega_x_evolution.engine import Archive, Artifact, Genome
    a=Archive(1); p=Artifact('p',None,0,0,BASELINE,Genome(),(.4,.9,.9,1.)); a.add(p)
    e=Artifact('e','p',0,1,'-(x+y+abs(x-y))',Genome(),(.9,.8,.8,1.)); a.add(e)
    def measured(baseline,*args):
        v=profile() if baseline==p.code else profile(150,180,225)
        return tuple(profile() for _ in range(3)),tuple(v for _ in range(3))
    monkeypatch.setattr(perf,'measure',measured)
    r=perf.check_candidate('new','-(x+y+abs(y-x))',.91,.8,p,a,Cascade(1).grid,perf.Policy())
    assert not r['accepted'] and r['comparisons'][0]['decision']['accepted'] and not r['comparisons'][1]['decision']['accepted']
