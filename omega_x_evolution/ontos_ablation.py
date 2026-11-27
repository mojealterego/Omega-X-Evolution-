"""Finite paired policy ablation and development-only parameter selection.

All arms execute the same observation-only controller and actual simulator.
Seeds are shared within each comparison; validation seeds are disjoint, not
independently blinded. This is not the original L12 60-configuration campaign.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from hashlib import sha256

from .ontos_observation_policy import ObservationPolicy, PolicyConfig, SensorFrame, SEEDS
from .ontos_paired_interventions import _summary
from .ontos_testbed import _episode
from .ontos_v74_campaign import paired_statistics, holm_adjust
from .ontos_v72_jcs import canonical_json

BASE=PolicyConfig()
ARMS=(('recurrent',BASE),('memoryless',replace(BASE,recurrent=False)),
      ('no_ood_veto',replace(BASE,ood_limit=1.)),
      ('no_confidence_veto',replace(BASE,confidence_min=0.)),
      ('lower_floor',replace(BASE,floor=1e-6)),
      ('zero_hazard',replace(BASE,hazard=0.)))
GRID=tuple((f'ood{ood}_conf{conf}',replace(BASE,ood_limit=ood/100,confidence_min=conf/100))
           for ood in (50,90,100) for conf in (0,35,50))
GUARDED_GRID=tuple((f'floor{floor}_hazard{hazard}',replace(BASE,floor=floor,hazard=hazard))
                   for floor in (1e-6,1e-4,.004) for hazard in (.01,.03,.10))
DEV_SEEDS=SEEDS
VALIDATION_SEEDS=tuple(30000+73*i for i in range(30))


def _validate(seeds,horizon):
    if (type(seeds) is not tuple or not 2<=len(seeds)<=30
            or any(type(s) is not int or not 0<=s<2**32 for s in seeds)
            or len(set(seeds))!=len(seeds) or type(horizon) is not int or not 1<=horizon<=240):
        raise ValueError('bounded unique episode seeds and horizon')


def run_arm(seed: int, config: PolicyConfig, *, horizon: int=240) -> dict:
    policy=ObservationPolicy(config)
    session=_episode(seed,horizon,paired=True)
    try:
        obs=next(session)
        for _ in range(horizon):
            decision=policy.decide(SensorFrame(obs.discrete,obs.continuous,obs.damage))
            try: obs=session.send(decision.action)
            except StopIteration as stop:
                rows=stop.value
                flags=bytes((int(x.ood)<<2)|(int(x.observation.lure)<<1)|int(x.observation.tamper) for x in rows)
                return {**_summary(rows),'seed':seed,'steps':horizon,
                        'exogenous_flags_sha256':sha256(flags).hexdigest(),
                        'ood_abstentions':sum(x.ood and x.action==5 for x in rows)}
        raise RuntimeError('simulator failed to terminate')
    finally: session.close()


def _aggregate(rows):
    totals={k:sum(r[k] for r in rows) for k in ('steps','correct','abstentions','wrong','harm','ood','ood_abstentions')}
    executed=totals['steps']-totals['abstentions']
    return {**totals,'unconditional_accuracy':totals['correct']/totals['steps'],
            'conditional_accuracy':totals['correct']/executed if executed else None}


def _evaluate(arms,seeds,horizon):
    rows=[]; by_arm={name:[] for name,_ in arms}
    for seed in seeds:
        expected=None
        for name,config in arms:
            r=run_arm(seed,config,horizon=horizon)
            flags=r['exogenous_flags_sha256']
            if expected is not None and flags!=expected:
                raise RuntimeError('paired flags diverged')
            expected=flags
            rows.append({'arm':name,**r}); by_arm[name].append(r)
    return rows,by_arm,{name:_aggregate(rs) for name,rs in by_arm.items()}


def _protocol(arms,seeds,horizon):
    return sha256(canonical_json({'arms':[[n,asdict(c)] for n,c in arms],
        'seeds':list(seeds),'horizon':horizon,'metric':'correct/all-scheduled-steps',
        'analysis_seed':20261127,'simulator':'paired-v1'})).hexdigest()


def run_ablation(seeds: tuple[int,...]=DEV_SEEDS, *, horizon: int=240) -> dict:
    _validate(seeds,horizon)
    rows,by_arm,summary=_evaluate(ARMS,seeds,horizon)
    comparisons=[]
    for i,(name,_) in enumerate(ARMS[1:]):
        deltas=tuple(a['correct']-b['correct'] for a,b in zip(by_arm[name],by_arm['recurrent']))
        comparisons.append({'arm':name,'baseline':'recurrent',**paired_statistics(
            deltas,horizon,seed=20261127+i,family_size=len(ARMS)-1)})
    for c,p in zip(comparisons,holm_adjust(tuple(c['p_raw'] for c in comparisons))):
        c['p_holm']=p
    return {'schema':'ontos-ablation-v1','protocol_sha256':_protocol(ARMS,seeds,horizon),
            'rows':rows,'summary':summary,'comparisons':comparisons,
            'source_reproduction_verified':False,'release_authorized':False}


def _selection(grid,scope,dev,validation,horizon):
    _validate(dev,horizon); _validate(validation,horizon)
    if set(dev)&set(validation): raise ValueError('development and validation overlap')
    # Selection uses only development correctness, then fewer wrong decisions,
    # then name for deterministic tie resolution. Validation never changes winner.
    dev_rows,_,development=_evaluate(grid,dev,horizon)
    winner=max(development,key=lambda n:(development[n]['correct'],-development[n]['wrong'],n))
    config=dict(grid)[winner]
    arms=(('baseline',BASE),('candidate',config))
    val_rows,by_arm,summary=_evaluate(arms,validation,horizon)
    deltas=tuple(a['correct']-b['correct'] for a,b in zip(by_arm['candidate'],by_arm['baseline']))
    comparison=paired_statistics(deltas,horizon,seed=20261128,family_size=1)
    protocol={'scope':scope,'grid':_protocol(grid,dev,horizon),'validation_seeds':list(validation),
              'selection':'max correct, min wrong, max name','validation_analysis_seed':20261128}
    return {'schema':'ontos-policy-selection-v1','protocol_sha256':sha256(canonical_json(protocol)).hexdigest(),
            'selection_scope':scope,'policy_changed':False,'winner':winner,'config':asdict(config),'development':development,
            'development_rows':dev_rows,'validation_rows':val_rows,'validation':summary,
            'comparison':comparison,'target_91_percent_met':summary['candidate']['unconditional_accuracy']>=.91,
            'independent_holdout_verified':False,'source_reproduction_verified':False,
            'release_authorized':False}


def run_selection(dev: tuple[int,...]=DEV_SEEDS, validation: tuple[int,...]=VALIDATION_SEEDS,
                  *, horizon: int=240) -> dict:
    """Unconstrained accuracy diagnostic; disabling vetoes is not safety approval."""
    return _selection(GRID,'UNCONSTRAINED_ACCURACY',dev,validation,horizon)


def run_guarded_selection(dev: tuple[int,...]=DEV_SEEDS, validation: tuple[int,...]=VALIDATION_SEEDS,
                          *, horizon: int=240) -> dict:
    """Calibrate floor/hazard with both existing veto thresholds unchanged."""
    return _selection(GUARDED_GRID,'GUARDED_CALIBRATION',dev,validation,horizon)
