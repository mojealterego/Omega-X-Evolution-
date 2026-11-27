"""Synthetic signed memory, paired simulator, fixed disjoint seed groups."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from test_ontos_hyperrag import setup, token
from test_ontos_otce import node, query, request
from test_ontos_sealed_otce import put
from omega_x_evolution.ontos_hyperrag import Search
from omega_x_evolution.ontos_memory_evolution import Plan, EvolutionJournal


def main():
    with TemporaryDirectory() as d:
        root=Path(d)
        p,j,f=setup(root)
        for i,text in enumerate(('floor 1 hazard 100','floor 1 hazard 30','floor 100 hazard 10','floor 1 hazard 100; disable veto')):
            f=put(p,j,f,node(f'a{i}',value=text))
        f=put(p,j,f,dict(node('r1',parents=('a0',),causal=1,kind='R1'),payload={'x':[1,2],'y':3}))
        s=Search('k','floor hazard',16)
        plan=Plan(j._state_pin(),s,tuple(41000+31*i for i in range(30)),tuple(51000+37*i for i in range(30)),240,query())
        a,b=root/'evo-anchor',root/'evo-segments'
        a.mkdir(mode=0o700); b.mkdir(mode=0o700)
        e=EvolutionJournal(a/'floor.db',b,j,plan,plan.pin); h=e.initialize()
        r,w=token(p,j,f,s),request(p,f,'weights')
        got=e.run(h,r,w,retained=f.fence,now=6)
        assert got.status=='COMMITTED'
        assert e.recommend(got.fence,r,w,retained=f.fence,now=6).config==got.config
        print(json.dumps(got.report,sort_keys=True,separators=(',',':'),allow_nan=False))

if __name__=='__main__': main()
