import itertools
import numpy as np
import pytest
from omega_x_evolution.optimization import BinaryProblem, solve, logistics, tensor_subset


def test_qubo_logistics_exact_and_feasibility():
    durations=((2,5),(4,1),(2,3))
    problem=logistics(durations, (4,4))
    result=solve(problem,steps=1024)
    assert result['feasible'] and result['energy']==5
    assert sum(result['bits'][:6])==3
    for bits in itertools.product((0,1),repeat=problem.n):
        assert problem.qubo_energy(bits)==problem.objective(bits)+problem.penalty*problem.violation(bits)


def test_infeasible_provider_never_promoted():
    p=logistics(((1,3),(3,1)),(2,2))
    with pytest.raises(PermissionError):solve(p,sampler=lambda q,n:[(0,)*p.n])
    r=solve(p,sampler=lambda q,n:[(0,)*p.n],authorized=True,reads=1)
    assert r['feasible'] and r['external']['feasible_samples']==0


def test_tensor_binary_decomposition():
    factors=np.array([[[1,0],[0,0]],[[0,0],[0,1]],[[1,1],[1,1]]],dtype=float)
    target=factors[0]+factors[1]
    p=tensor_subset(target,factors,k=2)
    r=solve(p,steps=128)
    assert r['bits']==[1,1,0] and r['energy']==0


def test_infeasible_problem_and_malformed():
    p=logistics(((5,5),),(1,1))
    assert not solve(p)['feasible']
    with pytest.raises(ValueError):BinaryProblem((1,),(),(((1,),1),),())


def test_large_logistics_categorical_neighborhood():
    p=logistics(tuple((1,3,4) for _ in range(6)),(8,8,8))
    r=solve(p,exact_cap=0,steps=4096)
    assert r['feasible'] and not r['exhaustive'] and r['energy']==6


def test_synthesized_memory_new_structure_and_holdout(tmp_path):
    from omega_x_evolution.architecture import Case
    from omega_x_evolution.architecture_synthesis import SynthesizedIndex, synthesize, Plan
    from omega_x_evolution.graph_memory import GraphMemory
    m=GraphMemory(tmp_path/'m.db',b'a'*32,'a')
    a=m.add('artifact','alpha catalyst shared bridge',{})
    b=m.add('artifact','beta bridge evidence',{})
    c=m.add('artifact','gamma temperature',{})
    m.link(a,'supports',b)
    index=SynthesizedIndex(m)
    assert index.hypergraph['bridge']==sorted([a,b])
    rows=index.retrieve(Plan(('hyper',)), 'alpha')
    assert any(r['id']==b for r in rows)
    r=synthesize(index,(Case('alpha catalyst',b),),(Case('alpha shared',b),),(Case('catalyst shared',b),),budget=24)
    assert r['test']['mrr']>=r['baseline_test']['mrr'] and r['test_evaluations']==2
    assert index.retrieve(Plan.from_json(r['selected']),'alpha shared')
    with pytest.raises(ValueError):Plan(('shell','rm'))
    with pytest.raises(ValueError):synthesize(index,(Case('alpha',b),),(Case('alpha',b),),(Case('beta',b),))


def test_mesh_discovery_and_propagation(tmp_path):
    import threading
    from contextlib import ExitStack
    from omega_x_evolution.federation import Identity,Peer
    from omega_x_evolution.mesh import Mesh,Endpoint,serve
    ids=[Identity(bytes([i])*32) for i in (1,2,3)]
    peers=[Peer(tmp_path/f'p{i}.db',ident,[x.public for x in ids if x!=ident]) for i,ident in enumerate(ids)]
    meshes=[Mesh(tmp_path/f'm{i}.db',b'm'*32,p,networks=('127.0.0.0/8',),ports=(1024,65535),create=True) for i,p in enumerate(peers)]
    with ExitStack() as stack:
        servers=[stack.enter_context(serve(m)) for m in meshes]
        threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in servers]
        for t in threads:t.start()
        try:
            endpoints=[Endpoint(x.public,'127.0.0.1',s.server_port) for x,s in zip(ids,servers)]
            for m,e in zip(meshes,endpoints):m.announce(e)
            meshes[1].discover(endpoints[2]);meshes[0].discover(endpoints[1]);assert ids[2].public in meshes[0].endpoints()
            assert meshes[0].propagate(ids[1].public,codes=('-(x+y+2)',))['accepted']==1
            assert meshes[1].propagate(ids[2].public)['accepted']==1
            assert meshes[2].peer.archive().best().code=='-(x+y+2)'
            assert meshes[0].propagate(ids[1].public,codes=('-(x+y+2)',)) is None
            reopened=Mesh(meshes[0].path,b'm'*32,peers[0],networks=('127.0.0.0/8',),ports=(1024,65535));assert ids[2].public in reopened.endpoints()
            with pytest.raises(ValueError):meshes[0].discover(Endpoint(ids[1].public,'169.254.169.254',1234))
        finally:
            for s in servers:s.shutdown()
            for t in threads:t.join(5)


