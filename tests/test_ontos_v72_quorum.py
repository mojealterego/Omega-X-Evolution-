"""Real Ed25519 and SQLite; deterministic delivery, public fixture keys."""
from dataclasses import replace
from itertools import combinations

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from omega_x_evolution.ontos_v72_checkpoint_note import Checkpoint, sign_note
from omega_x_evolution.ontos_v72_merkle import leaf_hash, merkle_root, consistency_proof, inclusion_proof
from omega_x_evolution.ontos_v72_witness import WitnessReceipt, _message
from omega_x_evolution.ontos_v72_quorum import (
    QuorumPolicy, QuorumWitness, QuorumCertificate, Vote, verify_quorum,
    quorum_challenge, verify_quorum_review,
)

LOG, *KEYS = [Ed25519PrivateKey.from_private_bytes(bytes([i])*32) for i in range(40,45)]
ORIGIN = 'omega/quorum'
PREFIX = (leaf_hash(b'genesis'),)
A = PREFIX + (leaf_hash(b'branch A'),)
B = PREFIX + (leaf_hash(b'branch B'),)
CH = b'c'*32


def pub(key):
    return key.public_key().public_bytes_raw()


def policy(environment='simulation'):
    return QuorumPolicy(environment, ORIGIN, ORIGIN, pub(LOG), 0, tuple(sorted(map(pub,KEYS))))


def cp(leaves):
    return Checkpoint(ORIGIN,len(leaves),merkle_root(leaves))


def note(leaves):
    return sign_note(cp(leaves),ORIGIN,LOG)


def cluster(path,p):
    return [QuorumWitness.initialize(path/f'w{i}.db',p,k,note(PREFIX)) for i,k in enumerate(KEYS)]


def deliver(nodes,indices,leaves,challenge=CH,revision=0,first_size=1):
    return tuple(v for i in indices if (v:=nodes[i].vote(note(leaves),consistency_proof(leaves,first_size),
        expected_revision=revision,challenge=challenge)) is not None)


def cert(leaves,votes,first_size=1):
    return QuorumCertificate(note(leaves),votes,consistency_proof(leaves,first_size))


def verify(p,leaves,votes,challenge=CH,previous=PREFIX):
    return verify_quorum(p,cp(previous),challenge,cert(leaves,votes,len(previous)))


def byzantine(p,leaves,challenge=CH):
    # A compromised witness controls its signing key and may equivocate.
    key=KEYS[0]; ch=quorum_challenge(p,challenge); n=note(leaves)
    r=WitnessReceipt(1,n,ch,key.sign(_message(p.member(pub(key)),1,n,ch)))
    return Vote(pub(key),r)


def test_one_unavailable_witness_and_recovery(tmp_path):
    p=policy(); nodes=cluster(tmp_path,p)
    votes=deliver(nodes,(0,1,2),A)
    assert verify(p,A,votes)==cp(A)
    reopened=QuorumWitness(tmp_path/'w3.db',p,KEYS[3])
    late=reopened.vote(note(A),consistency_proof(A,1),expected_revision=0,challenge=CH)
    assert late is not None
    assert verify(p,A,votes+(late,))==cp(A)


def test_two_two_partition_blocks_and_heals(tmp_path):
    p=policy(); nodes=cluster(tmp_path,p)
    left=deliver(nodes,(0,1),A)
    assert verify(p,A,left) is None
    right=deliver(nodes,(2,3),A)
    assert verify(p,A,right) is None
    assert verify(p,A,left+right)==cp(A)


def test_byzantine_equivocation_cannot_certify_two_forks(tmp_path):
    p=policy(); nodes=cluster(tmp_path,p)
    honest=deliver(nodes,(1,2),A)
    assert verify(p,A,(byzantine(p,A),)+honest)==cp(A)
    second=deliver(nodes,(1,2,3),B)
    assert len(second)==1
    assert verify(p,B,(byzantine(p,B),)+second) is None
    # Honest witnesses reject conflicting roots even with their correct current CAS.
    assert nodes[1].vote(note(B),(),expected_revision=1,challenge=CH) is None


def test_duplicate_keys_mixed_tips_forgery_and_replay_rejected(tmp_path):
    p=policy(); nodes=cluster(tmp_path,p); votes=deliver(nodes,(1,2,3),A)
    assert verify(p,A,votes)==cp(A)
    assert verify(p,A,(votes[0],)*3) is None
    assert verify(p,A,votes[:2]+(byzantine(p,B),)) is None
    bad=replace(votes[0],receipt=replace(votes[0].receipt,signature=bytes(64)))
    assert verify(p,A,(bad,)+votes[1:]) is None
    assert verify(p,A,votes,b'z'*32) is None
    assert verify(replace(p,epoch=1),A,votes) is None
    assert verify(replace(p,environment='operational'),A,votes) is None


