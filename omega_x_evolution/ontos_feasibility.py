"""Exact finite-count feasibility audit of the selective reference controller.

OOD labels are used only after the simulator terminates. The diagnostic recall
floor is not a newly imposed acceptance requirement. COUNT_FEASIBLE is only a
counting bound, not proof that a controller can realize it. No policy change.
"""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from math import ceil

from .ontos_ablation import BASE, VALIDATION_SEEDS
from .ontos_observation_policy import ObservationPolicy, SensorFrame
from .ontos_paired_interventions import _summary
from .ontos_testbed import _episode

_MAX_STEPS = 1_000_000
_GUARDED = replace(BASE, floor=1e-6, hazard=.1)


def feasibility(steps: int, ood: int, *, target: Fraction, recall: Fraction) -> dict:
    """Tight upper bound assuming every non-abstaining action is correct.

    An OOD abstention cannot count as a correct action under this metric.
    The same integer accounting covers zero OOD events (recall is vacuous).
    """
    if (type(steps) is not int or not 1 <= steps <= _MAX_STEPS
            or type(ood) is not int or not 0 <= ood <= steps
            or any(type(x) is not Fraction or not 0 <= x <= 1
                   or x.denominator > _MAX_STEPS for x in (target, recall))):
        raise ValueError('bounded exact count and fraction contract')
    required_correct = ceil(target * steps)
    required_abstain = ceil(recall * ood)
    maximum = steps - required_abstain
    return {'steps': steps, 'ood': ood,
            'required_correct': required_correct,
            'required_ood_abstentions': required_abstain,
            'max_correct': maximum,
            'max_ood_abstentions_at_target': min(ood, steps-required_correct),
            'shortfall': max(0, required_correct-maximum),
            'status': 'COUNT_FEASIBLE' if maximum >= required_correct else 'INCOMPATIBLE',
            'target': _ratio(target.numerator, target.denominator),
            'diagnostic_recall_floor': _ratio(recall.numerator, recall.denominator),
            'release_authorized': False}


def _ratio(numerator: int, denominator: int) -> dict:
    return {'numerator': numerator, 'denominator': denominator}


def _run(seed, horizon, config):
    policy = ObservationPolicy(config)
    sim = _episode(seed, horizon, paired=True)
    try:
        observation = next(sim)
        for _ in range(horizon):
            action = policy.decide(SensorFrame(observation.discrete, observation.continuous,
                                               observation.damage)).action
            try:
                observation = sim.send(action)
            except StopIteration as stop:
                return stop.value
        raise RuntimeError('incomplete simulator trace')
    finally:
        sim.close()


def replay_audit(seeds: tuple[int, ...] = VALIDATION_SEEDS, *, horizon: int = 240) -> dict:
    """Re-execute frozen baseline and earlier guarded candidate on known seeds.

    This is retrospective validation accounting, not new blind validation.
    Both original veto thresholds are unchanged. No hidden labels enter policy.
    """
    if (type(seeds) is not tuple or not 1 <= len(seeds) <= 30
            or any(type(s) is not int or not 0 <= s < 2**32 for s in seeds)
            or len(set(seeds)) != len(seeds) or type(horizon) is not int
            or not 1 <= horizon <= 240):
        raise ValueError('bounded unique episode seeds and horizon')
    arms = {}
    for name, config in (('baseline', BASE), ('guarded', _GUARDED)):
        counts = {group: dict.fromkeys(('correct','abstain','wrong','harm'), 0)
                  for group in ('clean','ood')}
        traces = []
        for seed in seeds:
            rows = _run(seed, horizon, config)
            if len(rows) != horizon:
                raise RuntimeError('incomplete simulator trace')
            for row in rows:
                outcome = ('harm' if row.harm else 'abstain' if row.action == 5
                           else 'correct' if row.correct else 'wrong')
                counts['ood' if row.ood else 'clean'][outcome] += 1
            traces.append({'seed': seed, **_summary(rows)})
        clean, ood = counts['clean'], counts['ood']
        n = len(seeds)*horizon
        ood_total = sum(ood.values())
        abstain = clean['abstain'] + ood['abstain']
        arms[name] = {**counts, 'ood_total': ood_total, 'traces': traces,
                      'observed_accuracy_ceiling': _ratio(n-abstain,n),
                      'observed_ood_recall': _ratio(ood['abstain'],ood_total) if ood_total else None,
                      'clean_accuracy': _ratio(clean['correct'],sum(clean.values())) if sum(clean.values()) else None,
                      'unconditional_accuracy': _ratio(clean['correct']+ood['correct'],n),
                      'feasibility_at_99_percent': feasibility(n,ood_total,target=Fraction(91,100),recall=Fraction(99,100)),
                      'feasibility_at_observed_recall': feasibility(n,ood_total,target=Fraction(91,100),
                          recall=Fraction(ood['abstain'],ood_total) if ood_total else Fraction(0))}
    if arms['baseline']['ood_total'] != arms['guarded']['ood_total']:
        raise RuntimeError('paired OOD count mismatch')
    return {'schema': 'ontos-selective-feasibility-v1', 'seeds': list(seeds),
            'horizon': horizon, 'arms': arms, 'policy_changed': False,
            'source_reproduction_verified': False, 'release_authorized': False}
