"""Exploratory fixed synthetic-memory DGM campaign and exact round replay."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from omega_x_evolution.engine import Config
from omega_x_evolution.engine_dgm import DGMJournal, Plan
from test_engine_memory import fixture, bind


async def main():
    results=[]
    with TemporaryDirectory() as directory:
        root=Path(directory)
        p,j,f,s,clock=fixture(root)
        memory=bind(p,j,f,s,clock)
        for seed in (41,5,77):
            plan=Plan(Config(generations=1,islands=1,workers=1,budget=20),2,5,seed)
            passes=[]
            for repeat in range(2):
                a,b=(root/f'a-{seed}-{repeat}',root/f'b-{seed}-{repeat}')
                a.mkdir(mode=0o700); b.mkdir(mode=0o700)
                d=DGMJournal(a/'floor.db',b,memory,plan,plan.pin(memory))
                h=d.initialize(source_fence=f.fence); rows=[]
                for _ in range(2):
                    d=DGMJournal(a/'floor.db',b,memory,plan,plan.pin(memory))
                    g=await d.step(h,source_fence=f.fence)
                    assert g.status=='COMMITTED' and g.record['release_authorized'] is False
                    assert d.active(g.fence,source_fence=f.fence)==g.active
                    h=g.fence; rows.append(g.record)
                passes.append(rows)
            assert passes[0]==passes[1]
            results.append({'seed':seed,'rounds':passes[0],'exact_replay':True})
    print(json.dumps({'schema':'dgm-campaign-v1','results':results,'engine_runs':168,'release_authorized':False},sort_keys=True,separators=(',',':'),allow_nan=False))


if __name__=='__main__': asyncio.run(main())
