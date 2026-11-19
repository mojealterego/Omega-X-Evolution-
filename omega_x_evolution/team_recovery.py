"""Crash-consistent variant of v9 team coevolution, preserving v9/v10 source bytes.

The same selection and migration policy is replayed from a signed snapshot of
pools, cached fitness, prior, RNG state and committed round history. The old
module remains available to keep historical v10 checkpoint contracts intact.
"""
from __future__ import annotations
import argparse
import asyncio
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import random
import sys

from .checkpoint import CheckpointStore,CheckpointError
from .engine import BASELINE,Config,run,simulated_proposal
from .knowledge import collect,fit,seeds
from .meta import OPERATORS,Workflow,promotion
from .multilevel import Team


def _wire(t): return json.loads(json.dumps(asdict(t)))
def _team(t): return Team(*(Workflow(tuple(t[r]['operators']),t[r]['attempts']) for r in ('fast','deep')))
def _tuples(v): return tuple(_tuples(x) for x in v) if isinstance(v,list) else v

def _contract(cfg,train,validation,demes,population,rounds,seed):
    root=Path(__file__).parent
    modules=('engine','checkpoint','workers','meta','knowledge','multilevel','formal','superopt','team_recovery')
    return {'schema':'omega-team-recovery-v1','config':asdict(cfg),'train':list(train),'validation':list(validation),'demes':demes,'population':population,'rounds':rounds,'seed':seed,'python':list(sys.version_info[:3]),'runtime':{n:hashlib.sha256((root/f'{n}.py').read_bytes()).hexdigest() for n in modules}}


