"""Bounded evolution of proposal workflows under independent fixed promotion gates."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, replace, asdict
import json
import math
import random

from .engine import Config, Expression, run, simulated_proposal, apply_patch

OPERATORS = ('sample', 'refine', 'ratio', 'symmetry', 'simplify')


@dataclass(frozen=True)
class Workflow:
    operators: tuple[str, ...]
    attempts: int = 1

    def __post_init__(self):
        if type(self.operators) is not tuple or not 1 <= len(self.operators) <= 8 or any(x not in OPERATORS for x in self.operators):
            raise ValueError('unsupported workflow operator')
        if type(self.attempts) is not int or not 1 <= self.attempts <= 4:
            raise ValueError('attempt budget')

    def mutate(self, rng):
        ops=list(self.operators)
        action=rng.randrange(4)
        if action==0 and len(ops)<8: ops.insert(rng.randrange(len(ops)+1),rng.choice(OPERATORS))
        elif action==1 and len(ops)>1: ops.pop(rng.randrange(len(ops)))
        elif action==2: ops[rng.randrange(len(ops))]=rng.choice(OPERATORS)
        else: return Workflow(tuple(ops),rng.randint(1,4))
        return Workflow(tuple(ops),self.attempts)


def proposal_for(workflow):
    async def propose(role,prompt,seed):
        parent=json.loads(prompt)['parent']; rng=random.Random(seed)
        Expression(parent)
        candidate=parent
        for _ in range(workflow.attempts):
            for op in workflow.operators:
                if op=='sample':
                    patch=await simulated_proposal(role,json.dumps({'parent':candidate}),rng.randrange(2**32))
                    candidate=apply_patch(candidate,patch)
                elif op=='refine':
                    a=round(rng.uniform(.05,2),4)
                    candidate=f'({candidate})-{a}*abs(x-y)'
                elif op=='ratio':
                    e=round(rng.uniform(.008,.04),4)
                    candidate=f'-(x+y+(x+{e})/(y+{e})+(y+{e})/(x+{e}))'
                elif op=='symmetry':
                    swapped=candidate.translate(str.maketrans('xy','yx'))
                    candidate=f'(({candidate})+({swapped}))/2'
                elif op=='simplify':
                    from .superopt import optimize
                    candidate=optimize(candidate).source
                try: Expression(candidate)
                except ValueError: candidate=parent
        return f'<<<<<<< SEARCH\n{parent}\n=======\n{candidate}\n>>>>>>> REPLACE'
    return propose


def promotion(baseline, candidate, budget):
    if not baseline or len(baseline)!=len(candidate): return False
    if any(len(x)!=3 or not all(math.isfinite(v) for v in x) or not 0<=x[0]<=1 or not 0<=x[1]<=1 or not 0<=x[2]<=budget for x in (*baseline,*candidate)): return False
    return all(c[0]>=b[0] and c[1]>=b[1] and 0<=c[2]<=budget for b,c in zip(baseline,candidate)) and sum(c[0] for c in candidate)>sum(b[0] for b in baseline)+1e-12


async def evolve(cfg, *, train_seeds=(5,7), validation_seeds=(11,13), rounds=3, population=4, seed=42):
    train_seeds=tuple(train_seeds); validation_seeds=tuple(validation_seeds)
    if not train_seeds or not validation_seeds or len(train_seeds)>8 or len(validation_seeds)>8 or len(set(train_seeds+validation_seeds))!=len(train_seeds+validation_seeds) or any(type(s) is not int for s in train_seeds+validation_seeds):
        raise ValueError('disjoint unique train and validation seeds required')
    if type(rounds) is not int or type(population) is not int or not 1<=rounds<=10 or not 2<=population<=16:
        raise ValueError('meta search budget')
    # Independent promotion uses original engine, immutable score and per-seed gates.
    if cfg.generations*cfg.islands*cfg.workers*(rounds*population*len(train_seeds)+2*len(validation_seeds))>100_000:
        raise ValueError('total evaluation budget exceeded')
    async def measure(workflow,seeds):
        values=[]
        for s in seeds:
            output=await run(replace(cfg,seed=s),simulated_proposal if workflow is None else proposal_for(workflow))
            held=output['holdout_quality']
            values.append((output['champion_score'],held if held is not None else -1.,output['spent']))
        return values
    rng=random.Random(seed)
    candidates=[Workflow(('sample',)),Workflow(('ratio',))]
    while len(candidates)<population: candidates.append(Workflow((rng.choice(OPERATORS),rng.choice(OPERATORS))))
    cache={}; history=[]
    for iteration in range(rounds):
        for w in candidates:
            if w not in cache:
                values=await measure(w,train_seeds); cache[w]=values
                history.append({'round':iteration,'workflow':asdict(w),'training':values})
        # Do not select on validation seeds; train fitness fixed, tie-break deterministic.
        champion=max(cache,key=lambda w:(sum(x[0] for x in cache[w]),sum(x[1] for x in cache[w]),-sum(x[2] for x in cache[w]),-len(w.operators),-w.attempts,w.operators))
        candidates=[champion]+[champion.mutate(rng) for _ in range(population-1)]
    baseline=await measure(None,validation_seeds); candidate=await measure(champion,validation_seeds)
    passed=promotion(baseline,candidate,cfg.budget)
    return {'training_seeds':list(train_seeds),'validation_seeds':list(validation_seeds),'history':history,'evaluated_workflows':len(cache),'challenger':asdict(champion),'validation_baseline':baseline,'validation_challenger':candidate,'promoted':passed,'selected':asdict(champion) if passed else None,'total_run_budget_bound':(rounds*population*len(train_seeds)+2*len(validation_seeds))*cfg.budget}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rounds',type=int,default=3);p.add_argument('--population',type=int,default=4);p.add_argument('--seed',type=int,default=42);p.add_argument('--generations',type=int,default=3)
    a=p.parse_args();print(json.dumps(asyncio.run(evolve(Config(generations=a.generations),rounds=a.rounds,population=a.population,seed=a.seed)),indent=2,allow_nan=False))


if __name__=='__main__': main()
