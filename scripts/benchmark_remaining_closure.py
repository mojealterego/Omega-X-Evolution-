"""Bounded reproducible evidence for existing maintainer requirements 5–12."""
from pathlib import Path
import itertools
import json
import random
import tempfile
import numpy as np
from omega_x_evolution.optimization import logistics, tensor_subset, solve
from omega_x_evolution.graph_memory import GraphMemory
from omega_x_evolution.architecture import Case
from omega_x_evolution.architecture_synthesis import SynthesizedIndex, synthesize
from omega_x_evolution.higher_order import prove
from omega_x_evolution.polyglot import Program
from omega_x_evolution.infinite_discovery import discover, rational_law
from omega_x_evolution.science import Data
from omega_x_evolution.llm_plasticity import demo
from omega_x_evolution.cloud_worker import simulate_tpu


def main():
    p=logistics(((2,5),(4,1),(2,3)),(4,4))
    def sample(q,reads):
        return sorted(itertools.product((0,1),repeat=p.n),key=lambda b:sum(v*b[i]*b[j] for (i,j),v in q.items()))[:reads]
    logistic=solve(p,sampler=sample,authorized=True,reads=8)
    atoms=np.array([[[1,0],[0,0]],[[0,0],[0,1]],[[1,1],[1,1]]],dtype=float)
    tensor=solve(tensor_subset(atoms[0]+atoms[1],atoms,k=2),steps=128)
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);m=GraphMemory(root/'m.db',b'a'*32,'benchmark')
        a=m.add('artifact','alpha catalyst shared bridge',{});b=m.add('artifact','beta bridge evidence',{});m.add('artifact','gamma temperature',{});m.link(a,'supports',b)
        architecture=synthesize(SynthesizedIndex(m),(Case('alpha catalyst',b),),(Case('alpha shared',b),),(Case('catalyst shared',b),),budget=24)
        x=('x',);y=('y',);proof=prove(Program(('add',('and',x,y),('xor',x,y))),Program(('or',x,y)))
        rng=random.Random(8);rows=[]
        for _ in range(36):
            mass,radius=rng.uniform(1,3),rng.uniform(1,3);rows.append(((mass,radius),mass/radius**2))
        data=Data(('mass','radius'),((0,1,0,0),(1,0,0,0)),(-2,1,0,0),tuple(rows[:18]),tuple(rows[18:27]),tuple(rows[27:]))
        discovery=discover(seed=42,budget=128)
        print(json.dumps({'logistics':logistic,'external_sampler':'exact classical enumeration, not QPU','tensor':tensor,'architecture':architecture,'proof':proof,'infinite_discovery':{k:len(discovery[k]) for k in ('proved','refuted','unknown')},'rational_law':rational_law(data),'transformer':demo(root/'live.db'),'tpu_contract':simulate_tpu()},indent=2,allow_nan=False))

if __name__=='__main__':main()