def test_cluster_epigenetics_real_switches_and_restart(tmp_path):
    import asyncio
    from omega_x_evolution.cluster import ClusterConfig, Store, LocalBackend, run_cluster
    from omega_x_evolution.topology import TopologyPolicy
    cfg=ClusterConfig(islands=1,rounds=3,batch=3,budget=9,parallelism=1,topology=TopologyPolicy(),annealed=True,holographic=True,formal_safety=True,epigenetic=True,pressure_schedule=((90,10,0),(30,10,0),(30,10,0)))
    def run(stop=None,create=False):
        store=Store(tmp_path/'c.db',b'c'*32,cfg)
        if create:store.initialize()
        with LocalBackend(cfg,processes=False) as backend:return asyncio.run(run_cluster(store,backend,stop_after=stop))
    assert not run(1,True)['complete'];report=run();assert report['complete']
    state=Store(tmp_path/'c.db',b'c'*32,cfg).open().read(0)[1]
    assert [x['enabled'] for x in state['pressure_history']]==[[],[],['tensor','holographic','topological']]
    assert all(x['action']==6 for x in state['trajectories'][:6])
    assert any(x['action']<6 for x in state['trajectories'][6:])
    assert len(state['formal_records'])==9
    assert report==run()


def test_mixed_bitvector_higher_order_and_fail_closed(monkeypatch):
    from omega_x_evolution.polyglot import Program
    from omega_x_evolution import higher_order
    x=('x',);y=('y',)
    a=Program(('add',('and',x,y),('xor',x,y)));b=Program(('or',x,y))
    result=higher_order.prove(a,b)
    assert result['proved'] and result['solver']['status']=='unsat'
    assert 'funext x y' in higher_order.lean_source(a,b)
    assert 'sorry' not in higher_order.lean_source(a,b)
    monkeypatch.setattr(higher_order.shutil,'which',lambda _:None)
    assert not higher_order.prove(a,b,require_lean=True)['proved']
    assert not higher_order.prove(Program(x),Program(y))['proved']


def test_formal_mixed_optimizer():
    from omega_x_evolution.polyglot import Program
    from omega_x_evolution.higher_order import optimize
    a=Program(('xor',('xor',('x',),('y',)),('y',)))
    r=optimize(a)
    assert r['promoted'] and r['selected']==['x'] and r['proof']['proved']


def test_bft_round_change_preserves_locked_value(tmp_path):
    from omega_x_evolution.bft import Genesis,Replica,make_block,quorum,leader
    from omega_x_evolution.federation import Identity
    ids=[Identity(bytes([i])*32) for i in range(1,5)]
    g=Genesis('a'*64,tuple(sorted(i.public for i in ids)),tuple(sorted(i.public for i in ids)),1,16,2)
    nodes={i.public:Replica(tmp_path/f'{j}.db',b'b'*32,g,i,create=True) for j,i in enumerate(ids)}
    s=next(iter(nodes.values())).inspect()['state'];block=make_block(s,[]);p=nodes[leader(s,0)].propose(block,[r.status() for r in nodes.values()]);pv=quorum(s,[r.prevote(p) for r in nodes.values()],phase='prevote');pcs=[r.precommit(block,pv) for r in nodes.values()]
    # No commit delivered; some nodes advance. Highest prevote QC must be reused.
    active=list(nodes.values())[:3]
    for r in nodes.values():r.advance()
    state=active[0].inspect()['state'];p2=nodes[leader(state,1)].propose(make_block(state,[{'kind':'submit','parent':'-(x+y)','action':0,'seed':42}]),[r.status() for r in active])
    assert p2['body']['block']==block
    pv2=quorum(state,[r.prevote(p2) for r in nodes.values()],phase='prevote');pc2=quorum(state,[r.precommit(block,pv2) for r in nodes.values()],phase='precommit')
    for r in nodes.values():r.commit(block,pv2,pc2)
    assert all(r.inspect()['state']['height']==2 for r in nodes.values())
    assert len({r.inspect()['state']['parent'] for r in nodes.values()})==1


