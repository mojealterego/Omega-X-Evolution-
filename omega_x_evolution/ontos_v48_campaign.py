"""Frozen, action-tape-only campaign for the ONTOS L7 offline reference.

The scorer is never queried to choose actions. Results are *not* a benchmark
of a live adaptive agent, JEPA, or causal generalization; there is no tuning.
"""
from dataclasses import asdict
import hashlib
import json
import random
from statistics import mean

from .ontos_testbed import replay

SEEDS = tuple(9100 + 29 * i for i in range(30))
ACTION_COUNT = 240
_POLICIES = ('cycle', 'constant', 'abstain', 'offset_cycle')
_TAPES = {
    'cycle': (0, 1, 2, 3) * 60,
    'constant': (0,) * ACTION_COUNT,
    'abstain': (5,) * ACTION_COUNT,
    'offset_cycle': (1, 2, 3, 0) * 60,
}


def _paired_interval(diffs: list[float], seed: int = 761) -> dict:
    """Paired percentile bootstrap over independent PRNG seeds; descriptive CI."""
    n = len(diffs)
    rng = random.Random(seed)
    means = sorted(mean(diffs[rng.randrange(n)] for _ in range(n)) for _ in range(512))
    middle = mean(diffs)
    return {'n': n, 'mean': middle,
            'lower': min(middle, means[12]), 'upper': max(middle, means[499]),
            'method': 'paired seed bootstrap 512 resamples; descriptive'}


def run_campaign(seeds: tuple[int, ...] = SEEDS) -> dict:
    if (
        type(seeds) is not tuple or not 1 <= len(seeds) <= 64
        or any(type(s) is not int or not 0 <= s < 2**32 for s in seeds)
        or len(set(seeds)) != len(seeds)
    ):
        raise ValueError('bounded unique seed contract')
    per_seed = []
    for seed in seeds:
        per_policy = {}
        for name in _POLICIES:
            # The tape is frozen before a scorer is called. No feedback loop.
            rows = replay(seed, _TAPES[name])
            canonical = json.dumps([asdict(row) for row in rows],
                                   sort_keys=True, separators=(',', ':'),
                                   allow_nan=False).encode('utf-8')
            accepted = sum(row.action != 5 for row in rows)
            correct = sum(row.correct for row in rows)
            per_policy[name] = {
                'steps': len(rows), 'correct': correct,
                'abstain': len(rows) - accepted,
                'harm': sum(row.harm for row in rows),
                'ood': sum(row.ood for row in rows),
                'coverage': accepted / len(rows),
                'unconditional_accuracy': correct / len(rows),
                'conditional_accuracy': correct / accepted if accepted else None,
                'trace_sha256': hashlib.sha256(canonical).hexdigest(),
            }
        per_seed.append({'seed': seed, 'per_policy': per_policy})
    def summarize(selected: list[dict]) -> dict:
        if not selected:
            return {}
        combined = {}
        for name in _POLICIES:
            rows = [r['per_policy'][name] for r in selected]
            total_steps = sum(r['steps'] for r in rows)
            accepted = sum(r['steps'] - r['abstain'] for r in rows)
            correct = sum(r['correct'] for r in rows)
            combined[name] = {
                'steps': total_steps,
                'correct': correct,
                'abstain': total_steps - accepted,
                'harm': sum(r['harm'] for r in rows),
                'ood': sum(r['ood'] for r in rows),
                'coverage': accepted / total_steps,
                'unconditional_accuracy': correct / total_steps,
                'conditional_accuracy': correct / accepted if accepted else None,
            }
        return combined
    summary = summarize(per_seed)
    dev, holdout = per_seed[:20], per_seed[20:]
    splits = {
        'dev': {'seed_count': len(dev), 'summary': summarize(dev)},
        'holdout': {'seed_count': len(holdout), 'summary': summarize(holdout)},
    }
    paired = {}
    for name in _POLICIES:
        if name != 'cycle':
            diffs = [row['per_policy'][name]['unconditional_accuracy']
                     - row['per_policy']['cycle']['unconditional_accuracy']
                     for row in per_seed]
            paired[name] = _paired_interval(diffs)
    return {
        'schema': 'ontos-offline-v48-reference-1',
        'number_of_seeds': len(seeds),
        'steps_per_seed': ACTION_COUNT,
        'policies': _POLICIES,
        'total_steps': len(seeds)*ACTION_COUNT*len(_POLICIES),
        # Precommitted first 20/remaining split. No fitting takes place.
        'dev_size': min(20, len(seeds)),
        'holdout_size': max(0, len(seeds) - 20),
        'observational_only': True,
        'summary': summary,
        'splits': splits,
        'paired_differences': paired,
        'per_seed': per_seed,
    }
