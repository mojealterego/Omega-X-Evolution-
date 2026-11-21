"""Finite kinetic proofreading under independent and shared-cause noise.

The p**(m+1) law requires independent verification draws. Common-cause noise
violates that assumption. Costs are MODELLED checks, not physical joules.
No claim about the source-reported L9 Suite D accuracy or health is made.
"""
from __future__ import annotations
import math
import numpy as np


def _real(x,a,b):
    return type(x) in (int,float) and math.isfinite(x) and a<=x<=b


def _validate(p,rechecks,correlation):
    if not _real(p,0.,1.) or type(rechecks) is not int or not 0<=rechecks<=8 or not _real(correlation,0.,1.):
        raise ValueError('proofreading probability/check count')


def theoretical_error(p:float,rechecks:int,*,correlation:float=0.)->float:
    _validate(p,rechecks,correlation)
    checks=rechecks+1
    return float(correlation*p+(1-correlation)*(p**checks))


def simulate_error(seed:int,*,p:float,rechecks:int,correlation:float,trials:int)->dict:
    _validate(p,rechecks,correlation)
    if type(seed) is not int or not 0<=seed<2**32 or type(trials) is not int or not 1<=trials<=100_000:
        raise ValueError('seed/trials budget')
    rng=np.random.default_rng(seed)
    common=rng.random(trials)<correlation
    shared=rng.random(trials)<p
    independent=np.all(rng.random((trials,rechecks+1))<p,axis=1)
    false_accepted=np.where(common,shared,independent)
    err=int(np.count_nonzero(false_accepted))
    return {'seed':seed,'trials':trials,'false_accepts':err,
            'error_rate':err/trials,'expected_rate':theoretical_error(p,rechecks,correlation=correlation),
            'independent_checks':correlation==0.,'checks_per_trial':rechecks+1,
            'modeled_checks':trials*(rechecks+1),'physical_joules':'UNKNOWN'}


def drift_campaign(seeds:tuple[int,...])->dict:
    if (type(seeds) is not tuple or not 1<=len(seeds)<=30
        or len(set(seeds))!=len(seeds)
        or any(type(s) is not int or not 0<=s<2**32 for s in seeds)):
        raise ValueError('bounded drift seeds')
    runs=[]
    overall_ind=overall_corr=0
    for seed in seeds:
        ires=[];cres=[]
        for t,p in ((0,.1),(1,.25)):
            ind=simulate_error(seed+t*11093,p=p,rechecks=3,correlation=0.,trials=120)
            cor=simulate_error(seed+t*11093,p=p,rechecks=3,correlation=.75,trials=120)
            ires.append(ind['false_accepts']);cres.append(cor['false_accepts'])
        overall_ind+=sum(ires);overall_corr+=sum(cres)
        runs.append({'seed':seed,'independent_false_accepts':sum(ires),
                     'correlated_false_accepts':sum(cres),'model_checks':2*120*4})
    return {'number_of_seeds':len(seeds),'trials':len(seeds)*240,
            'independent_false_acceptance':overall_ind,
            'correlated_false_acceptance':overall_corr,
            'mean_recheck_cost':4.,'physical_joules':'UNKNOWN',
            'source_suite_d_accuracy_reproduced':False,
            'source_suite_d_health_reproduced':False,
            'runs':runs}
