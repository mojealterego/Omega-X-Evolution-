"""Deterministic parity and operation accounting for the v27 classical reference."""
import math
import random
from itertools import combinations

import pytest
from omega_x_evolution.quantum import Problem, anneal


def problem(n, k):
    rng = random.Random(19 + n * 11 + k)
    return Problem(tuple(rng.randrange(1001) for _ in range(n)),
                   tuple(tuple(rng.randrange(101) for _ in range(16)) for _ in range(n)), k)


def reference(p, seed, steps):
    """Full energy recomputation, identical RNG and acceptance schedule."""
    rng = random.Random(seed)
    x = tuple(sorted(rng.sample(range(p.n), p.k)))
    e = p.energy(x)
    best = (e, x)
    work = 1
    if p.k < p.n:
        for s in range(steps):
            out = rng.choice(x)
            inc = rng.choice([i for i in range(p.n) if i not in x])
            y = tuple(sorted(set(x) - {out} | {inc}))
            v = p.energy(y)
            work += 1
            temp = 500 * (.001 ** (s / max(1, steps - 1)))
            if v <= e or rng.random() < math.exp((e - v) / temp):
                x, e = y, v
            best = min(best, (e, x))
    return best, work


@pytest.mark.parametrize('n,k', [(2,1),(5,2),(8,3),(12,4),(16,5),(24,6),(32,7),(32,8),(8,8)])
@pytest.mark.parametrize('seed,steps', [(0,1),(42,257),(2**32-1,512)])
def test_seeded_result_matches_full_reference(n, k, seed, steps):
    p = problem(n, k)
    best, work = reference(p, seed, steps)
    report = anneal(p, seed=seed, steps=steps)
    assert (report['energy'], tuple(report['indices'])) == best
    assert report['objective_evaluations'] == work
    assert p.energy(report['indices']) == report['energy']


@pytest.mark.parametrize('k', [1,2,3,4,5,6,7,8])
def test_pair_work_is_bounded_without_changing_quality(monkeypatch, k):
    p = problem(32, k)
    original = Problem.diversity
    calls = 0

    def count(self, i, j):
        nonlocal calls
        calls += 1
        return original(self, i, j)

    monkeypatch.setattr(Problem, 'diversity', count)
    steps = 128
    expected, work = reference(p, 42, steps)
    calls = 0
    result = anneal(p, seed=42, steps=steps)
    assert (result['energy'], tuple(result['indices'])) == expected
    assert result['objective_evaluations'] == work
    # Initial and final exact score, and cheapest exact method per proposal.
    pairs = math.comb(k, 2)
    assert calls <= 2 * pairs + steps * min(pairs, 2 * (k-1))


def test_all_tied_candidates_preserve_lexicographic_selection():
    p = Problem((0,) * 12, ((0,),) * 12, 8)
    expected, work = reference(p, 7, 200)
    result = anneal(p, seed=7, steps=200)
    assert (result['energy'], tuple(result['indices'])) == expected
    assert result['objective_evaluations'] == work
