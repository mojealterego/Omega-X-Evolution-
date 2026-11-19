import copy
import pytest
from omega_x_evolution.epigenetics import Switchboard, Telemetry
from omega_x_evolution.proof_kernel import certify, verify_certificate, lean_source, check_lean, optimize
from omega_x_evolution.polyglot import Program
from omega_x_evolution.federation import Identity
from omega_x_evolution.swarm import Campaign, proposal, BallotStore, certificate, verify_certificate as verify_quorum, work, verify_result, serve, request_vote


def test_epigenetic_reversible_hysteresis():
    b=Switchboard()
    assert b.update(Telemetry(95,90,50))['enabled']==[]
    assert b.update(Telemetry(30,30,50))['enabled']==[]
    assert set(b.update(Telemetry(30,30,50))['enabled'])=={'neural','associative','guided'}
    assert b.update(Telemetry(95,30,50))['enabled']==[]
    assert 'formal' in b.state()['mandatory']
    with pytest.raises(ValueError):Telemetry(-1,30,50)


def test_polynomial_proof_and_tamper():
    a=Program(('sub',('add',('x',),('y',)),('y',)));b=Program(('x',))
    proof=certify(a,b);assert proof['proved'] and verify_certificate(a,b,proof)
    fake=copy.deepcopy(proof);fake['left'][-1][0][2]=99
    assert not verify_certificate(a,b,fake)
    assert not certify(a,Program(('y',)))['proved']
    assert 'bv_decide' in lean_source(a,b) and 'sorry' not in lean_source(a,b)


def test_distribution_mod16_and_unknown():
    a=Program(('mul',('x',),('add',('y',),('lit',65535))))
    b=Program(('sub',('mul',('x',),('y',)),('x',)))
    assert certify(a,b)['proved']
    assert not certify(Program(('xor',('x',),('y',))),a)['proved']


def test_proof_optimizer():
    a=Program(('sub',('add',('x',),('y',)),('y',)))
    r=optimize(a);assert r['selected']==['x'] and r['selected_nodes']==1 and r['proof']['proved']


def setup(tmp_path):
    ids=[Identity(bytes([i])*32) for i in range(1,5)]
    c=Campaign('a'*64,tuple(sorted(x.public for x in ids)),faults=1,slots=12,epochs=2)
    stores=[BallotStore(tmp_path/f'{i}.db',identity,c) for i,identity in enumerate(ids)]
    return ids,c,stores


def test_quorum_and_persisted_equivocation(tmp_path):
    ids,c,stores=setup(tmp_path);p=proposal(c,ids[0],1)
    votes=[x.vote(p) for x in stores[:3]];q=certificate(c,p,votes)
    assert verify_quorum(c,q)==p['body']
    with pytest.raises(ValueError):certificate(c,p,votes[:2])
    with pytest.raises(ValueError):certificate(c,p,[votes[0],votes[0],votes[1]])
    s=BallotStore(stores[0].path,ids[0],c);assert s.vote(p)==votes[0]
    with pytest.raises(ValueError):s.vote(proposal(c,ids[1],1,offset=1))
    fake=copy.deepcopy(q);fake['proposal']['body']['assignments'][0]=ids[2].public
    with pytest.raises(ValueError):verify_quorum(c,fake)


def test_swarm_work_and_fail_closed(tmp_path):
    ids,c,stores=setup(tmp_path);p=proposal(c,ids[0],1);q=certificate(c,p,[x.vote(p) for x in stores[:3]])
    rs=[work(c,q,i,telemetry=[Telemetry(20,20,20)]*3) for i in ids]
    slots=[]
    for r in rs:
        body=verify_result(c,q,r);slots.extend(row['slot'] for row in body['rows'])
    assert sorted(slots)==list(range(c.slots))
    bad=copy.deepcopy(rs[0]);bad['body']['rows'][0]['code']='1/(x-.12)';bad['signature']=ids[0].sign(bad['body'])
    with pytest.raises(ValueError):verify_result(c,q,bad)
    with pytest.raises(ValueError):work(c,{'proposal':p,'votes':[]},ids[0])