def test_bft_reassign_and_reconfigure(tmp_path):
    from omega_x_evolution.bft import Genesis,Replica,make_block,quorum,leader,recover_ops,task_result
    from omega_x_evolution.federation import Identity
    ids=[Identity(bytes([i])*32) for i in range(1,6)]
    members=tuple(sorted(i.public for i in ids[:4]));g=Genesis('b'*64,members,tuple(sorted(i.public for i in ids)),1,10,2)
    nodes={i.public:Replica(tmp_path/f'{j}.db',b'b'*32,g,i,create=True) for j,i in enumerate(ids)}
    def commit_ops(ops):
        s=nodes[members[0]].inspect()['state'];active=[nodes[i] for i in s['members']];b=make_block(s,ops);p=nodes[leader(s,0)].propose(b,[r.status() for r in active]);pv=quorum(s,[r.prevote(p) for r in active],phase='prevote');pc=quorum(s,[r.precommit(b,pv) for r in active],phase='precommit')
        for r in nodes.values():r.commit(b,pv,pc)
    commit_ops([{'kind':'submit','parent':'-(x+y)','action':0,'seed':42}]);s=nodes[members[0]].inspect()['state'];ops=recover_ops(s,(members[0],));commit_ops(ops)
    s=nodes[members[0]].inspect()['state'];stale=task_result(s,next(iter(s['tasks'])),next(i for i in ids if i.public==members[0]));commit_ops([])
    s=nodes[members[0]].inspect()['state'];assert recover_ops(s,(members[1],));commit_ops(recover_ops(s,(members[1],)));s=nodes[members[1]].inspect()['state'];t=next(iter(s['tasks']));assert s['tasks'][t]['attempt']==2
    with pytest.raises(ValueError):make_block(s,[{'kind':'complete','result':stale}])
    good=task_result(s,t,next(i for i in ids if i.public==members[1]));commit_ops([{'kind':'complete','result':good}]);s=nodes[members[0]].inspect()['state'];assert s['tasks'][t]['result'] is not None
    new=tuple(sorted(set(members[1:])|{ids[4].public}));commit_ops([{'kind':'reconfigure','members':list(new),'faults':1}]);assert all(tuple(r.inspect()['state']['members'])==new for r in nodes.values())


def test_infinite_domain_theorem_synthesis_and_forgery():
    from omega_x_evolution.infinite_discovery import Polynomial, classify, verify, discover
    x=('x',);y=('y',)
    a=Polynomial(('mul',('add',x,y),('sub',x,y)));b=Polynomial(('sub',('mul',x,x),('mul',y,y)))
    r=classify(a,b);assert r['status']=='proved' and verify(a,b,r)
    bad=dict(r);bad['degrees']=[0,0];assert not verify(a,b,bad)
    r=classify(a,Polynomial(x));assert r['status']=='refuted' and verify(a,Polynomial(x),r)
    d=discover(seed=42,budget=48);assert d['proved'] and d['refuted']


def test_inverse_square_scientific_discovery():
    from omega_x_evolution.science import Data
    from omega_x_evolution.infinite_discovery import rational_law
    import random
    rng=random.Random(8);rows=[]
    for _ in range(36):
        m,r=rng.uniform(1,3),rng.uniform(1,3);rows.append(((m,r),m/r**2))
    data=Data(('mass','radius'),((0,1,0,0),(1,0,0,0)),(-2,1,0,0),tuple(rows[:18]),tuple(rows[18:27]),tuple(rows[27:]))
    result=rational_law(data);assert result['test_rmse']<1e-10 and result['terms'][0]['exponents']==[1,-2]
    assert result['test_evaluations']==1


