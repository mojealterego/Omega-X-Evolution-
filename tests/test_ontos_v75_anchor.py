from dataclasses import replace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from omega_x_evolution.ontos_v72_checkpoint_note import Checkpoint, sign_note
from omega_x_evolution.ontos_v72_merkle import leaf_hash, merkle_root, consistency_proof, inclusion_proof
from omega_x_evolution.ontos_v72_receipts import ReceiptScope, sign_receipt
from omega_x_evolution.ontos_v72_witness import WitnessPolicy, WitnessStore
from omega_x_evolution.ontos_v75_anchor import AnchorTrust, AnchorEvidence, review_leaf, verify_review_anchor

LOG, WIT, EVAL = (Ed25519PrivateKey.from_private_bytes(bytes([i])*32) for i in (21,22,23))
ORIGIN = 'omega/l12-review'
COMMIT = 'a'*40
CHALLENGE = b'n'*32
GATES = tuple(f'GATE-0{i}' for i in range(1,9))


def inputs():
    trust = {g:(ReceiptScope('L12',g,COMMIT,'tenant','eval'),EVAL.public_key().public_bytes_raw()) for g in GATES}
    receipts = {g:sign_receipt({'result':'PASS'},scope,EVAL) for g,(scope,_) in trust.items()}
    return trust, receipts


def leaf(trust, receipts, **changes):
    args = dict(commit_sha=COMMIT,tenant='tenant',manifest_pin='b'*64,campaign_pin='c'*64,trust=trust,receipts=receipts)
    args.update(changes)
    return review_leaf(**args)


def fixture(tmp_path, environment='operational'):
    trust, receipts = inputs()
    data = leaf(trust,receipts)
    policy = WitnessPolicy(environment,ORIGIN,ORIGIN,LOG.public_key().public_bytes_raw(),WIT.public_key().public_bytes_raw())
    leaves = (leaf_hash(b'prior'),leaf_hash(data))
    def note(items):
        return sign_note(Checkpoint(ORIGIN,len(items),merkle_root(items)),ORIGIN,LOG)
    store = WitnessStore.initialize(tmp_path/'witness.sqlite',policy,WIT,note(leaves[:1]))
    previous = store.read(b'p'*32)
    assert store.advance(note(leaves),consistency_proof(leaves,1),expected_revision=0)=='ADVANCED'
    pinned = AnchorTrust(policy,previous,CHALLENGE)
    evidence = AnchorEvidence(store.read(CHALLENGE),consistency_proof(leaves,1),inclusion_proof(leaves,1))
    return pinned,evidence,data,trust


def verify(pinned,evidence,data,trust):
    return verify_review_anchor(data,pinned,evidence,tuple(key for _,key in trust.values()))


def test_real_witness_accepts_review_commitment(tmp_path):
    p,e,data,t = fixture(tmp_path)
    assert verify(p,e,data,t)


def test_tampered_leaf_proof_or_challenge_rejected(tmp_path):
    p,e,data,t = fixture(tmp_path)
    assert not verify(p,e,data+b'x',t)
    assert not verify(p,replace(e,inclusion=()),data,t)
    assert not verify(p,replace(e,consistency=()),data,t)
    assert not verify(replace(p,challenge=b'x'*32),e,data,t)
    assert not verify(p,replace(e,current=p.previous),data,t)


def test_simulation_and_key_role_collision_rejected(tmp_path):
    p,e,data,t = fixture(tmp_path,'simulation')
    assert not verify(p,e,data,t)
    assert not verify(replace(p,policy=replace(p.policy,environment='operational')),e,data,t)
    other = tmp_path/'operational'; other.mkdir(mode=0o700)
    p,e,data,t = fixture(other)
    assert not verify_review_anchor(data,p,e,(p.policy.log_key,))
    assert not verify_review_anchor(data,p,e,(p.policy.witness_key,))


def test_leaf_binds_every_gate_and_scope():
    import pytest
    t,r=inputs(); original=leaf(t,r)
    assert original==leaf(dict(reversed(tuple(t.items()))),dict(reversed(tuple(r.items()))))
    assert original!=leaf(t,r,manifest_pin='d'*64)
    assert original!=leaf(t,r,campaign_pin='e'*64)
    for g in GATES:
        changed=dict(r); changed[g]=sign_receipt({'result':'FAIL'},t[g][0],EVAL)
        assert original!=leaf(t,changed)
    with pytest.raises(ValueError): leaf(t,{g:v for g,v in r.items() if g!='GATE-08'})
    with pytest.raises(ValueError): leaf(t,r,commit_sha='d'*40)


def test_old_review_not_accepted_below_tip(tmp_path):
    p,e,data,t=fixture(tmp_path)
    store=WitnessStore(tmp_path/'witness.sqlite',p.policy,WIT)
    leaves=(leaf_hash(b'prior'),leaf_hash(data),leaf_hash(b'new review'))
    n=sign_note(Checkpoint(ORIGIN,3,merkle_root(leaves)),ORIGIN,LOG)
    assert store.advance(n,consistency_proof(leaves,2),expected_revision=1)=='ADVANCED'
    e2=AnchorEvidence(store.read(CHALLENGE),consistency_proof(leaves,1),inclusion_proof(leaves,1))
    assert not verify(p,e2,data,t)