async def evolve_durable(cfg:Config, *, train_seeds=(41,42),validation_seeds=(51,52),demes=3,population=4,rounds=3,seed=42,checkpoint:CheckpointStore,resume=False,stop_after=None):
    train_seeds=seeds(train_seeds);validation_seeds=seeds(validation_seeds)
    if set(train_seeds)&set(validation_seeds):raise ValueError('split overlap')
    if not isinstance(checkpoint,CheckpointStore) or type(resume) is not bool or any(type(v) is not int for v in (demes,population,rounds,seed)) or not 2<=demes<=8 or not 3<=population<=12 or not 1<=rounds<=12 or not 0<=seed<2**32:raise ValueError('team recovery limits')
    target=rounds if stop_after is None else stop_after
    if type(target) is not int or not 1<=target<=rounds:raise ValueError('stop target')
    run_bound=demes*population*rounds*len(train_seeds)+2*len(validation_seeds)
    teacher_bound=8*len(train_seeds)*len(OPERATORS)
    if cfg.generations*cfg.islands*cfg.workers*run_bound+teacher_bound>100_000:raise ValueError('total evaluation budget')
    contract=_contract(cfg,train_seeds,validation_seeds,demes,population,rounds,seed);rng=random.Random(seed)
    cache={};history=[];migrations=[];runs=0;completed=0
    if resume:
        completed,state=checkpoint.load()
        if state.get('contract')!=contract or not 0<=completed<=rounds+1 or completed>target+(1 if target==rounds else 0):raise CheckpointError('team checkpoint contract mismatch')
        if completed==rounds+1:
            if not isinstance(state.get('report'),dict):raise CheckpointError('missing final report')
            return state['report']
        try:
            prior=_team(state['prior']);student_digest=state['student_digest'];pools=[[_team(t) for t in p] for p in state['pools']]
            cache={_team(r['team']):r['training'] for r in state['cache']};history=state['history'];migrations=state['migrations'];runs=state['runs'];rng.setstate(_tuples(state['rng']))
            if len(pools)!=demes or any(len(p)!=population for p in pools) or type(runs) is not int or runs!=len(cache)*len(train_seeds) or runs>run_bound or len(history)!=len(cache):raise ValueError('state bounds')
        except (ValueError,TypeError,KeyError,IndexError) as exc:raise CheckpointError('invalid team checkpoint') from exc
    else:
        student=fit(await collect(train_seeds,per_seed=8));student_digest=student.training_digest
        prior=Team(*(Workflow((OPERATORS[student.choose(role,BASELINE)],)) for role in ('fast','deep')))
        def random_workflow(): return Workflow(tuple(rng.choice(OPERATORS) for _ in range(rng.randint(1,3))),rng.randint(1,2))
        pools=[[prior]+[Team(random_workflow(),random_workflow()) for _ in range(population-1)] for _ in range(demes)]
    def snapshot():
        return {'contract':contract,'prior':_wire(prior),'student_digest':student_digest,'pools':[[_wire(t) for t in p] for p in pools],'cache':[{'team':_wire(t),'training':v} for t,v in cache.items()],'history':history,'migrations':migrations,'runs':runs,'rng':rng.getstate()}
    if not resume:checkpoint.initialize(snapshot())
    async def measure(team,seed_set):
        nonlocal runs
        values=[]
        for s in seed_set:
            out=await run(replace(cfg,seed=s),simulated_proposal if team is None else team.proposal());runs+=1;held=out['holdout_quality']
            values.append([out['champion_score'],held if held is not None else -1.,out['spent']])
        return values
    def rank(team):
        v=cache[team];return (sum(x[0] for x in v),sum(x[1] for x in v),-sum(x[2] for x in v),-len(team.fast.operators)-len(team.deep.operators),team.signature())
    for iteration in range(completed,target):
        for i,pool in enumerate(pools):
            for t in pool:
                if t not in cache:
                    cache[t]=await measure(t,train_seeds)
                    history.append({'round':iteration,'deme':i,'team':_wire(t),'training':cache[t]})
        elites=[max(pool,key=rank) for pool in pools]
        if iteration+1<rounds:
            next_pools=[]
            for i,elite in enumerate(elites):
                donor=(i-1)%demes;migrant=elites[donor]
                migrations.append({'round':iteration,'from':donor,'to':i,'team':_wire(migrant)})
                new=[elite,migrant]
                while len(new)<population:new.append(elite.cross(migrant,rng).mutate(rng))
                next_pools.append(new)
            pools=next_pools
        checkpoint.save(iteration+1,snapshot())
    if target<rounds:return {'complete':False,'completed_rounds':target,'runs':runs,'run_bound':run_bound}
    challenger=max(cache,key=rank);baseline=await measure(None,validation_seeds);candidate=await measure(challenger,validation_seeds);promoted=promotion(baseline,candidate,cfg.budget)
    report={'training_seeds':list(train_seeds),'validation_seeds':list(validation_seeds),'student_digest':student_digest,'prior':_wire(prior),'history':history,'migrations':migrations,'challenger':_wire(challenger),'validation_baseline':baseline,'validation_candidate':candidate,'promoted':promoted,'selected':_wire(challenger) if promoted else None,'runs':runs,'run_bound':run_bound,'teacher_evaluations':teacher_bound,'proposal_credit_bound':run_bound*cfg.budget}
    checkpoint.save(rounds+1,{'contract':contract,'report':report});return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rounds',type=int,default=3);p.add_argument('--demes',type=int,default=3);p.add_argument('--population',type=int,default=4);p.add_argument('--generations',type=int,default=3);p.add_argument('--seed',type=int,default=42);p.add_argument('--checkpoint',type=Path,required=True);p.add_argument('--key-file',type=Path,required=True);p.add_argument('--resume',action='store_true');p.add_argument('--stop-after',type=int);a=p.parse_args()
    with a.key_file.open('rb') as f:key=f.read(4097)
    if not 32<=len(key)<=4096:p.error('invalid key')
    print(json.dumps(asyncio.run(evolve_durable(Config(generations=a.generations),rounds=a.rounds,demes=a.demes,population=a.population,seed=a.seed,checkpoint=CheckpointStore(a.checkpoint,key),resume=a.resume,stop_after=a.stop_after)),indent=2,allow_nan=False))


if __name__=='__main__':main()
