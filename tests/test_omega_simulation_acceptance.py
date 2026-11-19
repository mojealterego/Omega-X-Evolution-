"""Independent deterministic contracts; never substitute for native provider execution."""
import random
import json
import pytest
from omega_x_evolution import higher_order as hol
from omega_x_evolution.polyglot import Program
from omega_x_evolution.simulation_contracts import check_source, VirtualCluster
from omega_x_evolution.cloud import CloudOrchestrator, Policy, Job, reservation


@pytest.mark.parametrize('backend', ['lean', 'isabelle'])
def test_proof_source_roundtrip_and_solver(backend):
    x,y=Program(('x',)),Program(('y',))
    a=Program(('sub',('add',x.tree,y.tree),y.tree))
    emit=getattr(hol,backend+'_source')
    good=check_source(backend,emit(a,x),a,x);bad=check_source(backend,emit(a,y),a,y)
    assert good['status']=='unsat' and bad['status']=='sat'
    print(json.dumps({'test':'source-roundtrip','valid':good,'counterexample':bad},sort_keys=True))
    # Valid syntax with a different RHS must fail the source/IR binding.
    with pytest.raises(ValueError):check_source(backend,emit(a,y),a,x)
    with pytest.raises(ValueError):check_source(backend,emit(a,x)+'\nsorry',a,x)
    for op in ('add','sub','mul','xor','and','or'):
        p=Program((op,x.tree,('lit',65535)))
        assert check_source(backend,emit(p,p),p,p)['proved']


def test_virtual_cluster_faults_capacity_restart_and_deadline(tmp_path):
    p=Policy('omega-test','registry.example/engine@sha256:'+'a'*64,5000000,1000000,2000000,3000000,api_call_micros=100,max_jobs=4,max_replicas=4)
    provider=VirtualCluster(p.namespace, cpu=2, gpu=1, tpu=0, seed=42)
    o=CloudOrchestrator(tmp_path/'cloud.db',b'a'*32,p,provider,ledger_id='a'*64,create=True)
    j=Job('first','gpu',1,1,10,42,16)
    provider.lose_next_create=True
    with pytest.raises(TimeoutError):o.submit(j,authorized=True)
    o=CloudOrchestrator(o.path,b'a'*32,p,provider,ledger_id='a'*64)
    assert o.reconcile('first',authorized=True)['status']=='active'
    assert provider.used['gpu']==1
    assert o.submit(j,authorized=True)['job']['id']=='first'
    j2=Job('second','gpu',1,1,10,42,16)
    assert o.submit(j2,authorized=True)['status']=='active'
    assert provider.used['gpu']==1  # queued, quota cannot be exceeded
    provider.advance(10)
    for jx in (j,j2):assert o.reconcile(jx.id,authorized=True)['status']=='failed'
    assert provider.used['gpu']==0
    j3=Job('third','cpu',1,0,20,42,16)
    o.submit(j3,authorized=True);provider.advance(1)
    assert provider.used['cpu']==1
    assert not o.stop(authorized=True)['delete_errors']
    assert provider.used=={'cpu':0,'gpu':0,'tpu':0}
    assert o.reconcile('third',authorized=True)['status']=='absent'
    assert o.inspect()['spent_micros']==sum(reservation(p,jx) for jx in (j,j2,j3))
    assert provider.create_count==3
    assert all(0<=v<=provider.capacity[k] for _,_,_,usage in provider.events for k,v in usage)
    assert any(e[1]=='lost-response' for e in provider.events)
    print(json.dumps({'test':'virtual-cluster','seed':42,'events':provider.events,'reserved_micros':o.inspect()['spent_micros']},sort_keys=True))


def test_virtual_cluster_state_replays():
    from omega_x_evolution.cloud import manifest
    p=Policy('omega-test','registry.example/engine@sha256:'+'a'*64,5000000,1000000,2000000,3000000)
    def scenario(seed):
        c=VirtualCluster(p.namespace,cpu=2,gpu=1,tpu=0,seed=seed)
        rng=random.Random(seed)
        for i in range(5):
            c.create(manifest(p,Job(f'job-{i}','cpu',1,0,10,seed,16),'a'*64))
            c.advance(rng.randrange(4))
        c.advance(20)
        return c.events,c.used,c.jobs
    assert scenario(42)==scenario(42)


