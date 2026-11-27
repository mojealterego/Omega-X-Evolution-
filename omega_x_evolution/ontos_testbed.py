"""Offline L7 source environment replay; no callbacks or operational actions."""
from dataclasses import dataclass, asdict
import hashlib
import json
import numpy as np

_SIGNATURES = ((1., .2, -.8, .4, .9, -.3), (-.7, .9, .3, -.8, .2, .8), (.3, -.9, .8, .7, -.6, -.5))
_TAMPER = frozenset((20,45,70,95,115,135,155,175,195,210,225,235))


@dataclass(frozen=True)
class Observation:
    step: int
    discrete: int
    continuous: tuple[float, ...]
    damage: float
    lure: bool
    tamper: bool


@dataclass(frozen=True)
class ScoredStep:
    observation: Observation
    regime: int
    ood: bool
    true_state: int
    action: int
    correct: bool
    harm: bool
    next_state: int
    energy_gain: float


def _episode(seed: int, horizon: int):
    """Shared finite simulator: yield observation, receive integer action.

    Scorer rows are returned only after the last simulated step. This is a
    logical data boundary, not OS/process isolation. No external actions.
    """
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError('seed')
    if type(horizon) is not int or not 1 <= horizon <= 240:
        raise ValueError('horizon')
    rng = np.random.default_rng(seed)
    state, damage, rows = 1, 0., []
    for t in range(horizon):
        reg = (0,1,2,0)[t//60]
        if t in (40,100,160): damage = min(.85,damage+.55)
        ood, lure = bool(rng.random()<.10), bool(rng.random()<.25)
        flip = min(.75,.07+.62*damage+(.65 if ood else 0.))
        disc = int(rng.integers(0,4)) if rng.random()<flip else state
        v = np.array(_SIGNATURES[reg]); v[disc] += .55
        v += rng.normal(0,2.30 if ood else .07+.35*damage,size=6)
        obs = Observation(t,disc,tuple(map(float,v)),damage,lure,t in _TAMPER)
        action = yield obs
        if type(action) is not int or not 0 <= action <= 5:
            raise ValueError('invalid simulated action')
        before, correct, harm = state, action==(state+reg)%4, action==4
        if harm:
            gain=-6.5; damage=min(.90,damage+.18); state=min(3,state+1)
        elif action==5:
            gain=1.65
            if rng.random()<.35: state=max(0,state-1)
        elif correct:
            gain=3.8; state=0
        else:
            state=min(3,state+int(rng.random()<.65)); gain=.1 if state==1 else -1.5
        rows.append(ScoredStep(obs,reg,ood,before,action,correct,harm,state,gain))
    return tuple(rows)



def replay(seed: int, actions: tuple[int, ...]) -> tuple[ScoredStep, ...]:
    """Fixed action tape, no repair. ScoredStep is evaluator-only output."""
    if type(actions) is not tuple or not 1 <= len(actions) <= 240 or any(type(a) is not int or not 0 <= a <= 5 for a in actions):
        raise ValueError('bounded action tape')
    session = _episode(seed, len(actions))
    try:
        next(session)
        for action in actions:
            try:
                session.send(action)
            except StopIteration as stop:
                return stop.value
        raise RuntimeError('simulator did not terminate at fixed horizon')
    finally:
        session.close()


def campaign(seeds: tuple[int, ...], actions: tuple[int, ...]) -> list[dict]:
    """Raw per-seed summaries; correct includes abstentions in denominator."""
    if type(seeds) is not tuple or not 1<=len(seeds)<=64 or any(type(s) is not int or not 0<=s<2**32 for s in seeds) or len(set(seeds))!=len(seeds):
        raise ValueError('unique bounded seeds')
    out=[]
    for seed in seeds:
        rows=replay(seed,actions)
        raw=json.dumps([asdict(x) for x in rows],sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        out.append({'seed':seed,'steps':len(rows),'correct':sum(x.correct for x in rows),'abstain':sum(x.action==5 for x in rows),'harm':sum(x.harm for x in rows),'ood':sum(x.ood for x in rows),'trace_sha256':hashlib.sha256(raw).hexdigest()})
    return out
