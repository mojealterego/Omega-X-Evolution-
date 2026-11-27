from dataclasses import replace
from fractions import Fraction as F
import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from omega_x_evolution.ontos_v51_skepticism import MemoryEvent
from omega_x_evolution.ontos_v51_sequential_memory import (
    ReviewPlan, SignedTrial, signing_payload, review_family,
)

A, B = 'a'*64, 'b'*64
KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
PUB = KEY.public_key().public_bytes_raw()


def plan(candidates=(A,), horizon=24):
    return ReviewPlan('tenant', candidates, PUB, horizon, F(1,20))


def trial(p, previous, n, outcome=True, candidate=A, **changes):
    ev = MemoryEvent('tenant',candidate,f'e{n}',f'g{n}',
                     hashlib.sha256(str(n).encode()).hexdigest(),outcome,0,1000,n)
    ev = replace(ev, **changes)
    payload = signing_payload(p.sha256, previous, n, ev)
    return SignedTrial(previous,n,ev,KEY.sign(payload))


def history(p, outcomes, candidate=A):
    chain=[]
    head=p.sha256
    for n,outcome in enumerate(outcomes,1):
        t=trial(p,head,n,outcome,candidate)
        chain.append(t)
        head=t.sha256(p.sha256)
    return tuple(chain)


def review(p, chain, **kw):
    return review_family(p, p.sha256, chain, **kw)


def test_threshold_is_family_adjusted_and_never_promotes():
    p=plan((A,B))
    chain=history(p,[True]*10)
    r=review(p,chain)
    assert r.candidates[0].wealth == F(3,2)**10
    assert r.candidates[0].status == 'REVIEW_THRESHOLD'
    assert r.candidates[1].status == 'PENDING'
    assert r.per_candidate_alpha == F(1,40)
    assert r.family_alpha == F(1,20)
    assert r.promotion_authorized is False
    assert r.null_verified is False
    assert r.retained_head_verified is False
    assert review(p,chain,expected_head=r.head).retained_head_verified


def test_four_hits_not_enough_and_failure_never_floored():
    p=plan()
    r=review(p,history(p,[True]*4+[False]*10))
    assert r.candidates[0].wealth == F(3,2)**4*F(1,2)**10
    assert r.candidates[0].status == 'PENDING'


def test_abstentions_are_neutral_but_consume_horizon():
    p=plan(horizon=3)
    r=review(p,history(p,[None,True,None]))
    assert r.candidates[0].wealth == F(3,2)
    assert r.candidates[0].count == 3
    assert r.candidates[0].status == 'EXHAUSTED'


@pytest.mark.parametrize('outcomes,horizon', [([True]*9,24),([False]*4,3)])
def test_no_trials_after_terminal_decision(outcomes,horizon):
    p=plan(horizon=horizon)
    with pytest.raises(ValueError):
        review(p,history(p,outcomes))


def test_valid_interleaved_family():
    p=plan((A,B),horizon=2)
    t1=trial(p,p.sha256,1,True,A)
    t2=trial(p,t1.sha256(p.sha256),2,False,B)
    t3=trial(p,t2.sha256(p.sha256),3,None,A)
    t4=trial(p,t3.sha256(p.sha256),4,True,B)
    r=review(p,(t1,t2,t3,t4))
    assert [x.wealth for x in r.candidates] == [F(3,2),F(3,4)]
    assert all(x.status=='EXHAUSTED' for x in r.candidates)


@pytest.mark.parametrize('field,value', [('tenant','other'),('candidate_sha256',B),('positive',False),('source_sha256','c'*64),('recorded_at',2)])
def test_signed_event_tampering(field,value):
    p=plan(); t=history(p,[True])[0]
    with pytest.raises(ValueError):
        review(p,(replace(t,event=replace(t.event,**{field:value})),))


@pytest.mark.parametrize('field,value', [('ident','e1'),('group','g1'),('source_sha256',hashlib.sha256(b'1').hexdigest()),('recorded_at',0)])
def test_duplicate_and_backdated_signed_evidence(field,value):
    p=plan(); t=history(p,[True])[0]
    t2=trial(p,t.sha256(p.sha256),2,**{field:value})
    with pytest.raises(ValueError):
        review(p,(t,t2))


def test_wrong_key_and_replay_rejected():
    p=plan(); t=history(p,[True])[0]
    other=Ed25519PrivateKey.from_private_bytes(b'\xff'*32)
    fake=replace(t,signature=other.sign(signing_payload(p.sha256,t.previous,t.sequence,t.event)))
    for chain in ((fake,),(t,t),history(p,[True,False])[1:]):
        with pytest.raises(ValueError):
            review(p,chain)


def test_plan_substitution_and_truncated_history():
    p=plan(); chain=history(p,[True,False]); r=review(p,chain)
    with pytest.raises(ValueError):
        review_family(replace(p,horizon=23),p.sha256,chain)
    with pytest.raises(ValueError):
        review(p,chain[:1],expected_head=r.head)


def test_signed_cross_tenant_and_unregistered_candidates():
    p=plan()
    for t in (trial(p,p.sha256,1,tenant='other'),trial(p,p.sha256,1,candidate=B)):
        with pytest.raises(ValueError):
            review(p,(t,))


@pytest.mark.parametrize('kwargs', [dict(candidates=(A,A)),dict(candidates=(B,A)),dict(candidates=()),dict(horizon=241),dict(horizon=True),dict(alpha=F(1,10)),dict(alpha=0.05),dict(evaluator_key=b'\x01'+b'\x00'*31)])
def test_invalid_plan(kwargs):
    args=dict(tenant='tenant',candidates=(A,),evaluator_key=PUB,horizon=24,alpha=F(1,20));args.update(kwargs)
    with pytest.raises(ValueError):
        ReviewPlan(**args)


def test_empty_family_is_quarantined():
    p=plan(); r=review(p,())
    assert r.head==p.sha256 and r.candidates[0].wealth==1
    assert not r.promotion_authorized and r.candidates[0].status=='PENDING'
