"""Bounded formal-proof and process-isolated quorum/search evidence."""
from __future__ import annotations
import concurrent.futures as cf
import json
import multiprocessing as mp
import os
from pathlib import Path
import secrets
import tempfile
import time
from omega_x_evolution.epigenetics import Switchboard,Telemetry
from omega_x_evolution.polyglot import Program
from omega_x_evolution.proof_kernel import certify,verify_certificate,optimize,check_lean
from omega_x_evolution.bitproof import prove as smt_prove
from omega_x_evolution.federation import Identity,Peer
from omega_x_evolution.swarm import Campaign,BallotStore,proposal,certificate,request_vote,serve,aggregate,export


def proofs():
    x=('x',);y=('y',);z=('lit',0);one=('lit',1)
    pairs=[(('sub',('add',x,y),y),x),(('mul',x,('add',y,('lit',65535))),('sub',('mul',x,y),x)),(('add',('mul',x,one),z),x),(('mul',('sub',x,x),y),z)]
    result=[]
    for a,b in pairs:
        a,b=Program(a),Program(b);t=time.perf_counter();cert=certify(a,b);ok=verify_certificate(a,b,cert);elapsed=time.perf_counter()-t
        result.append({'left':a.tree,'right':b.tree,'nodes':[a.size,b.size],'proved':ok,'certificate_bytes':len(json.dumps(cert).encode()),'local_seconds':elapsed,'smt':smt_prove(a,b),'optimization':optimize(a)})
    return {'cases':result,'negative':certify(Program(x),Program(y)),'lean':check_lean(Program(pairs[0][0]),Program(x))}


def _serve(path,key,c,queue,stop):
    s=BallotStore(path,Identity(key),c)
    with serve(s) as http:
        http.timeout=.2;queue.put((http.server_port,os.getpid()))
        while not stop.is_set():http.handle_request()


def _work(path,key,c,q,ts):
    s=BallotStore(path,Identity(key),c);r=s.execute(q,telemetry=ts)
    assert s.execute(q)==r
    return os.getpid(),r


def campaign(root):
    ctx=mp.get_context('spawn');keys=[secrets.token_bytes(32) for _ in range(4)];ids=[Identity(k) for k in keys]
    c=Campaign('a'*64,tuple(sorted(i.public for i in ids)),faults=1,slots=64,epochs=2,seed=42)
    paths=[root/f'peer-{i}.db' for i in range(4)];stop=ctx.Event();ps=[];ports=[];pids=[]
    try:
        for i in range(4):
            q=ctx.Queue();p=ctx.Process(target=_serve,args=(paths[i],keys[i],c,q,stop));p.start();ps.append(p);port,pid=q.get(timeout=15);ports.append(port);pids.append(pid);q.close();q.join_thread()
        # Peer 0 proposes epoch 1; peer 3 proposes epoch 2. Any member can gather votes.
        reports=[];all_workers=set();last=None
        with cf.ProcessPoolExecutor(max_workers=4,mp_context=ctx) as pool:
            for e,active in ((1,3),(2,4)):
                p=proposal(c,ids[e-1],e,offset=e-1)
                with cf.ThreadPoolExecutor(max_workers=4) as net:
                    votes=[f.result(timeout=15) for f in [net.submit(request_vote,'127.0.0.1',ports[i],c,p,ids[i].public) for i in range(active)]]
                cert=certificate(c,p,votes);ts=[Telemetry(90,30,30),Telemetry(20,20,20),Telemetry(20,20,20)]+[Telemetry(20,20,20)]*13
                futures=[pool.submit(_work,paths[i],keys[i],c,cert,ts) for i in range(active)]
                rs=[f.result(timeout=60) for f in futures];all_workers.update(pid for pid,_ in rs);raw=[r for _,r in rs];agg=aggregate(c,cert,raw);agg['votes']=len(votes);agg['durable_replay']=True;reports.append(agg);last=(cert,raw)
        # Conflicting epoch 1 proposal must not collect a second honest quorum.
        conflict=proposal(c,ids[3],1,offset=1);refused=0
        for i in range(3):
            try:request_vote('127.0.0.1',ports[i],c,conflict,ids[i].public)
            except ValueError:refused+=1
        cert,raw=last;receiver=Peer(root/'inbox.db',ids[1],[ids[0].public]);pk=export(c,cert,raw[0],ids[0],ids[1].public,1);receipt=receiver.receive(pk)
        return {'membership':len(ids),'f':c.faults,'quorum':c.quorum,'vote_server_processes':len(set(pids)),'work_processes':len(all_workers),'epochs':reports,'conflicting_votes_refused':refused,'federated_artifacts':receipt['accepted'],'replay_suppressed':receiver.receive(pk)['duplicate']}
    finally:
        stop.set()
        for p in ps:
            p.join(5)
            if p.is_alive():p.terminate();p.join(5)
            if p.exitcode!=0:raise RuntimeError('vote process failed')


def main():
    board=Switchboard();trace=[board.update(Telemetry(*s)) for s in ((95,30,30),(65,30,30),(20,20,20),(20,20,20),(20,95,20))]
    with tempfile.TemporaryDirectory() as d:
        print(json.dumps({'epigenetic_trace':trace,'live_telemetry':Telemetry.sample(10).__dict__,'formal':proofs(),'swarm':campaign(Path(d))},indent=2,allow_nan=False))

if __name__=='__main__':main()
