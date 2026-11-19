import copy
import random
import pytest
from omega_x_evolution.quantum import Problem, exact, anneal, hardware
from omega_x_evolution.architecture import Case, Plan, Index, synthesize
from omega_x_evolution.federation import Peer, Identity, packet, exchange, serve
from omega_x_evolution.graph_memory import GraphMemory


def test_qubo_constraint_and_reference():
    p=Problem((10,8,7,6),((0,0),(0,0),(1,1),(9,9)),2)
    b=exact(p); a=anneal(p,seed=42,steps=256)
    assert b['energy']==min(p.energy((i,j)) for i in range(4) for j in range(i+1,4))
    assert a['energy']>=b['energy'] and len(a['indices'])==2
    assert p.qubo_energy(b['indices'])==b['energy']
    assert p.qubo_energy(())>b['energy']


def test_quantum_backend_authorization_and_malformed():
    p=Problem((5,4,3),((0,0),(1,1),(2,2)),2)
    with pytest.raises(PermissionError):hardware(p,lambda q,n:[],authorized=False)
    with pytest.raises(ValueError):hardware(p,lambda q,n:[[0,0]],authorized=True)
    r=hardware(p,lambda q,n:[(0,1),(1,2)],authorized=True,reads=2)
    assert r['indices']==list(exact(p)['indices']) or r['energy']>=exact(p)['energy']


def memory(tmp_path):
    m=GraphMemory(tmp_path/'graph.db',b'g'*32,'demo')
    a=m.add('artifact','thermal cpu temperature',{})
    b=m.add('evidence','cooling throttle heat',{})
    c=m.add('artifact','symbolic equation polynomial',{})
    d=m.add('evidence','algebra derivation formula',{})
    m.link(a,'supports',b);m.link(c,'supports',d)
    return m,a,b,c,d


def test_architecture_search_split_and_provenance(tmp_path):
    m,a,b,c,d=memory(tmp_path);index=Index(m)
    train=(Case('cpu temperature',b),Case('polynomial equation',d))
    val=(Case('thermal cpu',b),Case('symbolic polynomial',d))
    test=(Case('temperature thermal',b),Case('equation symbolic',d))
    r=synthesize(index,train,val,test,budget=24)
    assert r['evaluations']==24 and r['test']['mrr']>=0
    plan=Plan(**r['selected']);hits=index.retrieve(plan,'cpu',limit=4)
    assert all(h['id'] in index.nodes and h['path'][-1]==h['id'] for h in hits)
    with pytest.raises(ValueError):synthesize(index,train,val,train,budget=4)


def peers(tmp_path):
    a,b=Identity(bytes(range(32))),Identity(bytes(range(1,33)))
    return Peer(tmp_path/'a.db',a,[b.public]),Peer(tmp_path/'b.db',b,[a.public])


def test_peer_replay_and_independent_proof(tmp_path):
    a,b=peers(tmp_path)
    raw=packet(a.identity,b.identity.public,1,['-(x+y)','-(x+y+2)'])
    r=b.receive(raw);assert r['accepted']==2 and not r['duplicate']
    assert b.receive(raw)['duplicate']
    assert len(b.archive().lineage)==2
    b=Peer(b.path,b.identity,[a.identity.public]);assert b.receive(raw)['duplicate']
    with pytest.raises(ValueError):b.receive(packet(a.identity,b.identity.public,1,['-(x+y+1)']))
    with pytest.raises(ValueError):b.receive(packet(a.identity,b.identity.public,2,['1/(x-.123456)']))


def test_peer_wrong_recipient_and_tamper(tmp_path):
    a,b=peers(tmp_path)
    raw=packet(a.identity,b.identity.public,1,['-(x+y)']);raw['body']['codes'][0]='-(x+y+1)'
    with pytest.raises(ValueError):b.receive(raw)
    with pytest.raises(ValueError):b.receive(packet(a.identity,a.identity.public,1,['-(x+y)']))