def test_network_vote(tmp_path):
    import threading
    ids,c,stores=setup(tmp_path);p=proposal(c,ids[0],1)
    with serve(stores[1]) as server:
        t=threading.Thread(target=server.serve_forever);t.start()
        try:assert request_vote('127.0.0.1',server.server_port,c,p,ids[1].public)==stores[1].vote(p)
        finally:server.shutdown();t.join(5)


def test_execution_persistence_and_manifest(tmp_path):
    import sqlite3
    from omega_x_evolution.swarm import aggregate
    ids,c,s=setup(tmp_path);p=proposal(c,ids[0],1);q=certificate(c,p,[x.vote(p) for x in s[:3]])
    ts=[Telemetry(90,20,20),Telemetry(20,20,20),Telemetry(20,20,20)]
    r=s[0].execute(q,telemetry=ts);s0=BallotStore(s[0].path,ids[0],c)
    assert s0.execute(q)==r
    assert [x['mode'] for x in r['body']['rows']][:2]==['uniform','uniform']
    assert r['body']['rows'][2]['mask']['enabled']
    with pytest.raises(ValueError):s0.execute(q,telemetry=[Telemetry(20,20,20)]*3)
    assert aggregate(c,q,[r])['executed_slots']==3
    with pytest.raises(ValueError):aggregate(c,q,[r,r])
    with sqlite3.connect(s0.path) as db:db.execute('DELETE FROM executions')
    with pytest.raises(ValueError):BallotStore(s0.path,ids[0],c)


def test_signed_but_forged_search_result(tmp_path):
    from omega_x_evolution.safety_synthesis import prove
    from omega_x_evolution.engine import Cascade
    ids,c,s=setup(tmp_path);p=proposal(c,ids[0],1);q=certificate(c,p,[x.vote(p) for x in s[:3]])
    r=work(c,q,ids[0]);b=r['body'];row=b['rows'][0];row.update(code='-(x+y)',proof=prove('-(x+y)'),metrics=list(Cascade(42).evaluate('-(x+y)').metrics),accepted=True)
    r['signature']=ids[0].sign(b)
    with pytest.raises(ValueError,match='transcript'):verify_result(c,q,r)


def test_quorum_intersection_exhaustive():
    from itertools import combinations
    for n,f in ((4,1),(7,2),(10,3)):
        sets=[set(x) for x in combinations(range(n),n-f)]
        assert all(len(a&b)>f for a in sets for b in sets)


def test_lean_explicit_absent_backend(monkeypatch):
    from omega_x_evolution import proof_kernel
    monkeypatch.setattr(proof_kernel.shutil,'which',lambda _:None)
    a=Program(('add',('x',),('lit',0)));b=Program(('x',))
    assert check_lean(a,b)['status']=='unavailable'
    r=optimize(a,require_lean=True);assert not r['promoted'] and r['selected_nodes']==a.size


def test_proof_checker_independent_of_generator(monkeypatch):
    from omega_x_evolution import proof_kernel
    a=Program(('sub',('add',('x',),('y',)),('y',)));b=Program(('x',))
    p=certify(a,b)
    monkeypatch.setattr(proof_kernel,'certify',lambda *args: (_ for _ in ()).throw(RuntimeError('generator unavailable')))
    assert verify_certificate(a,b,p)
    p['left'][0][0][2]=True
    assert not verify_certificate(a,b,p)


def test_live_telemetry():
    t=Telemetry.sample(50);assert 0<=t.cpu<=100 and 0<=t.memory<=100 and t.queue==50


def test_swarm_federation_bridge(tmp_path):
    from omega_x_evolution.swarm import export
    from omega_x_evolution.federation import Peer
    ids,c,s=setup(tmp_path);p=proposal(c,ids[0],1);q=certificate(c,p,[x.vote(p) for x in s[:3]])
    r=s[0].execute(q);peer=Peer(tmp_path/'federated.db',ids[1],[ids[0].public]);packet=export(c,q,r,ids[0],ids[1].public,1)
    receipt=peer.receive(packet);assert receipt['accepted']>0 and peer.receive(packet)['duplicate']


def test_live_swarm_telemetry_replayed(tmp_path):
    ids,c,s=setup(tmp_path);p=proposal(c,ids[0],1);q=certificate(c,p,[x.vote(p) for x in s[:3]])
    r=s[0].execute(q,live=True);assert verify_result(c,q,r)['telemetry']==r['body']['telemetry']
    assert s[0].execute(q,live=True)==r
