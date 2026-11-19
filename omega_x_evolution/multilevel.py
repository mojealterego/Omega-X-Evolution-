"""Three-level coevolution: expressions, role workflows, and migrating teams."""
from __future__ import annotations
import argparse
import asyncio
from dataclasses import asdict, dataclass, replace
import json
import random
from .engine import BASELINE, Config, run, simulated_proposal
from .knowledge import collect, fit, seeds
from .meta import OPERATORS, Workflow, proposal_for, promotion


@dataclass(frozen=True)
class Team:
    fast: Workflow
    deep: Workflow

    def __post_init__(self):
        if not isinstance(self.fast,Workflow) or not isinstance(self.deep,Workflow): raise ValueError('invalid team workflow')

    def mutate(self,rng):
        return replace(self,fast=self.fast.mutate(rng)) if rng.randrange(2)==0 else replace(self,deep=self.deep.mutate(rng))

    def cross(self,other,rng):
        return Team(self.fast,other.deep) if rng.randrange(2)==0 else Team(other.fast,self.deep)

    def proposal(self):
        roles={'fast':proposal_for(self.fast,require_proof=True),'deep':proposal_for(self.deep,require_proof=True)}
        async def propose(role,prompt,seed):
            if role not in roles: raise ValueError('unknown role')
            return await roles[role](role,prompt,seed)
        return propose

    def signature(self):
        return (self.fast.operators,self.fast.attempts,self.deep.operators,self.deep.attempts)


async def evolve_teams(cfg:Config, *, train_seeds=(41,42), validation_seeds=(51,52), demes=3,population=4,rounds=3,seed=42):
    train_seeds=seeds(train_seeds); validation_seeds=seeds(validation_seeds)
    if set(train_seeds)&set(validation_seeds): raise ValueError('training and validation overlap')
    if any(type(v) is not int for v in (demes,population,rounds,seed)) or not 2<=demes<=8 or not 3<=population<=12 or not 1<=rounds<=12: raise ValueError('team search budget')
    run_bound=demes*population*rounds*len(train_seeds)+2*len(validation_seeds)
    teacher_bound=8*len(train_seeds)*len(OPERATORS)
    if cfg.generations*cfg.islands*cfg.workers*run_bound+teacher_bound>100_000: raise ValueError('total evaluation budget exceeded')
    rng=random.Random(seed)
    # Distilled priors seed one candidate per deme; validation never feeds fit.
    student=fit(await collect(train_seeds,per_seed=8))
    prior=Team(*(Workflow((OPERATORS[student.choose(role,BASELINE)],)) for role in ('fast','deep')))
    def random_workflow(): return Workflow(tuple(rng.choice(OPERATORS) for _ in range(rng.randint(1,3))),rng.randint(1,2))
    pools=[[prior]+[Team(random_workflow(),random_workflow()) for _ in range(population-1)] for _ in range(demes)]
    cache={}; history=[]; migrations=[]; runs=0
    async def measure(team,seed_set):
        nonlocal runs
        values=[]
        for s in seed_set:
            output=await run(replace(cfg,seed=s),simulated_proposal if team is None else team.proposal())
            runs+=1; held=output['holdout_quality']
            values.append((output['champion_score'],held if held is not None else -1.,output['spent']))
        return values
    def rank(team):
        v=cache[team]; return (sum(x[0] for x in v),sum(x[1] for x in v),-sum(x[2] for x in v),-len(team.fast.operators)-len(team.deep.operators),team.signature())
    for iteration in range(rounds):
        for i,pool in enumerate(pools):
            for t in pool:
                if t not in cache:
                    cache[t]=await measure(t,train_seeds)
                    history.append({'round':iteration,'deme':i,'team':asdict(t),'training':cache[t]})
        elites=[max(pool,key=rank) for pool in pools]
        if iteration+1<rounds:
            next_pools=[]
            for i,elite in enumerate(elites):
                donor=(i-1)%demes; migrant=elites[donor]
                migrations.append({'round':iteration,'from':donor,'to':i,'team':asdict(migrant)})
                new=[elite,migrant]
                while len(new)<population:
                    new.append(elite.cross(migrant,rng).mutate(rng))
                next_pools.append(new)
            pools=next_pools
    challenger=max(cache,key=rank)
    baseline=await measure(None,validation_seeds); candidate=await measure(challenger,validation_seeds)
    promoted=promotion(baseline,candidate,cfg.budget)
    return {'training_seeds':list(train_seeds),'validation_seeds':list(validation_seeds),'student_digest':student.training_digest,'prior':asdict(prior),'history':history,'migrations':migrations,'challenger':asdict(challenger),'validation_baseline':baseline,'validation_candidate':candidate,'promoted':promoted,'selected':asdict(challenger) if promoted else None,'runs':runs,'run_bound':run_bound,'teacher_evaluations':teacher_bound,'proposal_credit_bound':run_bound*cfg.budget}


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--rounds',type=int,default=3); p.add_argument('--demes',type=int,default=3); p.add_argument('--population',type=int,default=4); p.add_argument('--generations',type=int,default=3);p.add_argument('--seed',type=int,default=42);a=p.parse_args()
    print(json.dumps(asyncio.run(evolve_teams(Config(generations=a.generations),rounds=a.rounds,demes=a.demes,population=a.population,seed=a.seed)),indent=2,allow_nan=False))


if __name__=='__main__': main()
