"""Finite terminal-round progress with authenticated messages and virtual time."""
from test_omega_final_gates import replicas
from omega_x_evolution.bft import MAX_ROUND, leader, timeout_quorum
from omega_x_evolution.bft_transport import _dispatch
from omega_x_evolution.pacemaker import Pacemaker


def test_terminal_round_leader_retries_after_quorum_restored(tmp_path):
    nodes = replicas(tmp_path)
    members = sorted(nodes)
    state = nodes[members[0]].inspect()['state']
    for r in range(MAX_ROUND - 1):
        certificate = timeout_quorum(state, [node.timeout_vote() for node in nodes.values()], r)
        for node in nodes.values():
            node.advance_certified(certificate)
    coordinator = leader(state, MAX_ROUND - 1)
    live = {coordinator}
    clock = [0.0]

    def call(peer, op, args):
        if peer not in live:
            raise OSError('partition')
        return _dispatch(nodes[peer], op, args)

    driver = Pacemaker(nodes[coordinator], call, clock=lambda: clock[0], base_timeout=1., max_timeout=1.)
    clock[0] = 2.
    assert driver.tick()['status'] == 'round-limit'
    assert all(node.inspect()['state']['height'] == 1 for node in nodes.values())
    live.update(members[:2])
    assert driver.tick()['status'] == 'committed'
    assert all(nodes[key].inspect()['state']['height'] == 2 for key in live)
    logs = [nodes[key].inspect()['log'] for key in live]
    assert all(log == logs[0] for log in logs)
    # A peer outside the honest quorum catches up using a real certificate.
    laggard = next(key for key in members if key not in live)
    live.add(laggard)
    assert Pacemaker(nodes[laggard], call, clock=lambda: clock[0], base_timeout=1.).tick()['status'] == 'caught-up'
    assert nodes[laggard].inspect()['log'] == logs[0]


def test_synthesis_budget_can_be_extended_without_restarting(tmp_path):
    import pytest
    from omega_x_evolution.architecture import Case
    from omega_x_evolution.architecture_search import Search
    from omega_x_evolution.architecture_synthesis import SynthesizedIndex
    from omega_x_evolution.graph_memory import GraphMemory

    memory = GraphMemory(tmp_path/'graph.db', b'm'*32, 'a')
    a = memory.add('artifact', 'alpha bridge catalyst', {})
    b = memory.add('artifact', 'beta bridge evidence', {})
    memory.link(a, 'supports', b)
    idx = SynthesizedIndex(memory)
    splits = ((Case('alpha catalyst', b),), (Case('alpha bridge', b),), (Case('beta evidence', b),))
    path = tmp_path/'search.db'
    search = Search(path, b's'*32, idx, *splits, budget=8, create=True)
    assert search.step(16)['evaluations'] == 8
    before = search.inspect()
    search.extend_budget(32)
    search = Search(path, b's'*32, idx, *splits, budget=8)
    assert search.inspect()['seen'] == before['seen']
    assert search.step(32)['evaluations'] == 32
    direct = Search(tmp_path/'direct.db', b's'*32, idx, *splits, budget=32, create=True)
    direct.step(32)
    for field in ('best', 'queue', 'seen', 'recent', 'work'):
        assert search.inspect()[field] == direct.inspect()[field]
    with pytest.raises(ValueError):
        search.extend_budget(31)
    with pytest.raises(ValueError):
        search.extend_budget(8193)
    search.finalize()
    with pytest.raises(ValueError):
        search.extend_budget(64)
