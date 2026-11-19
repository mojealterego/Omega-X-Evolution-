import asyncio
import copy
import random
import numpy as np
import pytest
from omega_x_evolution.annealed import TensorTrain, policy, propose
from omega_x_evolution.holographic import Memory, trajectory
from omega_x_evolution.safety_synthesis import prove, verify, modal_invariant
from omega_x_evolution.cluster import ClusterConfig, IslandActor, initial_state, verify_transition, ClusterError, Store, LocalBackend, run_cluster
from omega_x_evolution.topology import TopologyPolicy


def test_tt_exact_and_rank_compression():
    a=np.arange(4.)+1; b=np.arange(4.)+2; c=np.arange(6.)+3
    tensor=np.einsum('i,j,k->ijk',a,b,c)
    tt=TensorTrain.fit(tensor,2)
    assert tt.parameters<tensor.size
    assert all(tt.at(i,j,k)==pytest.approx(tensor[i,j,k]) for i,j,k in np.ndindex(tensor.shape))


def test_policy_feedback_and_reproducible_sampling():
    rows=[trajectory('t'+str(i),0,'p','-(x+y)','-(x+y+2)',4,True,0.8,0.5,3) for i in range(12)]
    p=policy('-(x+y)',rows,temperature=.15)
    assert sum(p)==pytest.approx(1) and min(p)>0 and p[4]>p[0]
    assert propose('-(x+y)',4,123)==propose('-(x+y)',4,123)


def test_memory_context_and_negative_evidence():
    good=trajectory('a',0,'p','-(x+y)','-(x+y+2)',4,True,.8,.5,3)
    bad=trajectory('b',1,'q','abs(x-y)','x/y',0,False,0.,.5,1)
    mem=Memory([good,bad]); r=mem.retrieve('-(x+y)',2)
    assert r[0]['record']==good and sum(x['weight'] for x in r)==pytest.approx(1)
    assert mem.retrieve('-(x+y)',2)==Memory([good,bad]).retrieve('-(x+y)',2)
    with pytest.raises(ValueError): Memory([good,{**bad,'reward':100}])


@pytest.mark.parametrize('code',['-(x+y)','-(x+y+(x-y)*(x-y)/(.01+x*y)+2)','min(abs(x-y),1)'])
def test_safety_certificate(code):
    p=prove(code); assert p['proved'] and verify(code,p)
    assert p['obligations']>0
    assert not verify(code,{**p,'digest':'0'*64})

@pytest.mark.parametrize('code',['1/(x-.123456)','1e6*1e6*1e6','__import__("os")','1/(x-x)'])
def test_unsafe_or_unknown_rejected(code):
    assert not prove(code)['proved']


def test_modal_model():
    assert modal_invariant()
    assert not modal_invariant(bypass=True)


def test_integrated_cluster_restart_and_tamper(tmp_path):
    cfg=ClusterConfig(islands=2,rounds=2,batch=4,budget=16,parallelism=2, migration_interval=1,topology=TopologyPolicy(),annealed=True,holographic=True,formal_safety=True)
    s=initial_state(cfg,0);n=IslandActor(cfg,0).step(s,None,s['elite'])
    verify_transition(cfg,s,n,None,s['elite'],False)
    assert len(n['trajectories'])==4 and n['formal_records']
    forged=copy.deepcopy(n);forged['trajectories'][0]['reward']=99
    with pytest.raises(ClusterError): verify_transition(cfg,s,forged,None,s['elite'],False)
    forged=copy.deepcopy(n);forged['formal_records']=[]
    with pytest.raises(ClusterError): verify_transition(cfg,s,forged,None,s['elite'],False)
    db=Store(tmp_path/'run.db',b'z'*32,cfg).initialize()
    with LocalBackend(cfg,processes=True) as b:
        assert not asyncio.run(run_cluster(db,b,stop_after=2))['complete']
    with LocalBackend(cfg,processes=True) as b:
        r=asyncio.run(run_cluster(db,b)); assert r['complete'] and r['attempts']==16
        assert r['trajectory_count']==16 and r['foreign_trajectories']>0 and r['formal_checks']>0
        assert r==asyncio.run(run_cluster(db,b))


def test_memory_keys_compressed_and_stable_subprocess():
    import subprocess,sys
    from omega_x_evolution.holographic import encode
    key=encode('-(x+y)')
    assert type(key) is bytes and len(key)==128
    result=subprocess.check_output([sys.executable,'-c','from omega_x_evolution.holographic import encode; print(encode("-(x+y)").hex())'],text=True).strip()
    assert result==key.hex()


def test_annealed_operator_provenance():
    from omega_x_evolution.engine import apply_patch
    parent='-(x+y)';child=apply_patch(parent,propose(parent,4,123))
    r=trajectory('a',0,'p',parent,child,4,True,.8,.5,3,123)
    assert r['proposal_seed']==123
    with pytest.raises(ValueError): Memory([{**r,'proposal_seed':124}])


def test_formal_failure_before_empirical(monkeypatch):
    from omega_x_evolution import cluster
    async def unsafe(model,prompt,seed):
        import json
        parent=json.loads(prompt)['parent']
        return f'<<<<<<< SEARCH\n{parent}\n=======\n1/(x-.123456)\n>>>>>>> REPLACE'
    monkeypatch.setattr(cluster,'simulated_proposal',unsafe)
    cfg=ClusterConfig(islands=1,rounds=1,batch=1,budget=1,formal_safety=True)
    s=initial_state(cfg,0)
    n=IslandActor(cfg,0).step(s,None,s['elite'])
    assert n['rejections']==1 and len(n['lineage'])==1 and not n['formal_records'][0]['certificate']['proved']
    verify_transition(cfg,s,n,None,s['elite'],False)


def test_regression_gate_still_mandatory_with_proof(monkeypatch):
    from omega_x_evolution import performance
    from omega_x_evolution.performance import Policy, Latency
    a=Latency(100,120,150,192); b=Latency(500,600,750,192)
    monkeypatch.setattr(performance,'measure',lambda *x:((a,)*3,(b,)*3))
    cfg=ClusterConfig(islands=1,rounds=1,batch=4,budget=4,annealed=True,holographic=True,formal_safety=True,policy=Policy())
    s=initial_state(cfg,0); n=IslandActor(cfg,0).step(s,None,s['elite'])
    assert n['rejections']==4 and len(n['lineage'])==1
    assert n['performance_records'] and n['formal_records']
    verify_transition(cfg,s,n,None,s['elite'],False)


def test_foreign_packet_tamper():
    cfg=ClusterConfig(islands=2,rounds=2,batch=2,budget=8,migration_interval=1,holographic=True)
    s=initial_state(cfg,0); t=initial_state(cfg,1)
    n=IslandActor(cfg,0).step(s,None,s['elite'])
    verify_transition(cfg,s,n,None,s['elite'],False)
    forged=copy.deepcopy(n);forged['outgoing']['trajectories'][0]['reward']=99
    with pytest.raises(ClusterError):verify_transition(cfg,s,forged,None,s['elite'],False)
    m=IslandActor(cfg,1).step(t,n['outgoing'],n['elite'])
    verify_transition(cfg,t,m,n['outgoing'],n['elite'],False)
    assert m['foreign_trajectories']==n['outgoing']['trajectories']
    forged=copy.deepcopy(m);forged['foreign_trajectories']=[]
    with pytest.raises(ClusterError):verify_transition(cfg,t,forged,n['outgoing'],n['elite'],False)