def test_bft_network_leader_failure_and_conflict(tmp_path):
    import threading
    from contextlib import ExitStack
    from omega_x_evolution.bft import Genesis,Replica,leader,make_block
    from omega_x_evolution.bft_transport import serve,run_round
    from omega_x_evolution.mesh import Endpoint
    from omega_x_evolution.federation import Identity
    ids=[Identity(bytes([i])*32) for i in range(1,5)]
    pubs=tuple(sorted(i.public for i in ids));g=Genesis('c'*64,pubs,pubs,1,8,2)
    nodes={i.public:Replica(tmp_path/f'n{j}.db',b'a'*32,g,i,create=True) for j,i in enumerate(ids)}
    with ExitStack() as stack:
        active=[k for k in pubs if k!=pubs[0]];servers={k:stack.enter_context(serve(nodes[k])) for k in active}
        threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in servers.values()]
        for t in threads:t.start()
        try:
            for k in active:nodes[k].advance()
            r=nodes[leader(nodes[active[0]].inspect()['state'],1)];endpoints=tuple(Endpoint(k,'127.0.0.1',s.server_port) for k,s in servers.items() if k!=r.identity.public)
            report=run_round(r,endpoints,[{'kind':'submit','parent':'-(x+y)','action':0,'seed':7}],networks=('127.0.0.0/8',),ports=(1024,65535));assert report['committed'] and report['participants']==3
            assert all(nodes[k].inspect()['state']['height']==2 for k in active)
            nodes[pubs[0]].sync(r.inspect()['log']);assert nodes[pubs[0]].inspect()['state']==r.inspect()['state']
        finally:
            for s in servers.values():s.shutdown()
            for t in threads:t.join(5)


def test_transformer_plasticity_real_training_and_recovery(tmp_path):
    import os,subprocess,sys
    command=[sys.executable,'-m','omega_x_evolution.llm_plasticity','--demo','--db',str(tmp_path/'online.db')]
    env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    r=subprocess.run(command,env=env,capture_output=True,text=True,timeout=90)
    assert r.returncode==0,r.stderr
    import json
    report=json.loads(r.stdout)
    assert report['rounds']==2 and report['spent_steps']==8 and report['attempts']==8
    assert report['base_unchanged'] and report['trainable_parameters']>0 and report['frozen_parameters']>report['trainable_parameters']
    assert report['replay_verified'] and len(report['history'])==2
    assert all(row['actual_steps']==4 and row['records']==4 for row in report['history'])


def test_cloud_budget_lifecycle_and_recovery(tmp_path):
    from omega_x_evolution.cloud import Policy,Job,CloudOrchestrator,manifest
    class Provider:
        namespace='omega-test';identity='fake-https-contract'
        def __init__(self):self.jobs={};self.creates=0;self.deletes=0;self.fail=True
        def create(self,body):
            import copy
            self.creates+=1;obj=copy.deepcopy(body);obj['metadata']['uid']='fixture-uid';self.jobs[body['metadata']['name']]=obj
            if self.fail:self.fail=False;raise TimeoutError('lost response')
            return obj
        def get(self,name):return self.jobs.get(name)
        def delete(self,name,uid):
            assert self.jobs[name]['metadata']['uid']==uid;self.deletes+=1;del self.jobs[name]
    policy=Policy('omega-test','registry.example/engine@sha256:'+'a'*64,5000000,1000000,2000000,3000000,api_call_micros=100,max_jobs=2,max_replicas=3,tpu_accelerator='tpu-v5-lite-podslice',tpu_topology='2x2')
    provider=Provider();o=CloudOrchestrator(tmp_path/'cloud.db',b'a'*32,policy,provider,ledger_id='a'*64,create=True)
    j=Job('first','gpu',2,1,60,42,16)
    with pytest.raises(PermissionError):o.submit(j)
    with pytest.raises(TimeoutError):o.submit(j,authorized=True)
    assert o.inspect()['jobs']['first']['status']=='reserved' and provider.creates==1
    row=o.reconcile('first',authorized=True);assert row['status']=='active' and row['uid']=='fixture-uid'
    assert o.submit(j,authorized=True)==row and provider.creates==1
    other=CloudOrchestrator(o.path,b'a'*32,policy,provider,ledger_id='a'*64)
    with pytest.raises(ValueError):other.submit(Job('second','tpu',2,4,60,42,16),authorized=True)
    assert other.stop(authorized=True)['stopped'] and provider.deletes==1
    assert other.reconcile('first',authorized=True)['status']=='absent'
    with pytest.raises(ValueError):other.submit(Job('third','cpu',1,0,10,42,16),authorized=True)
    spec=manifest(policy,Job('tpu','tpu',1,4,60,42,16),'a'*64)['spec']
    assert spec['template']['spec']['containers'][0]['resources']['limits']['google.com/tpu']=='4'
    assert spec['activeDeadlineSeconds']==60 and spec['backoffLimit']==0


