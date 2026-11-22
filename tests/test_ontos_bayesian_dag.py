"""OMEGA-CAUSAL-001..012: independent graph and statistical-claim boundary tests."""
import hashlib
import random
from collections import deque

import pytest

from omega_x_evolution.ontos_bayesian_dag import BayesianDAG, SelectionAssessment


def _oracle_dsep(parents: dict[str, tuple[str, ...]], x: str, y: str, observed: set[str]) -> bool:
    """Slow, independent active-trail enumerator for n<=7 (NOT production logic)."""
    undirected = {v: set() for v in parents}
    for v, ps in parents.items():
        for p in ps:
            undirected[p].add(v)
            undirected[v].add(p)
    activated = set(observed)
    q = list(observed)
    while q:
        for p in parents[q.pop()]:
            if p not in activated:
                activated.add(p)
                q.append(p)

    def trail_active(path):
        for a, b, c in zip(path, path[1:], path[2:]):
            collider = a in parents[b] and c in parents[b]
            if collider and b not in activated:
                return False
            if not collider and b in observed:
                return False
        return True

    paths = [(x,)]
    while paths:
        path = paths.pop()
        if path[-1] == y and trail_active(path):
            return False
        for other in undirected[path[-1]]:
            if other not in path:
                paths.append(path + (other,))
    return True


def test_causal_001_chain_blocks_conditionally():
    g = BayesianDAG({'X': (), 'M': ('X',), 'Y': ('M',)})
    assert not g.d_separated('X', 'Y')
    assert g.d_separated('X', 'Y', observed={'M'})


def test_causal_002_fork_common_parent():
    g = BayesianDAG({'X': ('C',), 'Y': ('C',), 'C': ()})
    assert not g.d_separated('X', 'Y')
    assert g.d_separated('X', 'Y', observed={'C'})


def test_causal_003_collider_and_descendant():
    g = BayesianDAG({'X': (), 'Y': (), 'C': ('X', 'Y'), 'D': ('C',), 'E': ()})
    assert g.d_separated('X', 'Y')
    assert not g.d_separated('X', 'Y', observed={'C'})
    assert not g.d_separated('X', 'Y', observed={'D'})
    assert g.d_separated('X', 'Y', observed={'E'})


def test_causal_004_two_independent_paths_both_need_blocking():
    g = BayesianDAG({'X': (), 'A': ('X',), 'B': ('X',), 'Y': ('A', 'B')})
    assert not g.d_separated('X', 'Y', observed={'A'})
    assert g.d_separated('X', 'Y', observed={'A', 'B'})


def test_causal_005_selection_structurally_recoverable_conditional_not_promoted():
    # S <- X -> Y : Y independent of S only after conditioning on X.
    g = BayesianDAG({'X': (), 'Y': ('X',), 'S': ('X',)})
    report = g.selection_criterion(outcome='Y', selection='S', given={'X'})
    assert isinstance(report, SelectionAssessment)
    assert report.status == 'STRUCTURALLY_SEPARATED'
    assert report.structurally_separated
    assert report.assumptions_attested is False
    assert report.selection_positivity_attested is False
    assert report.causal_effect_identified is False
    assert report.release_authorized is False
    assert not g.selection_criterion(outcome='Y', selection='S').structurally_separated


def test_causal_006_selection_failure_is_not_global_nonidentifiability():
    g = BayesianDAG({'Y': (), 'S': ('Y',), 'X': ()})
    report = g.selection_criterion('Y', 'S', given={'X'})
    assert report.status == 'CRITERION_NOT_ESTABLISHED'
    assert not report.structurally_separated
    assert report.release_authorized is False


@pytest.mark.parametrize('invalid', [
    {},
    {'A': ('A',)},
    {'A': ('B',), 'B': ('A',)},
    {'A': ('MISSING',)},
    {'A': ('B', 'B'), 'B': ()},
    {'A': ('B',), 'B': ('C',), 'C': ('A',)},
    {'A': [42]},
    {'A': ('',)},
    {'A': (), '__import__': ('A',)},
    {'A': (), 'a b': ('A',)},
    {'A': (1,)},
    {'A': 4},
    {1: ()},
])
def test_causal_007_bad_graph_rejected(invalid):
    with pytest.raises(ValueError):
        BayesianDAG(invalid)


def test_causal_008_query_budget_and_unknown_nodes_rejected():
    g = BayesianDAG({'A': (), 'B': ('A',), 'C': ()})
    bad_calls = [
        ('A', 'MISSING', None), ('A', 'A', None), ('A', 'B', {'B'}),
        ('A', 'B', {'A'}), (set(), 'B', None), (['A', 7], 'B', None),
        ('A', 'B', 'A B'), ('A', 'B', {'MISSING'}), (None, 'B', None),
        (['A', []], 'B', None), ('A', 'B', [[]]),
    ]
    for x, y, z in bad_calls:
        with pytest.raises(ValueError):
            g.d_separated(x, y, observed=z)


def test_causal_009_capacity_budgets_enforced():
    with pytest.raises(ValueError):
        BayesianDAG({f'N{i}': () for i in range(129)})
    with pytest.raises(ValueError):
        BayesianDAG({f'N{i}': tuple(f'N{j}' for j in range(i)) for i in range(100)})


def test_causal_010_random_dags_vs_independent_active_trail_oracle():
    rng = random.Random(62026)
    for _ in range(250):
        n = rng.randrange(2, 8)
        names = [f'N{i}' for i in range(n)]
        parents = {name: tuple(names[j] for j in range(i) if rng.random() < .38)
                   for i, name in enumerate(names)}
        g = BayesianDAG(parents)
        x, y = rng.sample(names, 2)
        observed = {name for name in names if name not in (x, y) and rng.random() < .45}
        assert g.d_separated(x, y, observed=observed) == _oracle_dsep(parents, x, y, observed)
        assert g.d_separated(y, x, observed=observed) == _oracle_dsep(parents, x, y, observed)


def test_causal_011_deterministic_digest_and_immutable_snapshot():
    g = BayesianDAG({'B': ('A',), 'A': (), 'C': ('B',)})
    h = BayesianDAG({'C': ('B',), 'A': (), 'B': ('A',)})
    assert g.digest == h.digest
    assert len(g.digest) == 64 and all(v in '0123456789abcdef' for v in g.digest)
    assert isinstance(g.parents, tuple)
    with pytest.raises((AttributeError, TypeError)):
        g.parents += ('X',)
    assert g.d_separated('A', 'C', {'B'})
    assert g.digest == h.digest


def test_causal_012_deep_chain_iterative_no_recursion_and_complete():
    g = BayesianDAG({f'N{i}': (() if i == 0 else (f'N{i-1}',)) for i in range(128)})
    assert not g.d_separated('N0', 'N127')
    assert g.d_separated('N0', 'N127', {'N63'})
    for _ in range(60):
        assert g.d_separated('N0', 'N127', {'N63'})