def test_rollback_and_bad_consistency_rejected(tmp_path):
    p=policy(); nodes=cluster(tmp_path,p); votes=deliver(nodes,(0,1,2),A)
    assert verify_quorum(p,cp(A),CH,cert(A,votes,2))==cp(A)
    assert verify_quorum(p,cp(B),CH,cert(A,votes,2)) is None
    assert verify_quorum(p,cp(PREFIX),CH,replace(cert(A,votes),consistency=())) is None
    newer=A+(leaf_hash(b'next'),)
    assert verify_quorum(p,cp(newer),CH,cert(A,votes,2)) is None


def test_quorum_roster_validation():
    p=policy()
    with pytest.raises(ValueError): replace(p,witness_keys=(p.witness_keys[0],)*4)
    with pytest.raises(ValueError): replace(p,witness_keys=tuple(sorted((pub(LOG),)+p.witness_keys[:3])))
    with pytest.raises(ValueError): replace(p,epoch=True)
    with pytest.raises(ValueError): replace(p,witness_keys=p.witness_keys[:3])
    with pytest.raises(ValueError): replace(p,witness_keys=tuple(reversed(p.witness_keys)))


def test_operational_review_requires_tip_and_distinct_roles(tmp_path):
    p=policy('operational'); nodes=cluster(tmp_path,p)
    votes=deliver(nodes,(0,1,2),A); certificate=cert(A,votes)
    evaluator=pub(Ed25519PrivateKey.from_private_bytes(b'e'*32))
    assert verify_quorum_review(b'branch A',p,cp(PREFIX),CH,certificate,inclusion_proof(A,1),(evaluator,))
    assert not verify_quorum_review(b'genesis',p,cp(PREFIX),CH,certificate,inclusion_proof(A,0),(evaluator,))
    assert not verify_quorum_review(b'branch A',p,cp(PREFIX),CH,certificate,inclusion_proof(A,1),(pub(KEYS[0]),))
    assert not verify_quorum_review(b'branch A',replace(p,environment='simulation'),cp(PREFIX),CH,certificate,inclusion_proof(A,1),(evaluator,))


def test_exhaustive_quorum_intersection_for_one_byzantine():
    # All four possible quorums; any two share at least two members.
    subsets=tuple(map(set,combinations(range(4),3)))
    assert len(subsets)==4
    assert all(len(a&b)>=2 for a in subsets for b in subsets)
    assert all((a&b)-{fault} for a in subsets for b in subsets for fault in range(4))


def test_recovery_after_lost_reply_and_single_store_rollback(tmp_path):
    p=policy(); nodes=cluster(tmp_path,p)
    snapshot=(tmp_path/'w0.db').read_bytes()
    votes=deliver(nodes,(0,1,2),A)
    assert verify(p,A,votes)==cp(A)
    # Lost reply: reopen the honest witness and read its durable tip.
    recovered=QuorumWitness(tmp_path/'w1.db',p,KEYS[1])
    fresh=b'd'*32
    assert recovered.current(fresh).receipt.note==note(A)
    assert recovered.vote(note(A),(),expected_revision=0,challenge=fresh) is None
    assert recovered.vote(note(A),(),expected_revision=1,challenge=fresh) is not None
    # Restore precisely one witness database: this counts as a Byzantine fault.
    (tmp_path/'w0.db').write_bytes(snapshot)
    nodes[0]=QuorumWitness(tmp_path/'w0.db',p,KEYS[0])
    branch=B+(leaf_hash(b'divergent later entry'),)
    competing=deliver(nodes,(0,3),branch,fresh)
    assert len(competing)==2
    assert verify(p,branch,competing,fresh) is None
    assert recovered.vote(note(branch),consistency_proof(branch,2),expected_revision=1,challenge=fresh) is None


def test_partition_with_divergent_tips_fails_closed_after_heal(tmp_path):
    p=policy(); nodes=cluster(tmp_path,p)
    left=deliver(nodes,(0,1),A)
    right=deliver(nodes,(2,3),B)
    assert len(left)==len(right)==2
    assert verify(p,A,left+right) is None
    assert verify(p,B,left+right) is None
    # Healing the transport does not reconcile irreversible divergent votes.
    assert not deliver(nodes,(2,3),A,revision=1,first_size=2)
    assert not deliver(nodes,(0,1),B,revision=1,first_size=2)
    assert verify(p,A,left) is None and verify(p,B,right) is None