def test_cloud_api_reservation_and_manifest_tamper(tmp_path):
    from omega_x_evolution.cloud import Policy,Job,CloudOrchestrator,manifest
    class P:
        namespace='omega-test';identity='contract';obj=None
        def create(self,b):
            import copy
            self.obj=copy.deepcopy(b);self.obj['metadata']['uid']='uid';self.obj['spec']['activeDeadlineSeconds']=999
            return self.obj
        def get(self,name):return self.obj
        def delete(self,name,uid):raise AssertionError('must not delete unverified object')
    p=Policy('omega-test','registry.example/engine@sha256:'+'a'*64,100000,10000,10000,10000)
    o=CloudOrchestrator(tmp_path/'db',b'g'*32,p,P(),ledger_id='b'*64,create=True)
    with pytest.raises(ValueError):o.submit(Job('bad','cpu',1,0,10,42,16),authorized=True)
    a=o.reserve_api('api-1',100,10,authorized=True);assert a['reserved_micros']==1000 and o.reserve_api('api-1',100,10,authorized=True)==a
    with pytest.raises(ValueError):o.reserve_api('api-1',101,10,authorized=True)
    assert o.settle_api('api-1',50,authorized=True)['used_units']==50
    assert o.inspect()['spent_micros']>=1000


def test_cloud_worker_cpu_and_absent_gpu():
    import subprocess,sys,os,json
    env={**os.environ,'JOB_COMPLETION_INDEX':'1','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    cmd=[sys.executable,'-m','omega_x_evolution.cloud_worker','--kind','cpu','--budget','16'];r=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=30)
    assert r.returncode==0,r.stderr
    assert json.loads(r.stdout)['seed']==43
    # Force CPU-only visible device set without relying on host accelerator presence.
    r=subprocess.run([sys.executable,'-m','omega_x_evolution.cloud_worker','--kind','gpu','--budget','16'],env={**env,'CUDA_VISIBLE_DEVICES':''},capture_output=True,text=True,timeout=30)
    assert r.returncode!=0 and 'Torch training failed' in r.stderr


def test_cloud_https_real_transport(tmp_path):
    import json,ssl,subprocess,threading
    from http.server import BaseHTTPRequestHandler,HTTPServer
    from omega_x_evolution.cloud import KubernetesProvider,Policy,Job,CloudOrchestrator
    cert=tmp_path/'cert.pem';key=tmp_path/'tls.key'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-keyout',str(key),'-out',str(cert),'-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],capture_output=True,check=True,timeout=15)
    state={}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_POST(self):self.handle_call('POST')
        def do_GET(self):self.handle_call('GET')
        def do_DELETE(self):self.handle_call('DELETE')
        def handle_call(self,method):
            assert self.headers['Authorization']=='Bearer '+'z'*32
            assert self.path.startswith('/apis/batch/v1/namespaces/omega-test/jobs')
            raw=self.rfile.read(int(self.headers.get('Content-Length','0')));obj=json.loads(raw) if raw else None
            code=200
            if method=='POST':
                obj['metadata']['uid']='test-uid';state[obj['metadata']['name']]=obj;out=obj;code=201
            elif method=='GET':out=state.get(self.path.rsplit('/',1)[-1]);code=200 if out else 404
            else:
                name=self.path.rsplit('/',1)[-1];assert obj['preconditions']['uid']==state[name]['metadata']['uid'];assert obj['propagationPolicy']=='Foreground';del state[name];out={}
            data=json.dumps(out).encode();self.send_response(code);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    with HTTPServer(('127.0.0.1',0),Handler) as http:
        tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(cert,key);http.socket=tls.wrap_socket(http.socket,server_side=True);t=threading.Thread(target=http.serve_forever,daemon=True);t.start()
        try:
            p=KubernetesProvider(f'https://localhost:{http.server_port}','omega-test','z'*32,ca_file=str(cert))
            policy=Policy('omega-test','registry.example/engine@sha256:'+'a'*64,100000,100000,100000,100000)
            o=CloudOrchestrator(tmp_path/'real.db',b'q'*32,policy,p,ledger_id='c'*64,create=True)
            assert o.submit(Job('real','cpu',1,0,10,42,16),authorized=True)['status']=='active'
            assert o.stop(authorized=True)['delete_errors']==[] and not state
            assert o.reconcile('real',authorized=True)['status']=='absent'
        finally:http.shutdown();t.join(5)