def test_peer_network_and_reverse_exchange(tmp_path):
    import threading
    a,b=peers(tmp_path)
    for source,target in [(a,b),(b,a)]:
        with serve(target) as server:
            thread=threading.Thread(target=server.serve_forever);thread.start()
            try:
                r=exchange('127.0.0.1',server.server_port,packet(source.identity,target.identity.public,1,['-(x+y+2)']))
                assert r['accepted']==1
            finally:server.shutdown();thread.join(5)
    assert a.archive().best().code==b.archive().best().code


def test_packet_atomicity_deletion_and_allowlist(tmp_path):
    import sqlite3
    a,b=peers(tmp_path)
    with pytest.raises(ValueError):b.receive(packet(a.identity,b.identity.public,1,['-(x+y)','1/(x-.123456)']))
    assert not b.archive().lineage
    b.receive(packet(a.identity,b.identity.public,1,['-(x+y)']))
    unauthorized=Identity(b'Z'*32)
    with pytest.raises(ValueError):b.receive(packet(unauthorized,b.identity.public,2,['-(x+y)']))
    with sqlite3.connect(b.path) as db:db.execute('DELETE FROM inbox')
    with pytest.raises(ValueError):b.archive()


def test_export_cluster_and_federated_evolution(tmp_path):
    import asyncio
    from omega_x_evolution.cluster import ClusterConfig,Store,LocalBackend,run_cluster
    from omega_x_evolution.federation import export_store
    a,b=peers(tmp_path)
    cfg=ClusterConfig(islands=2,rounds=2,batch=4,budget=16,parallelism=2,annealed=True,formal_safety=True)
    store=Store(tmp_path/'cluster.db',b'k'*32,cfg).initialize()
    with LocalBackend(cfg,processes=True) as backend:
        r=asyncio.run(run_cluster(store,backend));assert r['complete']
    raw,report=export_store(store,a.identity,b.identity.public,1,limit=4)
    assert b.receive(raw)['accepted']==len(raw['body']['codes'])
    response,run=b.evolve(a.identity.public,1,budget=16,seed=4,limit=4)
    assert run['attempts']==16 and run['accepted']>0 and run['champion']>=run['baseline']
    assert a.receive(response)['accepted']==len(response['body']['codes'])
    assert store.read(0)[1]['done'] # never mutates previous campaign


def test_non_loopback_fails_closed(tmp_path):
    a,b=peers(tmp_path)
    with pytest.raises(ValueError):serve(a,'0.0.0.0')
    with pytest.raises(ValueError):exchange('192.0.2.1',80,packet(a.identity,b.identity.public,1,['-(x+y)']))


def test_qubo_penalty_all_bitstrings():
    from itertools import combinations
    p=Problem((1,5,1000,2),((0,0),(100,100),(60,30),(70,20)),2)
    valid=exact(p)['energy']
    for k in range(5):
        if k!=2:
            assert all(p.qubo_energy(x)>valid for x in combinations(range(4),k))


def test_graph_promotion_and_heldout_independence(tmp_path):
    m,a,b,c,d=memory(tmp_path);idx=Index(m)
    tr=(Case('cpu temperature',b),Case('polynomial equation',d))
    va=(Case('thermal cpu',b),Case('symbolic polynomial',d))
    te=(Case('temperature thermal',b),Case('equation symbolic',d))
    r=synthesize(idx,tr,va,te,budget=24)
    assert r['promoted'] and r['selected']['hops']>0
    assert r['test']['mrr']>r['baseline_test']['mrr']
    wrong=tuple(Case(x.query,a if x.target==b else c) for x in te)
    s=synthesize(idx,tr,va,wrong,budget=24)
    assert s['selected']==r['selected'] and s['validation']==r['validation']


