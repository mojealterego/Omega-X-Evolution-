"""Paired offline comparison of search strategies under equal proposal budgets."""
from __future__ import annotations
import argparse
import json
import math
import random
from statistics import mean
from .discovery import TASKS, STRATEGIES, discover, fixture
from .knowledge import seeds as validate_seeds


def compare(*, seeds=(81,82,83,84), budget=128, tasks=TASKS):
    seeds=validate_seeds(seeds); tasks=tuple(tasks)
    if not tasks or len(set(tasks))!=len(tasks) or any(t not in TASKS for t in tasks): raise ValueError('invalid benchmark tasks')
    if type(budget) is not int or not 1<=budget<=4096 or len(seeds)*len(tasks)*len(STRATEGIES)*budget>100_000:
        raise ValueError('benchmark proposal budget')
    runs=[]
    for task in tasks:
        for seed in seeds:
            data=fixture(task,seed=seed)
            for method in STRATEGIES:
                r=discover(data,seed=seed,budget=budget,strategy=method)
                runs.append({'task':task,**r})
    summaries=[]; comparisons=[]
    for method in STRATEGIES:
        group=[r for r in runs if r['strategy']==method]; errors=[r['holdout_rmse'] for r in group if r['holdout_rmse'] is not None]
        summaries.append({'strategy':method,'runs':len(group),'matches':sum(r['empirical_match'] for r in group),
                          'failures':len(group)-len(errors),'mean_holdout_rmse':mean(errors) if errors else None,
                          'valid_candidates':sum(r['valid_candidates'] for r in group),'attempts':sum(r['attempts'] for r in group)})
    index={(r['task'],r['seed'],r['strategy']):r for r in runs}
    for method in ('enumeration','random'):
        delta=[]; wins=ties=losses=missing=0
        for task in tasks:
            for seed in seeds:
                baseline=index[(task,seed,method)]['holdout_rmse']; challenger=index[(task,seed,'evolution')]['holdout_rmse']
                if baseline is None or challenger is None:
                    missing+=1; continue
                d=baseline-challenger; delta.append(d)
                if math.isclose(baseline,challenger,rel_tol=0,abs_tol=1e-12): ties+=1
                elif d>0: wins+=1
                else: losses+=1
        # descriptive paired mean, no inference from correlated synthetic tasks
        comparisons.append({'baseline':method,'challenger':'evolution','pairs':len(tasks)*len(seeds),'comparable_pairs':len(delta),
                            'wins':wins,'ties':ties,'losses':losses,'missing_pairs':missing,'mean_rmse_reduction':mean(delta) if delta else None})
    return {'schema':'omega-benchmark-v1','seeds':list(seeds),'tasks':list(tasks),'proposal_budget_per_run':budget,
            'runs':runs,'summaries':summaries,'comparisons':comparisons,'external_systems_compared':[]}


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--budget',type=int,default=128);p.add_argument('--seeds',nargs='+',type=int,default=[81,82,83,84]);p.add_argument('--tasks',nargs='+',choices=TASKS,default=TASKS)
    a=p.parse_args()
    try: result=compare(seeds=a.seeds,budget=a.budget,tasks=a.tasks)
    except ValueError as exc: p.error(str(exc))
    print(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__': main()
