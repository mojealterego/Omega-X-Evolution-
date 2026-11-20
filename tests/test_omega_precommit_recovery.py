"""Recover a real signed quorum after the leader disappears before publication."""
import copy
from omega_x_evolution.bft import Replica, leader, make_block, quorum, timeout_quorum
from omega_x_evolution.bft_transport import _dispatch
from omega_x_evolution.pacemaker import Pacemaker
from test_omega_final_gates import replicas


def prepare(tmp_path, *, terminal=False, count=3):
    nodes = replicas(tmp_path)
    state = next(iter(nodes.values())).inspect()['state']
    r = state['round_limit'] - 1 if terminal else 0
    for i in range(r):
        cert = timeout_quorum(state, [n.timeout_vote() for n in nodes.values()], i)
        for n in nodes.values():
            n.advance_certified(cert)
    dead = leader(state, r)
    live = sorted(set(nodes) - {dead})
    proposal = nodes[dead].propose(make_block(state, []), [n.status() for n in nodes.values()])
    block = proposal['body']['block']
    pv = quorum(state, [nodes[k].prevote(proposal) for k in live], phase='prevote')
    for k in live[:count]:
        nodes[k].precommit(block, pv)
    return nodes, state, r, dead, live, block


def test_terminal_quorum_survives_leader_crash_and_restart(tmp_path):
    nodes, state, r, dead, live, block = prepare(tmp_path, terminal=True)
    for k in live:
        n = nodes[k]
        nodes[k] = Replica(n.path, b'k'*32, n.g, n.identity)
    def call(peer, op, args):
        if peer == dead:
            raise OSError('leader vanished before publishing commit')
        return _dispatch(nodes[peer], op, args)
    clock = [0.]
    d = Pacemaker(nodes[live[0]], call, clock=lambda:clock[0], base_timeout=1.,max_timeout=1.)
    clock[0] = 2.
    assert d.tick()['status'] == 'recovered-commit'
    assert all(nodes[k].inspect()['log'][0]['block'] == block for k in live)
    assert nodes[dead].inspect()['state']['height'] == 1


def test_timeout_transition_preserves_unpublished_certificate(tmp_path):
    nodes, state, r, dead, live, block = prepare(tmp_path)
    cert = timeout_quorum(state, [nodes[k].timeout_vote() for k in live], r)
    for k in live:
        nodes[k].advance_certified(cert)
    def call(peer, op, args):
        if peer == dead:
            raise OSError('unreachable')
        return _dispatch(nodes[peer], op, args)
    assert Pacemaker(nodes[live[0]], call, clock=lambda:0.).tick()['status'] == 'recovered-commit'
    assert all(nodes[k].inspect()['log'][0]['block'] == block for k in live)


def test_insufficient_or_forged_precommit_never_recovers(tmp_path):
    nodes, state, r, dead, live, block = prepare(tmp_path)
    def call(peer, op, args):
        if peer == dead:
            raise OSError('unreachable')
        result = _dispatch(nodes[peer], op, args)
        if op == 'commit_evidence' and peer == live[-1]:
            result = copy.deepcopy(result)
            result['vote']['signature'] = '0'*128
        return result
    before = nodes[live[0]].inspect()
    assert Pacemaker(nodes[live[0]], call, clock=lambda:0.).tick()['status'] == 'waiting-leader'
    assert nodes[live[0]].inspect() == before
    assert all(nodes[k].inspect()['state']['height'] == 1 for k in live)
    def partition(peer, op, args):
        if peer in (dead, live[-1]):
            raise OSError('minority')
        return _dispatch(nodes[peer], op, args)
    assert Pacemaker(nodes[live[0]], partition, clock=lambda:0.).tick()['status'] == 'waiting-leader'
    assert all(nodes[k].inspect()['state']['height'] == 1 for k in live)


def test_recovery_over_authenticated_rpc_and_height_binding(tmp_path):
    import threading
    from contextlib import ExitStack
    from omega_x_evolution.bft_transport import serve
    from omega_x_evolution.mesh import Endpoint
    from omega_x_evolution.pacemaker import network_driver
    nodes, state, r, dead, live, block = prepare(tmp_path)
    with ExitStack() as stack:
        servers = {k:stack.enter_context(serve(nodes[k])) for k in live}
        threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers.values()]
        for t in threads:t.start()
        try:
            me = live[0]
            endpoints = tuple(Endpoint(k, '127.0.0.1', servers[k].server_port) for k in live if k != me)
            driver = network_driver(nodes[me], endpoints, networks=('127.0.0.0/8',),ports=(1024,65535),clock=lambda:0.)
            assert driver.tick()['status'] == 'recovered-commit'
            for k in live:
                assert nodes[k].inspect()['state']['height'] == 2
                assert nodes[k].inspect()['log'][0]['block'] == block
                assert nodes[k].commit_evidence(1) is None
                assert nodes[k].commit_evidence(2) is None
        finally:
            for s in servers.values():s.shutdown()
            for t in threads:t.join(5)


def test_wrong_round_and_voter_binding_cannot_recover(tmp_path):
    nodes, state, r, dead, live, block = prepare(tmp_path)
    original = nodes[live[0]].commit_evidence(1)
    for mutation in ('duplicate','wrong-round','wrong-campaign','wrong-qc'):
        def call(peer, op, args):
            if peer == dead:raise OSError('unreachable')
            result = _dispatch(nodes[peer], op, args)
            if op == 'commit_evidence' and peer == live[-1]:
                result = copy.deepcopy(result)
                if mutation == 'duplicate':return original
                if mutation == 'wrong-round':result['vote']['body']['round'] += 1
                if mutation == 'wrong-campaign':result['vote']['body']['campaign'] = '0'*64
                if mutation == 'wrong-qc':result['lock']['qc']['votes'][0]['signature'] = '0'*128
                result['vote']['signature'] = nodes[peer].identity.sign(result['vote']['body'])
            return result
        assert Pacemaker(nodes[live[0]], call, clock=lambda:0.).tick()['status'] == 'waiting-leader'
        assert all(nodes[k].inspect()['state']['height'] == 1 for k in live)