def test_cloud_spec_tamper_after_reservation(tmp_path):
    from omega_x_evolution.cloud import Policy,Job,CloudOrchestrator
    class Provider:
        namespace='omega-test';identity='tamper-contract'
        def create(self,b):
            import copy
            self.actual=copy.deepcopy(b);self.actual['metadata']['uid']='uid';self.actual['spec']['activeDeadlineSeconds']+=1
            return self.actual
        def get(self,name):return self.actual
        def delete(self,name,uid):raise AssertionError('must not delete mutated object')
    p=Policy('omega-test','registry.example/engine@sha256:'+'a'*64,1000000,1000,1000,1000)
    provider=Provider();o=CloudOrchestrator(tmp_path/'db',b'g'*32,p,provider,ledger_id='b'*64,create=True)
    with pytest.raises(ValueError,match='spec mismatch'):o.submit(Job('tampered','cpu',1,0,10,42,16),authorized=True)
    assert o.inspect()['jobs']['tampered']['status']=='reserved'
    assert o.stop(authorized=True)['delete_errors']==['tampered']


def test_qubo_external_contract_exact_sample():
    from omega_x_evolution.optimization import tensor_subset,solve
    p=tensor_subset([[1,0],[0,1]],[[[1,0],[0,0]],[[0,0],[0,1]],[[1,1],[1,1]]],k=2)
    def exact_model(q,reads):
        rows=sorted(itertools.product((0,1),repeat=p.n),key=lambda b:sum(v*b[i]*b[j] for (i,j),v in q.items()))
        return rows[:reads]
    result=solve(p,sampler=exact_model,authorized=True,reads=2)
    assert result['external']['feasible_samples']>=1 and result['external']['best_energy']==result['energy']==0


def test_tpu_jax_cpu_contract(tmp_path):
    import subprocess,sys,os,json
    env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','JAX_PLATFORMS':'cpu'}
    code='from omega_x_evolution.cloud_worker import simulate_tpu; import json; print(json.dumps(simulate_tpu(seed=42,epochs=16)))'
    r=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True,timeout=90)
    assert r.returncode==0,r.stderr
    data=json.loads(r.stdout);assert data['backend']=='jax-cpu-simulation' and data['reference_verified'] and data['loss_after']<data['loss_before']


def test_mesh_bounded_automatic_discovery_and_gossip(tmp_path):
    import threading
    from contextlib import ExitStack
    from omega_x_evolution.federation import Identity, Peer
    from omega_x_evolution.mesh import Mesh,Endpoint,serve
    ids=[Identity(bytes([i])*32) for i in (1,2,3)]
    peers=[Peer(tmp_path/f'auto-p{i}.db',ident,[x.public for x in ids if x!=ident]) for i,ident in enumerate(ids)]
    meshes=[Mesh(tmp_path/f'auto-m{i}.db',b'm'*32,p,networks=('127.0.0.0/8',),ports=(1024,65535),create=True) for i,p in enumerate(peers)]
    with ExitStack() as stack:
        servers=[stack.enter_context(serve(m)) for m in meshes]
        threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in servers]
        for t in threads:t.start()
        try:
            es=tuple(Endpoint(i.public,'127.0.0.1',s.server_port) for i,s in zip(ids,servers))
            for m,e in zip(meshes,es):m.announce(e)
            meshes[1].discover(es[2]);meshes[1].discover(es[0])
            meshes[1].propagate(ids[0].public,codes=('-(x+y+2)',))
            report=meshes[0].sync_once((es[1],),max_contacts=3)
            assert report['contacted']==2 and report['failed']==[]
            assert peers[2].archive().best().code=='-(x+y+2)'
            assert ids[2].public in meshes[0].endpoints()
        finally:
            for s in servers:s.shutdown()
            for t in threads:t.join(5)
