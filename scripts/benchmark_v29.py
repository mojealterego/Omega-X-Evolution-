"""Cost-accounted local QUBO, architecture and real process federation evidence."""
from __future__ import annotations
import asyncio
import json
import multiprocessing as mp
from pathlib import Path
import random
import secrets
import tempfile
import time
from omega_x_evolution.quantum import Problem, exact, anneal
from omega_x_evolution.architecture import Index, Case, synthesize
from omega_x_evolution.graph_memory import GraphMemory
from omega_x_evolution.federation import Identity,Peer,serve,exchange,export_store
from omega_x_evolution.cluster import ClusterConfig, Store,LocalBackend,run_cluster


def optimizer():
    results=[]
    for seed in (81,82,83,84):
        rng=random.Random(seed);p=Problem(tuple(rng.randrange(400,1001) for _ in range(16)),tuple(tuple(rng.randrange(101) for _ in range(8)) for _ in range(16)),4)
        b=exact(p);a=anneal(p,seed=seed,steps=512);rng=random.Random(seed);t=time.perf_counter();cost=a['objective_evaluations']
        random_best=min((p.energy(x),x) for x in (tuple(sorted(rng.sample(range(p.n),p.k))) for _ in range(cost)))
        results.append({'seed':seed,'exact':b,'anneal':a,'random':{'objective_evaluations':cost,'energy':random_best[0],'indices':random_best[1],'wall_seconds':time.perf_counter()-t}})
    return results


def architecture(path):
    m=GraphMemory(path,secrets.token_bytes(32),'study');groups=[[],[],[]]
    fixtures=[('cpu thermal heat','fan throttle cooling','temperature control policy'),('symbolic polynomial algebra','equation theorem proof','formal simplification result'),('neural training gradient','optimizer momentum learning','weights validation checkpoint'),('network socket transport','tls packet connection','latency retry handshake'),('camera sensor optics','lens aperture exposure','photographic calibration evidence'),('storage disk volume','archive backup checksum','persistence integrity journal'),('robot motor motion','kinematic position velocity','trajectory dynamics measurement'),('chemical reaction molecule','kinetics reagent catalyst','experiment concentration record')]
    for i,(q,x,y) in enumerate(fixtures):
        a=m.add('artifact',q,{'domain':i});b=m.add('evidence',y,{'domain':i});m.link(a,'supports',b)
        terms=q.split();noise=x.split()
        for j in range(3):groups[j].append(Case(terms[j]+' '+noise[j],b))
    r=synthesize(Index(m),*(tuple(g) for g in groups),budget=56);return r


def _server(path,key,allowed,ports,stop):
    peer=Peer(path,Identity(key),allowed)
    with serve(peer) as server:
        server.timeout=.2;ports.put((server.server_port,__import__('os').getpid()))
        while not stop.is_set():server.handle_request()


def federation(root):
    cfg=ClusterConfig(islands=4,rounds=3,batch=4,budget=48,parallelism=2,annealed=True,holographic=True,formal_safety=True)
    db=Store(root/'source.db',secrets.token_bytes(32),cfg).initialize()
    with LocalBackend(cfg,processes=True) as backend:source=asyncio.run(run_cluster(db,backend));source['workers']=len(backend.worker_pids)
    context=mp.get_context('spawn');keys=[secrets.token_bytes(32) for _ in range(3)];identities=[Identity(k) for k in keys];pubs=[x.public for x in identities];paths=[root/f'peer{i}.db' for i in range(3)];stops=context.Event();procs=[];ports=[];pids=[]
    try:
        for i in range(3):
            q=context.Queue();p=context.Process(target=_server,args=(paths[i],keys[i],[x for x in pubs if x!=pubs[i]],q,stops));p.start();procs.append(p);port,pid=q.get(timeout=15);ports.append(port);pids.append(pid);q.close();q.join_thread()
        peers=[Peer(paths[i],identities[i],[x for x in pubs if x!=pubs[i]]) for i in range(3)]
        raw,selection=export_store(db,identities[0],pubs[1],1,limit=4)
        r=exchange('127.0.0.1',ports[1],raw);duplicate=exchange('127.0.0.1',ports[1],raw)
        x,run1=peers[1].evolve(pubs[2],1,budget=32,limit=4,seed=81);r1=exchange('127.0.0.1',ports[2],x)
        y,run2=peers[2].evolve(pubs[0],1,budget=32,limit=4,seed=82);r2=exchange('127.0.0.1',ports[0],y)
        graph=GraphMemory(root/'published.db',secrets.token_bytes(32),'federated');ids=peers[0].publish(graph);assert ids==peers[0].publish(graph)
        return {'source':source,'server_processes':len(set(pids)),'received':[r['accepted'],r1['accepted'],r2['accepted']], 'duplicate_suppressed':duplicate['duplicate'],'selection':selection,'local_evolution':[run1,run2],'archive_sizes':[len(p.archive().lineage) for p in peers],'published_nodes':len(ids),'graph_total_nodes':len(graph.snapshot()[0])}
    finally:
        stops.set()
        for p in procs:
            p.join(5)
            if p.is_alive():p.terminate();p.join(5)
            if p.exitcode!=0:raise RuntimeError('peer process failed')


def main():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);out={'qubo':optimizer(),'architecture':architecture(root/'study.db'),'federation':federation(root),'physical_quantum':False}
    print(json.dumps(out,indent=2,allow_nan=False))


if __name__=='__main__':main()
