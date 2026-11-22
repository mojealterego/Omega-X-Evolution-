"""OMEGA-GRAPH-001..004 bounded DAG/cycle stress for existing GraphMemory.expand.

This is not a new Graph-of-Thought reasoning engine and has a max hop depth of 3.
"""
import random
import pytest

from omega_x_evolution.graph_memory import GraphMemory


def graph(n, *, fanout=4, cycles=False):
    nodes = {f'n{i:04d}': {'kind': 'artifact', 'text': f'node {i}', 'payload': {}}
             for i in range(n)}
    adj = {key: [] for key in nodes}
    for i in range(n):
        for k in range(1, fanout+1):
            j = i + k
            if j < n:
                adj[f'n{i:04d}'].append((f'n{j:04d}', 'derived', 'out'))
        if cycles and i:
            adj[f'n{i:04d}'].append((f'n{(i-1):04d}', 'refutes', 'in'))
    return nodes, adj


@pytest.mark.parametrize('size,fanout,hops', [(8,2,0),(64,4,1),(256,8,2),(512,16,3)])
def test_graph_001_stable_bounded_traversal_with_increasing_depth(size,fanout,hops):
    nodes, adj = graph(size,fanout=fanout)
    start=[('n0000',1.0)]
    a=GraphMemory.expand(nodes,adj,start,limit=32,hops=hops)
    b=GraphMemory.expand(nodes,adj,start,limit=32,hops=hops)
    assert a == b
    assert 1 <= len(a) <= 32
    assert len({x['id'] for x in a}) == len(a)
    assert all(len(x['path'])-1 <= hops for x in a)
    assert all(x['id'] == x['path'][-1] for x in a)


def test_graph_002_dense_dag_and_cycles_do_not_revisit():
    nodes,adj=graph(512,fanout=16,cycles=True)
    out=GraphMemory.expand(nodes,adj,[('n0000',1.0)],limit=32,hops=3)
    assert len(out)==32
    assert len(set(x['id'] for x in out))==32
    assert all(len(set(x['path']))==len(x['path']) for x in out)


def test_graph_003_duplicate_edges_and_shared_descendants_are_bounded():
    nodes,adj=graph(128,fanout=8,cycles=True)
    rng=random.Random(73)
    for _ in range(250):
        key=f'n{rng.randrange(128):04d}'
        adj[key].extend(adj[key][:3])
    out=GraphMemory.expand(nodes,adj,[('n0000',1.0)],limit=24,hops=3)
    assert len(out)<=24
    assert len({x['id'] for x in out})==len(out)


def test_graph_004_retrieval_rejects_deeper_than_current_contract():
    obj=object.__new__(GraphMemory)
    with pytest.raises(ValueError):obj.retrieve('node',hops=4)
    with pytest.raises(ValueError):obj.retrieve('node',hops=-1)
