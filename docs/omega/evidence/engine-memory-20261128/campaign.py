"""Fixed synthetic-memory scheduler campaign; no operational deployment."""
import asyncio
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from omega_x_evolution.checkpoint import CheckpointStore
from omega_x_evolution.engine import Config, run
from test_engine_memory import fixture, bind


def main():
    rows=[]
    with TemporaryDirectory() as tmp:
        root=Path(tmp); p,j,f,s,clock=fixture(root)
        a=bind(p,j,f,s,clock)
        for seed in (101,211,512):
            cfg=Config(seed=seed,generations=3,islands=2,workers=2,budget=100,concurrency=2)
            baseline=asyncio.run(run(cfg))
            memory=asyncio.run(run(cfg,a))
            store=CheckpointStore(root/f'run-{seed}.db',b'k'*32)
            asyncio.run(run(replace(cfg,generations=1),a,checkpoint=store))
            resumed=asyncio.run(run(cfg,bind(p,j,f,s,clock),checkpoint=store,resume=True,evaluation_processes=2))
            assert memory==resumed
            assert memory['release_authorized'] is False
            rows.append({'seed':seed,'baseline':baseline,'memory':memory,'exact_resume_match':True})
        print(json.dumps({'schema':'engine-memory-campaign-v1','rows':rows,'release_authorized':False},sort_keys=True,separators=(',',':'),allow_nan=False))


if __name__=='__main__': main()
