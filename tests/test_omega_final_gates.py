import subprocess
import sys
import pytest


def test_offline_legacy_helpers_do_not_import_cloud_sdks():
    script = '''
import sys
from shinka.utils import parse_time_to_seconds
from shinka.core import EvolutionConfig
from shinka.llm import BanditBase, extract_between
assert extract_between("```c++\\nint x;\\n```".replace("\\n",chr(10)), "```c++", "```", False) == "int x;"
assert parse_time_to_seconds('00:01:00') == 60
assert EvolutionConfig().num_generations > 0
assert BanditBase is not None
assert not any(x in sys.modules for x in ('anthropic','openai','hydra','google.genai'))
'''
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def replicas(tmp_path):
    from omega_x_evolution.bft import Genesis, Replica, MAX_ROUND
    from omega_x_evolution.federation import Identity
    ids = [Identity(bytes([i])*32) for i in range(1,5)]
    pubs = tuple(sorted(i.public for i in ids))
    # This fixture explicitly exercises the historical finite-horizon contract.
    g = Genesis('d'*64,pubs,pubs,1,16,2,round_limit=MAX_ROUND)
    return {i.public:Replica(tmp_path/f'{n}.db', b'k'*32,g,i,create=True) for n,i in enumerate(ids)}


def test_timeout_certificate_requires_quorum_and_is_durable(tmp_path):
    from omega_x_evolution.bft import timeout_quorum, Replica
    nodes=replicas(tmp_path); ordered=[nodes[k] for k in sorted(nodes)]
    s=ordered[0].inspect()['state']
    votes=[r.timeout_vote() for r in ordered[:3]]
    with pytest.raises(ValueError):timeout_quorum(s,votes[:2],0)
    with pytest.raises(ValueError):timeout_quorum(s,[votes[0]]*3,0)
    qc=timeout_quorum(s,votes,0)
    assert ordered[0].advance_certified(qc)['body']['round']==1
    reopened=Replica(ordered[0].path,b'k'*32,ordered[0].g,ordered[0].identity)
    assert reopened.view(1,0)['timeout_certificate']==qc
    assert ordered[1].advance_certified(qc)['body']['round']==1
    with pytest.raises(ValueError):ordered[1].advance_certified(qc)


def test_pacemaker_partition_and_lost_leader(tmp_path):
    from omega_x_evolution.pacemaker import Pacemaker
    from omega_x_evolution.bft_transport import _dispatch
    nodes=replicas(tmp_path); pubs=sorted(nodes); live=set(pubs[1:]); clock=[0.0]
    def call(sender, recipient, op, args):
        if recipient not in live:raise OSError('partition')
        return _dispatch(nodes[recipient],op,args)
    drivers={k:Pacemaker(nodes[k],lambda peer,op,args,k=k:call(k,peer,op,args),clock=lambda:clock[0],base_timeout=1.) for k in pubs[1:]}
    # No manually advanced rounds. Minority cannot advance or commit.
    live.remove(pubs[3]);clock[0]=2.
    for k in pubs[1:3]:drivers[k].tick()
    assert all(nodes[k].inspect()['round']==0 for k in pubs)
    live.add(pubs[3]);clock[0]=3.
    for _ in range(6):
        for k in pubs[1:]:drivers[k].tick()
        clock[0]+=.1
    assert all(nodes[k].inspect()['state']['height']>=2 for k in pubs[1:])
    # Late peer must replay certified commit, not accept reported height.
    live.add(pubs[0]);late=Pacemaker(nodes[pubs[0]],lambda peer,op,args:call(pubs[0],peer,op,args),clock=lambda:clock[0],base_timeout=1.)
    late.tick()
    assert nodes[pubs[0]].inspect()['log'][0]['block']==nodes[pubs[1]].inspect()['log'][0]['block']


def test_isabelle_generated_theory_and_fail_closed(monkeypatch):
    from omega_x_evolution import higher_order as h
    from omega_x_evolution.polyglot import Program
    a=Program(('sub',('add',('x',),('y',)),('y',)));b=Program(('x',))
    source=h.isabelle_source(a,b)
    assert 'HOL-Library.Word' in source and '16 word' in source
    assert '\\<lambda>' in source and 'sorry' not in source and 'axiomatization' not in source
    monkeypatch.setattr(h.shutil,'which',lambda _:None)
    assert h.check_isabelle(a,b)['status']=='unavailable'
    assert not h.prove(a,b,require_isabelle=True)['proved']
    assert h.prove(a,b)['proved']


