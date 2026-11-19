"""Paired bounded search benchmark and integrated cluster/recovery evidence."""
from __future__ import annotations
import asyncio
import json
from pathlib import Path
import random
import tempfile
import time
import numpy as np
from omega_x_evolution.annealed import TensorTrain, policy, propose
from omega_x_evolution.cluster import ClusterConfig, Store, LocalBackend, run_cluster
from omega_x_evolution.engine import Cascade, BASELINE, apply_patch, score
from omega_x_evolution.holographic import trajectory
from omega_x_evolution.safety_synthesis import prove
from omega_x_evolution.topology import TopologyPolicy

PARENTS=(BASELINE,'-(x+y+abs(x-y)+1)','-(x+y+(x-y)*(x-y)/(.07+x*y)+2)','-(x+y+abs(x-y)+max(x,y)+min(x,y))')


def pair(seed,adaptive,budget=64):
    c=Cascade(seed); rng=random.Random(seed); params=random.Random(seed^0x1234)
    history=[]; best=BASELINE; champion=score(c.evaluate(best).metrics); counts=[0]*6;accepted=0
    started=time.perf_counter()
    for i in range(budget):
        parent=PARENTS[i%len(PARENTS)];baseline=score(c.evaluate(parent).metrics)
        probs=policy(parent,history[-64:],temperature=max(.1,1-i/budget)) if adaptive else [1/6]*6
        a=rng.choices(range(6),probs)[0];pseed=params.randrange(2**32);code=apply_patch(parent,propose(parent,a,pseed))
        r=c.evaluate(code);ok=r.stage==3 and r.metrics[3]==1.;v=score(r.metrics) if ok else 0.
        history.append(trajectory(str(i),0,'fixture',parent,code,a,ok,v,baseline,r.stage,pseed));counts[a]+=1;accepted+=int(ok)
        if ok and v>champion:best=code;champion=v
    return {'seed':seed,'strategy':'tt' if adaptive else 'uniform','proposals':budget,'accepted':accepted,'action_counts':counts,
            'champion':champion,'holdout':c.heldout(best),'wall_seconds':time.perf_counter()-started}


def cluster():
    cfg=ClusterConfig(islands=8,rounds=4,batch=4,budget=128,parallelism=4,migration_interval=1,topology=TopologyPolicy(),annealed=True,holographic=True,formal_safety=True)
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/'state.db';key=b'b'*32;db=Store(path,key,cfg).initialize()
        with LocalBackend(cfg,processes=True) as backend:
            first=asyncio.run(run_cluster(db,backend,stop_after=11))
        with LocalBackend(cfg,processes=True) as backend:
            r=asyncio.run(run_cluster(Store(path,key,cfg).open(),backend));assert r==asyncio.run(run_cluster(db,backend));r['worker_processes']=len(backend.worker_pids)
        r['checkpoint_commits_before_restart']=first['commits'];r['replay_identical']=True
        r['proof_obligations']=sum(p['certificate']['obligations'] for i in range(cfg.islands) for p in db.read(i)[1]['formal_records'])
        return r


def main():
    rows=[pair(seed,mode) for seed in (81,82,83,84) for mode in (False,True)]
    a=np.einsum('i,j,k->ijk',np.arange(4.)+1,np.arange(4.)+2,np.arange(6.)+3);tt=TensorTrain.fit(a,2)
    out={'paired':rows,'rank_one_fixture':{'dense_parameters':a.size,'tt_parameters':tt.parameters,
        'max_absolute_error':max(abs(tt.at(i,j,k)-a[i,j,k]) for i,j,k in np.ndindex(a.shape))},
        'cluster':cluster(),'safety_examples':{c:prove(c) for c in (BASELINE,'-(x+y+(x-y)*(x-y)/(.01+x*y)+2)','1/(x-.123456)','1e6*1e6*1e6')}}
    print(json.dumps(out,indent=2,allow_nan=False))


if __name__=='__main__':main()
