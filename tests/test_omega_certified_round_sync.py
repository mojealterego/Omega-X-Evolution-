import copy
import pytest
from omega_x_evolution.bft import leader, make_block, quorum, timeout_quorum, Replica
from omega_x_evolution.bft_transport import _dispatch
from omega_x_evolution.pacemaker import Pacemaker
from test_omega_final_gates import replicas


def test_round_jump_preserves_prior_lock_and_signed_progress(tmp_path):
    nodes=replicas(tmp_path); members=sorted(nodes); lag=nodes[members[-1]]
    active=[nodes[k] for k in members[:-1]]; s=lag.inspect()['state']
    p=nodes[leader(s,0)].propose(make_block(s,[]), [n.status() for n in nodes.values()])
    block=p['body']['block']; pv=quorum(s,[n.prevote(p) for n in nodes.values()],phase='prevote')
    lag.precommit(block,pv); locked=lag.inspect()['locked']
    for r in range(10):
        cert=timeout_quorum(s,[n.timeout_vote() for n in active],r)
        for n in active:n.advance_certified(cert)
    # The laggard has no intermediate certificates and retains a genuine lock.
    def call(peer,op,args):return _dispatch(nodes[peer],op,args)
    driver=Pacemaker(lag,call,clock=lambda:0.)
    assert driver.tick()['status']=='advanced'
    assert lag.inspect()['round']==10
    assert lag.inspect()['locked']==locked
    reopened=Replica(lag.path,b'k'*32,lag.g,lag.identity)
    assert reopened.inspect()['round']==10 and reopened.inspect()['locked']==locked
    assert reopened.view(1,0)['latest_timeout_certificate']==cert
    # Lock-safe proposal after certified synchronization.
    coordinator=nodes[leader(s,10)]
    driver=Pacemaker(coordinator,call,clock=lambda:0.)
    assert driver.tick()['status']=='committed'
    assert all(n.inspect()['log'][0]['block']==block for n in nodes.values())


def test_round_jump_rejects_forgery_and_stale_cert(tmp_path):
    nodes=replicas(tmp_path); members=sorted(nodes); lag=nodes[members[-1]]
    active=[nodes[k] for k in members[:-1]]; s=lag.inspect()['state']
    for r in range(4):
        cert=timeout_quorum(s,[n.timeout_vote() for n in active],r)
        for n in active:n.advance_certified(cert)
    fake=copy.deepcopy(cert);fake['votes'][0]['signature']='0'*128
    before=lag.inspect()
    with pytest.raises(ValueError):lag.catch_up_round(fake)
    assert lag.inspect()==before
    lag.catch_up_round(cert)
    assert lag.inspect()['round']==4
    with pytest.raises(ValueError):lag.catch_up_round(cert)
