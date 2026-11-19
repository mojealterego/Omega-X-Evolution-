"""Real signed replicas, virtual time; progress past the historical round cap."""
import pytest
from omega_x_evolution.bft import Genesis, Replica, MAX_ROUND, leader, timeout_quorum
from omega_x_evolution.bft_transport import _dispatch
from omega_x_evolution.federation import Identity
from omega_x_evolution.pacemaker import Pacemaker


def test_default_protocol_replaces_faulty_legacy_terminal_leader(tmp_path):
    ids = [Identity(bytes([i])*32) for i in range(1,5)]
    members = tuple(sorted(i.public for i in ids))
    g = Genesis('e'*64,members,members,1,16,2)
    nodes = {i.public:Replica(tmp_path/f'{n}.db',b'k'*32,g,i,create=True) for n,i in enumerate(ids)}
    s=nodes[members[0]].inspect()['state']
    faulty=leader(s,MAX_ROUND-1)
    honest=tuple(k for k in members if k!=faulty)
    # A long outage legitimately exhausted the historical 32-round horizon.
    for r in range(MAX_ROUND-1):
        qc=timeout_quorum(s,[nodes[k].timeout_vote() for k in honest],r)
        for k in honest:nodes[k].advance_certified(qc)
    def call(peer,op,args):
        if peer==faulty:raise OSError('Byzantine withholding')
        return _dispatch(nodes[peer],op,args)
    clock=[0.]
    drivers={k:Pacemaker(nodes[k],call,clock=lambda:clock[0],base_timeout=1.,max_timeout=1.) for k in honest}
    clock[0]=2.
    events=[]
    for _ in range(8):
        for k in honest:events.append(drivers[k].tick())
        if all(nodes[k].inspect()['state']['height']>=2 for k in honest):break
    print('fault schedule:',[(e['height'],e['round'],e['status']) for e in events])
    assert all(nodes[k].inspect()['state']['height']>=2 for k in honest)
    assert len({str(nodes[k].inspect()['log'][0]) for k in honest})==1
    assert any(e['round']>=MAX_ROUND and e['status']=='committed' for e in events)


def test_extended_round_history_is_bounded_and_restart_non_equivocation(tmp_path):
    ids=[Identity(bytes([i])*32) for i in range(1,5)]
    members=tuple(sorted(i.public for i in ids));g=Genesis('f'*64,members,members,1,8)
    nodes=[Replica(tmp_path/f'{n}.db',b'k'*32,g,i,create=True) for n,i in enumerate(ids)]
    s=nodes[0].inspect()['state']
    for r in range(MAX_ROUND+5):
        qc=timeout_quorum(s,[n.timeout_vote() for n in nodes[:3]],r)
        for n in nodes[:3]:n.advance_certified(qc)
    r=nodes[0].inspect()['round'];assert r==MAX_ROUND+5
    reopened=Replica(nodes[0].path,b'k'*32,g,nodes[0].identity)
    assert reopened.inspect()['round']==r
    assert len(reopened.inspect()['votes'])<=4 and len(reopened.inspect()['timeouts'])<=1
    assert reopened.view(1,0)['latest_timeout_certificate']==qc
    nodes[3].catch_up_round(qc)
    assert nodes[3].inspect()['round']==r
    with pytest.raises(ValueError):reopened.catch_up_round(qc)
