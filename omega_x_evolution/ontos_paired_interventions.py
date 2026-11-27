"""Paired finite simulator intervention: recurrent belief vs fresh prior.

The same exogenous draws feed both arms. Only the recurrent belief state is
ablated; policy parameters, sensors and transition law are unchanged. Effects
are in this specified simulator, not independent evidence about real systems.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json

import numpy as np

from .ontos_observation_policy import ObservationPolicy, SensorFrame, SEEDS
from .ontos_testbed import _episode


def _arm(seed: int, horizon: int, recurrent: bool):
    policy=ObservationPolicy(); session=_episode(seed,horizon,paired=True)
    try:
        obs=next(session)
        for _ in range(horizon):
            if not recurrent: policy=ObservationPolicy()
            action=policy.decide(SensorFrame(obs.discrete,obs.continuous,obs.damage)).action
            try: obs=session.send(action)
            except StopIteration as stop: return stop.value
        raise RuntimeError('simulator failed to terminate')
    finally: session.close()


def _summary(rows):
    correct=sum(r.correct for r in rows); abstain=sum(r.action==5 for r in rows)
    raw=json.dumps([asdict(r) for r in rows],sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    return {'correct':correct,'abstentions':abstain,'wrong':len(rows)-correct-abstain,
            'harm':sum(r.harm for r in rows),'ood':sum(r.ood for r in rows),
            'trace_sha256':sha256(raw).hexdigest()}


def run_pair(seed: int, *, horizon: int=240) -> dict:
    if (type(seed) is not int or not 0<=seed<2**32 or type(horizon) is not int
            or not 1<=horizon<=240):
        raise ValueError('bounded paired episode')
    recurrent=_arm(seed,horizon,True); memoryless=_arm(seed,horizon,False)
    if any((a.ood,a.observation.lure,a.observation.tamper)!=(b.ood,b.observation.lure,b.observation.tamper)
           for a,b in zip(recurrent,memoryless)):
        raise RuntimeError('paired exogenous flags diverged')
    r,m=_summary(recurrent),_summary(memoryless)
    return {'seed':seed,'steps':horizon,'recurrent':r,'memoryless':m,
            'effect_correct':r['correct']-m['correct']}


def campaign(seeds: tuple[int,...]=SEEDS, *, horizon: int=240) -> dict:
    """Paired difference in unconditional accuracy, bootstrap by seed cluster.

    Fixed 4096 resamples with replacement, analysis seed 20261127. One seed
    is an episode cluster, not 240 independent observations. Percentile
    interval is descriptive for this finite model/seed sample, not a proven
    confidence guarantee or external causal generalization.
    """
    if (type(seeds) is not tuple or not 2<=len(seeds)<=64
            or any(type(s) is not int or not 0<=s<2**32 for s in seeds)
            or len(set(seeds))!=len(seeds) or type(horizon) is not int or not 1<=horizon<=240):
        raise ValueError('unique bounded paired campaign')
    pairs=tuple(run_pair(s,horizon=horizon) for s in seeds)
    effects=np.asarray([r['effect_correct'] for r in pairs],dtype=np.float64)/horizon
    rng=np.random.default_rng(20261127)
    indices=rng.integers(0,len(seeds),size=(4096,len(seeds)))
    samples=np.mean(effects[indices],axis=1)
    interval=tuple(map(float,np.quantile(samples,(.025,.975))))
    steps=len(seeds)*horizon
    return {'pairs':pairs,'steps_per_arm':steps,
            'paired_effect_accuracy':sum(r['effect_correct'] for r in pairs)/steps,
            'bootstrap_ci95':interval,'bootstrap_seed':20261127,'bootstrap_resamples':4096,
            'recurrent_accuracy':sum(r['recurrent']['correct'] for r in pairs)/steps,
            'memoryless_accuracy':sum(r['memoryless']['correct'] for r in pairs)/steps,
            'external_causal_effect_verified':False,'release_authorized':False}
