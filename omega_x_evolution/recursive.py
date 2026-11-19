"""Bounded recursive policy improvement, with authenticated round commits.

Only typed proposal workflows can evolve; the evaluator, proof gate and resource
limits are immutable. The active policy is a research artifact, not deployment.
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

from .checkpoint import CheckpointError, CheckpointStore
from .engine import Config, run, simulated_proposal
from .formal import prove_rules, RULES
from .meta import Workflow, promotion
from .multilevel import Team


def _team(value):
    if value is None:
        return None
    return Team(*(Workflow(tuple(value[r]['operators']), value[r]['attempts']) for r in ('fast','deep')))


def _wire(team):
    return json.loads(json.dumps(asdict(team))) if team is not None else None


def _contract(cfg, rounds, population, seed):
    root = Path(__file__).parent
    modules = ('engine','checkpoint','workers','meta','multilevel','knowledge','superopt','formal','recursive')
    return {'schema':'omega-recursive-v1','config':asdict(cfg),'rounds':rounds,
            'population':population,'seed':seed,'python':list(sys.version_info[:3]),
            'runtime':{m:hashlib.sha256((root/f'{m}.py').read_bytes()).hexdigest() for m in modules}}


async def improve(cfg: Config, *, rounds=4, population=5, seed=1001,
                  checkpoint: CheckpointStore | None=None, resume=False, stop_after=None):
    if any(type(x) is not int for x in (rounds,population,seed)) or not 1<=rounds<=8 or not 2<=population<=12 or not 0<=seed<2**32:
        raise ValueError('recursive search budget')
    if resume and checkpoint is None: raise ValueError('resume requires checkpoint')
    target = rounds if stop_after is None else stop_after
    if type(target) is not int or not 1<=target<=rounds: raise ValueError('invalid stop target')
    # Population training runs plus the incumbent and selected challenger on two validation seeds.
    bound = rounds*(2*population+4)
    if cfg.generations*cfg.islands*cfg.workers*bound>100_000: raise ValueError('total evaluation budget exceeded')
    proofs=prove_rules()
    if set(proofs)!=set(RULES) or any(v!='unsat' for v in proofs.values()): raise RuntimeError('formal gate failed')
    contract=_contract(cfg,rounds,population,seed)
    contract['proofs']=proofs
    schedule=random.Random(seed).sample(range(2**32),4*rounds)
    history=[]; active=None; runs=0; completed=0
    if resume:
        completed,state=checkpoint.load()
        if state.get('contract')!=contract or not 0<=completed<=target: raise CheckpointError('recursive checkpoint contract mismatch')
        try:
            history=state['history']; active=_team(state['active']); runs=state['runs']
            if len(history)!=completed or type(runs) is not int or not 0<=runs<=bound: raise ValueError('invalid state')
            if completed and history[-1]['active']!=_wire(active): raise ValueError('invalid active policy')
        except (TypeError,KeyError,ValueError,IndexError) as exc: raise CheckpointError('invalid recursive checkpoint') from exc
    elif checkpoint is not None:
        checkpoint.initialize({'contract':contract,'history':history,'active':None,'runs':runs})

    async def measure(team, seed_set):
        nonlocal runs
        values=[]
        for s in seed_set:
            output=await run(replace(cfg,seed=s), simulated_proposal if team is None else team.proposal())
            runs+=1
            values.append([output['champion_score'],output['holdout_quality'] if output['holdout_quality'] is not None else -1.,output['spent']])
        return values

    for i in range(completed,target):
        train=schedule[4*i:4*i+2]; validation=schedule[4*i+2:4*i+4]
        rng=random.Random((seed<<8)+i)
        parent=active or Team(Workflow(('sample',)),Workflow(('sample',)))
        # Explicit task-specific prior is only used before the first promotion.
        candidates=[parent, Team(Workflow(('ratio',)),Workflow(('ratio',))) if active is None else parent.mutate(rng)]
        while len(candidates)<population:
            candidates.append(parent.mutate(rng))
        ranked=[]
        for team in dict.fromkeys(candidates):
            values=await measure(team,train)
            ranked.append((team,values))
        challenger, _=max(ranked,key=lambda pair:(sum(v[0] for v in pair[1]),sum(v[1] for v in pair[1]),-sum(v[2] for v in pair[1]),pair[0].signature()))
        before=await measure(active,validation); after=await measure(challenger,validation)
        passed=promotion(before,after,cfg.budget)
        incumbent=active
        if passed: active=challenger
        history.append({'round':i+1,'train_seeds':train,'validation_seeds':validation,
                        'incumbent':_wire(incumbent),'challenger':_wire(challenger),'active':_wire(active),
                        'training':[{'team':_wire(t),'metrics':v} for t,v in ranked],
                        'validation_incumbent':before,'validation_challenger':after,'promoted':passed})
        if checkpoint is not None:
            checkpoint.save(i+1,{'contract':contract,'history':history,'active':_wire(active),'runs':runs})
    return {'history':history,'active':_wire(active),'runs':runs,'run_bound':bound,
            'credit_bound':bound*cfg.budget,'rounds_completed':target,'rounds_planned':rounds}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name, default in [('rounds',4),('population',5),('seed',1001),('generations',2)]:
        p.add_argument('--'+name,type=int,default=default)
    p.add_argument('--checkpoint',type=Path); p.add_argument('--key-file',type=Path)
    p.add_argument('--resume',action='store_true'); p.add_argument('--stop-after',type=int)
    a=p.parse_args()
    if bool(a.checkpoint)!=bool(a.key_file) or (a.resume and not a.checkpoint): p.error('checkpoint/key-file pair required')
    try:
        store=None
        if a.checkpoint:
            with a.key_file.open('rb') as f: key=f.read(4097)
            if not 32<=len(key)<=4096: raise ValueError('invalid key length')
            store=CheckpointStore(a.checkpoint,key)
        result=asyncio.run(improve(Config(generations=a.generations),rounds=a.rounds,population=a.population,seed=a.seed,checkpoint=store,resume=a.resume,stop_after=a.stop_after))
    except (ValueError,CheckpointError,OSError,RuntimeError) as exc: p.error(str(exc))
    print(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__': main()
