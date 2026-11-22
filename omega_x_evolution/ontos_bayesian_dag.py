"""Finite Bayesian DAG d-separation and conservative selection-bias diagnostics.

This checks *graph separation*, not whether a causal graph is scientifically true.
It does not estimate probabilities, prove causal identification, authorize RSI,
or assert recovery from selected data without Markov/positivity assumptions.

Algorithm: ancestral moralization (Lauritzen et al.). Bounded, iterative O(V+E
+sum_v indegree(v)^2) followed by BFS. Graph capacity: 128 vertices,
2048 edges. No recursion, I/O, side effects or arbitrary code execution.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

_MAX_VERTICES = 128
_MAX_EDGES = 2048
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z", re.ASCII)


def _name(value: object) -> bool:
    return type(value) is str and _NAME.fullmatch(value) is not None


def _node_set(value: object, *, graph_nodes: frozenset[str], allow_empty: bool) -> frozenset[str]:
    if type(value) is str:
        if not _name(value):
            raise ValueError('invalid node')
        members = frozenset((value,))
    elif type(value) in (set, frozenset, tuple, list):
        try:
            members = frozenset(value)
        except TypeError as exc:
            raise ValueError('invalid node set') from exc
        if len(members) != len(value) or any(not _name(x) for x in members):
            raise ValueError('invalid or duplicated node set')
    else:
        raise ValueError('invalid node set')
    if (not allow_empty and not members) or not members <= graph_nodes:
        raise ValueError('empty or unknown node in query')
    return members


@dataclass(frozen=True, slots=True)
class SelectionAssessment:
    """Graph-only, non-authorizing diagnostic; assumptions unverified."""
    graph_digest: str
    outcome: str
    selection: str
    conditioning: tuple[str, ...]
    structurally_separated: bool
    status: str
    assumptions_attested: bool = False
    selection_positivity_attested: bool = False
    causal_effect_identified: bool = False
    release_authorized: bool = False


@dataclass(frozen=True, slots=True, init=False)
class BayesianDAG:
    """Immutable, canonical graph with parents indexed by variable name.

    Input maps each node to its *complete* tuple/list of direct parents.
    All nodes must appear as keys; a cycle or unknown parent is rejected.
    Empty parents are the root nodes. This is a structural graph, not a CPD.
    """
    parents: tuple[tuple[str, tuple[str, ...]], ...]
    digest: str

    def __init__(self, parents: dict[str, tuple[str, ...] | list[str]]) -> None:
        if type(parents) is not dict or not 1 <= len(parents) <= _MAX_VERTICES:
            raise ValueError('finite Bayesian DAG required')
        if any(not _name(name) for name in parents):
            raise ValueError('invalid graph variable name')
        norm: dict[str, tuple[str, ...]] = {}
        edge_count = 0
        for name, raw in parents.items():
            if type(raw) not in (tuple, list) or len(raw) > _MAX_VERTICES:
                raise ValueError('invalid parent sequence')
            if any(not _name(p) or p not in parents or p == name for p in raw):
                raise ValueError('self-parent, unknown or invalid parent')
            if len(set(raw)) != len(raw):
                raise ValueError('duplicate parent')
            norm[name] = tuple(sorted(raw))
            edge_count += len(raw)
            if edge_count > _MAX_EDGES:
                raise ValueError('edge budget exceeded')
        # Kahn topological traversal: deterministic, iterative, fail closed on cycles.
        children: dict[str, list[str]] = {name: [] for name in norm}
        indegree = {name: len(ps) for name, ps in norm.items()}
        for child, ps in norm.items():
            for p in ps:
                children[p].append(child)
        queue = [v for v in sorted(norm) if indegree[v] == 0]
        head = 0
        while head < len(queue):
            current = queue[head]
            head += 1
            for child in children[current]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if head != len(norm):
            raise ValueError('cycles are forbidden in Bayesian DAGs')
        canonical = tuple(sorted(norm.items()))
        digest = hashlib.sha256(json.dumps({'schema': 'omega-bayes-dag-v1',
                                            'parents': canonical},
                                            sort_keys=True, separators=(',', ':'),
                                            ensure_ascii=True).encode('ascii')).hexdigest()
        object.__setattr__(self, 'parents', canonical)
        object.__setattr__(self, 'digest', digest)

    def d_separated(self, x: object, y: object,
                    observed: object = None) -> bool:
        """Check X ⫫ Y | Z by ancestral moralization, for a *given* DAG.

        O(V + E + sum_v indegree(v)^2); worst case at most 128 nodes.
        Collider descendants are correctly activated by conditioning.
        Observed must not overlap tested endpoints.
        """
        parents = dict(self.parents)
        nodes = frozenset(parents)
        a = _node_set(x, graph_nodes=nodes, allow_empty=False)
        b = _node_set(y, graph_nodes=nodes, allow_empty=False)
        z = frozenset() if observed is None else _node_set(
            observed, graph_nodes=nodes, allow_empty=True)
        if a & b or a & z or b & z:
            raise ValueError('X, Y, Z must be pairwise disjoint')

        # All ancestors of X ∪ Y ∪ Z in the original directed acyclic graph.
        relevant = set(a | b | z)
        pending = list(relevant)
        while pending:
            for p in parents[pending.pop()]:
                if p not in relevant:
                    relevant.add(p)
                    pending.append(p)

        # Moralize the induced ancestral graph: undirect parent-child edges,
        # and marry any two parents of the same node.
        adj: dict[str, set[str]] = {v: set() for v in relevant}
        for v in relevant:
            ps = [p for p in parents[v] if p in relevant]
            for p in ps:
                adj[v].add(p)
                adj[p].add(v)
            for i, p in enumerate(ps):
                for q in ps[i + 1:]:
                    adj[p].add(q)
                    adj[q].add(p)

        # Delete the conditioned nodes. Connectivity means d-connection.
        seen = set(a)
        pending = list(a)
        while pending:
            current = pending.pop()
            if current in b:
                return False
            for next_node in adj[current]:
                if next_node not in z and next_node not in seen:
                    seen.add(next_node)
                    pending.append(next_node)
        return True

    def selection_criterion(self, outcome: str, selection: str,
                            given: object = None) -> SelectionAssessment:
        """Structural check of Y ⫫ S | X (NOT causal do-identification).

        If separation holds, the observational conditional P(Y|X) agrees
        with P(Y|X,S=1) under the local Markov property and selection
        positivity. Those external assumptions and the graph are not proven
        by this method. Failure does not imply global non-identifiability.
        """
        z = frozenset() if given is None else _node_set(
            given, graph_nodes=frozenset(dict(self.parents)), allow_empty=True)
        yes = self.d_separated(outcome, selection, z)
        return SelectionAssessment(
            graph_digest=self.digest, outcome=outcome, selection=selection,
            conditioning=tuple(sorted(z)), structurally_separated=yes,
            status='STRUCTURALLY_SEPARATED' if yes else 'CRITERION_NOT_ESTABLISHED',
        )
