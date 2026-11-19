"""Explicit acceptance gate: real Ray, actor kill, durable continuation. No mocks."""
from __future__ import annotations
import argparse
import asyncio
import json
import secrets
import tempfile
from pathlib import Path
from omega_x_evolution.cluster import ClusterConfig, RayBackend, Store, run_cluster


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--address',default='local')
    p.add_argument('--islands',type=int,default=2)
    p.add_argument('--distinct-nodes',action='store_true')
    a=p.parse_args()
    cfg=ClusterConfig(islands=a.islands,rounds=2,batch=2,budget=a.islands*4,parallelism=a.islands,migration_interval=1)
    with tempfile.TemporaryDirectory() as d, RayBackend(cfg,address=a.address,distinct_nodes=a.distinct_nodes) as backend:
        store=Store(Path(d)/'run.db',secrets.token_bytes(32),cfg).initialize()
        first=asyncio.run(run_cluster(store,backend,stop_after=1))
        assert first['commits']==1
        # Kill the live process; allow configured actor restart. The durable
        # snapshot is sent to the new incarnation on its next operation.
        backend.ray.kill(backend.actors[0],no_restart=False)
        final=asyncio.run(run_cluster(store,backend))
        if not final['complete'] or final['attempts']!=cfg.islands*4 or final['commits']!=cfg.islands*3:
            raise RuntimeError('Ray recovery invariant failed')
        if a.distinct_nodes and len(backend.nodes)!=cfg.islands:
            raise RuntimeError('distinct-node acceptance failed')
        print(json.dumps({**final,'observed_nodes':len(backend.nodes),'observed_processes':len(backend.worker_pids)},indent=2))


if __name__=='__main__':main()