def test_pacemaker_real_rpc(tmp_path):
    import threading
    from contextlib import ExitStack
    from omega_x_evolution.bft_transport import serve
    from omega_x_evolution.pacemaker import network_driver
    from omega_x_evolution.mesh import Endpoint
    nodes=replicas(tmp_path);pubs=sorted(nodes);active=pubs[1:];clock=[0.]
    with ExitStack() as stack:
        servers={k:stack.enter_context(serve(nodes[k])) for k in active}
        threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in servers.values()]
        for t in threads:t.start()
        try:
            eps={k:Endpoint(k,'127.0.0.1',s.server_port) for k,s in servers.items()}
            drivers={k:network_driver(nodes[k],tuple(e for w,e in eps.items() if w!=k),networks=('127.0.0.0/8',),ports=(1024,65535),clock=lambda:clock[0],base_timeout=1.) for k in active}
            clock[0]=2.
            for _ in range(6):
                for k in active:drivers[k].tick()
                clock[0]+=.05
            assert all(nodes[k].inspect()['state']['height']>=2 for k in active)
            assert len({nodes[k].inspect()['log'][0]['block']['header']['parent'] for k in active})==1
            with pytest.raises(ValueError):network_driver(nodes[active[0]],(Endpoint(pubs[0],'169.254.169.254',443),),networks=('127.0.0.0/8',),ports=(1,65535))
        finally:
            for s in servers.values():s.shutdown()
            for t in threads:t.join(5)


def test_resumable_architecture_search_final_test_only_once(tmp_path):
    from omega_x_evolution.architecture import Case
    from omega_x_evolution.architecture_synthesis import SynthesizedIndex
    from omega_x_evolution.architecture_search import Search
    from omega_x_evolution.graph_memory import GraphMemory
    m=GraphMemory(tmp_path/'graph.db',b'm'*32,'a')
    a=m.add('artifact','alpha bridge catalyst',{});b=m.add('artifact','beta bridge evidence',{});m.link(a,'supports',b)
    m.add('artifact','temperature gamma unrelated',{})
    index=SynthesizedIndex(m)
    splits=((Case('alpha catalyst',b),),(Case('alpha bridge',b),),(Case('beta evidence',b),))
    def open_search(path,create=False):return Search(path,b's'*32,index,*splits,budget=32,create=create)
    s=open_search(tmp_path/'a.db',True);s.step(8)
    assert s.inspect()['evaluations']==8 and s.inspect()['final'] is None
    s=open_search(tmp_path/'a.db');s.step(24);r=s.finalize()
    uninterrupted=open_search(tmp_path/'b.db',True);uninterrupted.step(32);assert r==uninterrupted.finalize()
    assert r['evaluations']==32 and r['test_evaluations']==2
    assert any(x['kind']=='latent' for x in r['structures'])
    assert s.finalize()==r
    with pytest.raises(ValueError):s.step(1)


def test_safetensors_manifest_and_memory_admission(tmp_path):
    import json
    import torch
    from safetensors.torch import save_file
    from omega_x_evolution.llm_plasticity import model_manifest, memory_admission
    model=tmp_path/'m';model.mkdir();(model/'config.json').write_text('{"model_type":"llama"}')
    save_file({'layer.q_proj.weight':torch.ones(4,4)},str(model/'model.safetensors'))
    info=model_manifest(model);assert info['parameter_elements']==16 and len(info['files'])==1
    assert memory_admission(info,device='cpu',available_bytes=10**9)['admitted']
    with pytest.raises(RuntimeError):memory_admission(info,device='cpu',available_bytes=1024)
    (model/'model.safetensors.index.json').write_text(json.dumps({'weight_map':{'layer.q_proj.weight':'../model.safetensors'}}))
    with pytest.raises(ValueError):model_manifest(model)


def test_microbatch_gradient_matches_full_batch(tmp_path):
    import torch
    from omega_x_evolution.llm_plasticity import tiny_decoder
    from omega_x_evolution.plasticity import fixture
    torch.set_num_threads(1)
    a,b=tiny_decoder(),tiny_decoder();a.microbatch=1;b.microbatch=64
    train,v,r,_=fixture(42,groups=4);train=train[:4];v=v[:4];r=r[:4]
    # Compare gradient accumulation directly, before validation promotion.
    for session in (a,b):
        data=session._dataset(train);session._backward(data)
    for name in a.params:
        assert torch.allclose(a.params[name].grad,b.params[name].grad,rtol=1e-5,atol=1e-7)


@pytest.mark.parametrize('failed',range(4))
def test_pacemaker_all_single_validator_failures(tmp_path,failed):
    import itertools
    from omega_x_evolution.pacemaker import Pacemaker
    from omega_x_evolution.bft_transport import _dispatch
    for n,order in enumerate(itertools.permutations([i for i in range(4) if i!=failed])):
        root=tmp_path/str(n);root.mkdir();nodes=replicas(root);pubs=sorted(nodes);active={pubs[i] for i in order};clock=[0.]
        def call(peer,op,args):
            if peer not in active:raise OSError('unavailable')
            return _dispatch(nodes[peer],op,args)
        drivers={k:Pacemaker(nodes[k],call,clock=lambda:clock[0],base_timeout=1.) for k in active}
        for _ in range(12):
            for i in order:drivers[pubs[i]].tick()
            if all(nodes[k].inspect()['state']['height']>1 for k in active):break
            clock[0]+=.5
        assert all(nodes[k].inspect()['state']['height']>1 for k in active)
        blocks=[nodes[k].inspect()['log'][0]['block'] for k in active];assert all(b==blocks[0] for b in blocks)