def test_distributed_gradient_reference_and_optimizer():
    import torch
    from omega_x_evolution.llm_plasticity import tiny_decoder
    from omega_x_evolution.plasticity import fixture
    from omega_x_evolution.simulation_contracts import distributed_step
    old=torch.get_num_threads();torch.set_num_threads(1)
    try:
        train=fixture(42,groups=4)[0][:7]
        reference=tiny_decoder();replicas=[tiny_decoder() for _ in range(3)]
        opt=torch.optim.AdamW(list(reference.params.values()),lr=.01,weight_decay=0.)
        for _ in range(3):
            opt.zero_grad(set_to_none=True);reference._backward(reference._dataset(train))
            torch.nn.utils.clip_grad_norm_(list(reference.params.values()),1.,error_if_nonfinite=True);opt.step()
        report=distributed_step(replicas,train,steps=3,seed=42)
        assert report['samples']==21 and report['steps']==3
        print(json.dumps({'test':'distributed-training','report':report,'frozen_base_sha':reference.base_sha},sort_keys=True))
        for replica in replicas:
            assert replica.base_digest()==reference.base_sha
            for name in reference.params:
                assert torch.allclose(replica.params[name],reference.params[name],rtol=1e-5,atol=2e-6)
        # Missing worker must not result in an update with a silently smaller batch.
        before=replicas[0].snapshot()
        with pytest.raises(ValueError):distributed_step(replicas,train,steps=1,seed=42,unavailable=(1,))
        assert replicas[0].snapshot()==before
        with pytest.raises(RuntimeError,match='collective interrupted'):
            distributed_step(replicas,train,steps=3,seed=43,fail_at_step=1)
        assert all(r.snapshot()==before for r in replicas)
        assert all(p.grad is None for r in replicas for p in r.params.values())
    finally:torch.set_num_threads(old)


def test_virtual_cluster_success_and_uid_preconditions(tmp_path):
    from omega_x_evolution.cloud import manifest
    from omega_x_evolution.cloud_worker import run
    p=Policy('omega-test','registry.example/engine@sha256:'+'a'*64,5000000,1000000,2000000,3000000)
    c=VirtualCluster(p.namespace,cpu=1,gpu=0,tpu=0,seed=42)
    o=CloudOrchestrator(tmp_path/'ok.db',b'a'*32,p,c,ledger_id='b'*64,create=True)
    j=Job('cpu-job','cpu',1,0,20,42,16)
    obj=o.submit(j,authorized=True);name=obj['manifest']['metadata']['name']
    with pytest.raises(ValueError):c.delete(name,'wrong-uid')
    assert c.used['cpu']==1
    # Run the actual fixed workload, not a constant completion response.
    result=run('cpu',42,16,0)
    assert result['backend']=='cpu' and result['seed']==42 and result['result']
    c.advance(1);c.complete(name)
    assert o.reconcile(j.id,authorized=True)['status']=='complete'
    assert c.used['cpu']==0
    assert c.get(name)['metadata']['uid']==obj['uid']
    print(json.dumps({'test':'cpu-workload','seed':42,'events':c.events,'backend':result['backend']},sort_keys=True))
    assert not o.stop(authorized=True)['delete_errors']


@pytest.mark.parametrize('kind', ['gpu','npu'])
def test_virtual_accelerator_real_math_and_memory(kind):
    import torch
    from omega_x_evolution.compute import Device, Router, TorchBackend, ComputeError
    from omega_x_evolution.neural import BASELINE, fit
    from omega_x_evolution.neuro_symbolic import fixture
    from omega_x_evolution.llm_plasticity import memory_admission
    d=fixture('smooth',seed=42);m=fit(BASELINE,d.train,epochs=3,seed=42)
    b=TorchBackend(torch,Device('virtual-'+kind,kind,1024*1024,False),'cpu',torch.float32)
    r=Router([b],memory_cap=1024*1024)
    assert not r.infer(m,d.test,prefer=(kind,)).physical
    assert r.reserved==0
    with pytest.raises(ComputeError):Router([b],memory_cap=1).infer(m,d.test,prefer=(kind,))
    info={'parameter_elements':1_500_000_000,'storage_bytes':3_000_000_000}
    # Simulated resource envelope only: no claim that actual activations fit.
    assert memory_admission(info,device='cuda',available_bytes=16*1024**3)['admitted']
    with pytest.raises(RuntimeError):memory_admission(info,device='cuda',available_bytes=4*1024**3)
