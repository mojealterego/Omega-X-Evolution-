"""Bounded, observation-only Bayesian policy for the existing L7 simulator.

Fixed known model signatures and transition/observation laws are explicit
priors, not learned or held-out. No access to the actual regime, OOD label,
clock, reward or evaluator state. This is not full Active Inference or a
reproduction of the monograph v2. No operational actions or memory writes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math

from .ontos_testbed import ScoredStep, _episode
from .ontos_v50_belief import BeliefFilter

_SIGNATURE_PRIORS = ((1., .2, -.8, .4, .9, -.3), (-.7, .9, .3, -.8, .2, .8), (.3, -.9, .8, .7, -.6, -.5))
_REGIME_HAZARD = .03
_FLOOR = .004
SEEDS = tuple(9100+29*i for i in range(30))


def _real(value: object, lo: float, hi: float) -> bool:
    return type(value) in (int,float) and lo <= value <= hi and math.isfinite(value)


@dataclass(frozen=True, slots=True)
class SensorFrame:
    discrete: int
    continuous: tuple[float, ...]
    damage: float

    def __post_init__(self):
        if (type(self.discrete) is not int or not 0 <= self.discrete < 4
                or type(self.continuous) is not tuple or len(self.continuous)!=6
                or any(not _real(x,-1e6,1e6) for x in self.continuous)
                or not _real(self.damage,0,.9)):
            raise ValueError('invalid bounded sensory frame')


@dataclass(frozen=True, slots=True)
class Decision:
    action: int
    posterior: tuple[float, ...]
    ood_probability: float
    predicted_success: float


def _predict(posterior: tuple[float, ...], action: int) -> tuple[float, ...]:
    out = [0.]*12
    for r in range(3):
        for s in range(4):
            if action == 5:
                transitions = ((s,.65),(max(0,s-1),.35))
            elif action == (s+r)%4:
                transitions = ((0,1.),)
            else:
                transitions = ((s,.35),(min(3,s+1),.65))
            for ns, weight in transitions:
                for nr in range(3):
                    shift = (1-_REGIME_HAZARD) if nr==r else _REGIME_HAZARD/2
                    out[nr*4+ns] += posterior[r*4+s]*weight*shift
    total=math.fsum(out)
    return tuple(x/total for x in out)


class ObservationPolicy:
    """12-state joint Bayesian filter, bounded to 240 decisions per episode."""
    def __init__(self):
        self._prior=(1/12,)*12
        self._count=0
        self._filter=BeliefFilter(prior_mix=0.,floor=_FLOOR)

    def decide(self, frame: SensorFrame) -> Decision:
        if type(frame) is not SensorFrame or self._count>=240:
            raise ValueError('sensor type or decision horizon')
        frame.__post_init__()
        d, v, damage = frame.discrete, frame.continuous, frame.damage
        # Relative log densities, using the known generative mixture, never
        # the environment's sampled OOD bit. The common Gaussian constant
        # cancels. The discrete likelihood includes uniform flip-to-self.
        logs=[]
        for r, signature in enumerate(_SIGNATURE_PRIORS):
            sq=math.fsum((x-y-(.55 if j==d else 0.))**2
                         for j,(x,y) in enumerate(zip(v,signature)))
            for s in range(4):
                pair=[]
                for contamination, sigma, weight in ((False,.07+.35*damage,.9),(True,2.3,.1)):
                    flip=min(.75,.07+.62*damage+(.65 if contamination else 0.))
                    discrete=flip/4+(1-flip if s==d else 0.)
                    pair.append(math.log(weight*discrete)-6*math.log(sigma)-sq/(2*sigma*sigma))
                logs.append(tuple(pair))
        peak=max(max(pair) for pair in logs)
        scaled=tuple(tuple(math.exp(x-peak) for x in pair) for pair in logs)
        likelihood=tuple(math.fsum(pair) for pair in scaled)
        norm=max(likelihood)
        likelihood=tuple(x/norm for x in likelihood)
        denominator=math.fsum(p*math.fsum(pair) for p,pair in zip(self._prior,scaled))
        ood=math.fsum(p*pair[1] for p,pair in zip(self._prior,scaled))/denominator
        posterior=self._filter.update(self._prior,likelihood).posterior
        scores=tuple(math.fsum(posterior[r*4+s] for r in range(3) for s in range(4) if (r+s)%4==a) for a in range(4))
        best=max(range(4),key=scores.__getitem__)
        action=5 if ood>.5 or scores[best]<.5 else best
        self._prior=_predict(posterior,action)
        self._count+=1
        return Decision(action,posterior,ood,scores[best])


def run_observation_episode(seed: int, *, horizon: int = 240) -> tuple[ScoredStep, ...]:
    """One fixed controller, no caller callback; scorer is returned at EOF."""
    policy=ObservationPolicy()
    session=_episode(seed,horizon)
    try:
        obs=next(session)
        for _ in range(horizon):
            decision=policy.decide(SensorFrame(obs.discrete,obs.continuous,obs.damage))
            try:
                obs=session.send(decision.action)
            except StopIteration as stop:
                return stop.value
        raise RuntimeError('simulator did not terminate at fixed horizon')
    finally:
        session.close()


def run_campaign(seeds: tuple[int, ...] = SEEDS) -> dict:
    """All scheduled steps, unconditional denominator, no invented survival."""
    if (type(seeds) is not tuple or not 1<=len(seeds)<=30
            or any(type(s) is not int or not 0<=s<2**32 for s in seeds)
            or len(set(seeds))!=len(seeds)):
        raise ValueError('unique bounded campaign seeds')
    per_seed=[]
    for seed in seeds:
        rows=run_observation_episode(seed)
        raw=json.dumps([asdict(x) for x in rows],sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        correct=sum(x.correct for x in rows)
        abstentions=sum(x.action==5 for x in rows)
        per_seed.append({'seed':seed,'steps':len(rows),'correct':correct,
                         'abstentions':abstentions,'wrong':len(rows)-correct-abstentions,
                         'harm':sum(x.harm for x in rows),
                         'ood':sum(x.ood for x in rows),
                         'ood_abstentions':sum(x.ood and x.action==5 for x in rows),
                         'clean_abstentions':sum(not x.ood and x.action==5 for x in rows),
                         'trace_sha256':hashlib.sha256(raw).hexdigest()})
    summary={key:sum(row[key] for row in per_seed) for key in ('steps','correct','abstentions','wrong','harm','ood','ood_abstentions','clean_abstentions')}
    executed=summary['steps']-summary['abstentions']
    return {**summary,'coverage':executed/summary['steps'],
            'unconditional_accuracy':summary['correct']/summary['steps'],
            'conditional_accuracy':summary['correct']/executed if executed else None,
            'per_seed':per_seed,'release_authorized':False,'process_isolation_verified':False,
            'source_v2_reproduced':False,'survival_measured':False}