def test_federation_graph_publication_idempotent(tmp_path):
    a,b=peers(tmp_path);b.receive(packet(a.identity,b.identity.public,1,['-(x+y)','-(x+y+2)']))
    m=GraphMemory(tmp_path/'peer-graph.db',b'g'*32,'peer');ids=b.publish(m)
    assert len(ids)==2 and b.publish(m)==ids
    nodes,adj=m.snapshot();assert len(nodes)==3
    assert all(nodes[i]['payload']['certificate']['proved'] for i in ids)
    assert all(adj[i] for i in ids)


def test_signed_receipt_not_reusable_for_other_packet(tmp_path):
    from omega_x_evolution.federation import verify
    a,b=peers(tmp_path);r=b.receive(packet(a.identity,b.identity.public,1,['-(x+y)']))
    body={k:v for k,v in r.items() if k!='signature'};verify(b.identity.public,body,r['signature'])
    body['accepted']=8
    with pytest.raises(ValueError):verify(b.identity.public,body,r['signature'])


def test_real_mutual_tls(tmp_path):
    import subprocess,ssl,threading
    a,b=peers(tmp_path)
    def run(*args):subprocess.run(['openssl',*args],cwd=tmp_path,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
    run('req','-x509','-newkey','rsa:2048','-nodes','-subj','/CN=Test CA','-days','1','-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign','-keyout','ca.key','-out','ca.pem')
    for name in ('server','client'):
        run('req','-newkey','rsa:2048','-nodes','-subj','/CN='+name,'-keyout',name+'.key','-out',name+'.csr')
        (tmp_path/(name+'.ext')).write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nsubjectAltName=IP:127.0.0.1\nextendedKeyUsage='+('serverAuth' if name=='server' else 'clientAuth')+'\n')
        run('x509','-req','-in',name+'.csr','-CA','ca.pem','-CAkey','ca.key','-CAcreateserial','-days','1','-extfile',name+'.ext','-out',name+'.pem')
    ca=str(tmp_path/'ca.pem');server_ctx=ssl.create_default_context(ssl.Purpose.CLIENT_AUTH,cafile=ca);server_ctx.verify_mode=ssl.CERT_REQUIRED
    server_ctx.load_cert_chain(str(tmp_path/'server.pem'),str(tmp_path/'server.key'))
    client_ctx=ssl.create_default_context(ssl.Purpose.SERVER_AUTH,cafile=ca);client_ctx.load_cert_chain(str(tmp_path/'client.pem'),str(tmp_path/'client.key'))
    with serve(b,tls=server_ctx) as server:
        thread=threading.Thread(target=server.serve_forever);thread.start()
        try:
            raw=packet(a.identity,b.identity.public,1,['-(x+y)'])
            assert exchange('127.0.0.1',server.server_port,raw,tls=client_ctx)['accepted']==1
            with pytest.raises((ssl.SSLError,ConnectionError)):exchange('127.0.0.1',server.server_port,raw,tls=ssl.create_default_context(ssl.Purpose.SERVER_AUTH,cafile=ca))
        finally:server.shutdown();thread.join(5)


def test_quantum_selection_on_real_artifacts():
    from omega_x_evolution.quantum import select_elites
    from omega_x_evolution.engine import Artifact,Cascade,Genome
    codes=['-(x+y)','-(x+y+2)','-(x+y+abs(x-y))'];c=Cascade(42)
    rows=[Artifact(str(i),None,0,0,x,Genome(),c.evaluate(x).metrics) for i,x in enumerate(codes)]
    calls=[]
    def sampler(q,n):calls.append(n);return [(0,1),(1,2)]
    with pytest.raises(PermissionError):select_elites(rows,2,sampler=sampler)
    assert not calls
    selected,r=select_elites(rows,2,sampler=sampler,authorized=True,reads=2)
    assert len(selected)==2 and calls==[2] and r['provider_submissions']==1
    assert r['energy']<=r['classical_reference']['energy']
