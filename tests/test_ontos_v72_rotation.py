"""Exercise real SQLite witness handoff; deterministic test keys only."""
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from omega_x_evolution.ontos_v72_checkpoint_note import Checkpoint, sign_note
from omega_x_evolution.ontos_v72_merkle import leaf_hash, merkle_root, consistency_proof
from omega_x_evolution.ontos_v72_witness import WitnessPolicy, WitnessStore, verify_witness
from omega_x_evolution.ontos_v72_rotation import EpochPin, rotation_bytes, rotate_epoch, advance_pin

KEYS = tuple(Ed25519PrivateKey.from_private_bytes(bytes([i])*32) for i in range(1,8))
ROOT, LOG, WIT, NEW_LOG, NEW_WIT, OTHER_LOG, OTHER_WIT = KEYS
ORIGIN = 'omega/rotation'
LEAVES = tuple(leaf_hash(str(i).encode()) for i in range(4))
CHALLENGE = b'b'*32


def pub(key):
    return key.public_key().public_bytes_raw()


def policy(log=LOG,wit=WIT,*,environment='simulation'):
    return WitnessPolicy(environment,ORIGIN,ORIGIN,pub(log),pub(wit))


def note(leaves,log):
    return sign_note(Checkpoint(ORIGIN,len(leaves),merkle_root(leaves)),ORIGIN,log)


@pytest.fixture
def handoff(tmp_path):
    old = WitnessStore.initialize(tmp_path/'old.db',policy(),WIT,note(LEAVES[:1],LOG))
    pin = EpochPin(0,policy(),pub(ROOT),old.read(b'a'*32),())
    assert old.advance(note(LEAVES[:2],LOG),consistency_proof(LEAVES[:2],1),expected_revision=0)=='ADVANCED'
    p = policy(NEW_LOG,NEW_WIT)
    new = WitnessStore.initialize(tmp_path/'new.db',p,NEW_WIT,note(LEAVES[:2],NEW_LOG))
    return pin, p, old.read(CHALLENGE), new.read(CHALLENGE), consistency_proof(LEAVES[:2],1), new


def cert(pin,p,old,new,challenge=CHALLENGE):
    return ROOT.sign(rotation_bytes(pin,p,old,new,challenge))


def rotate(pin,p,old,new,proof,signature=None,challenge=CHALLENGE):
    if signature is None:
        signature = cert(pin,p,old,new,challenge)
    return rotate_epoch(pin,p,old,new,proof,challenge=challenge,authority_signature=signature)


def test_real_rotation_and_continued_merkle_history(handoff,tmp_path):
    pin,p,old,new,proof,store = handoff
    successor = rotate(pin,p,old,new,proof)
    assert successor is not None and successor.epoch==1 and successor.policy==p
    assert successor.receipt==new and set(successor.retired_keys)=={pub(LOG),pub(WIT)}
    assert not verify_witness(old,p,CHALLENGE)
    reopened = WitnessStore(tmp_path/'new.db',p,NEW_WIT)
    assert reopened.advance(note(LEAVES,NEW_LOG),consistency_proof(LEAVES,2),expected_revision=0)=='ADVANCED'
    next_pin=advance_pin(successor,reopened.read(b'c'*32),consistency_proof(LEAVES,2),challenge=b'c'*32)
    assert next_pin is not None and next_pin.epoch==1 and next_pin.receipt.revision==1
    assert advance_pin(next_pin,new,(),challenge=CHALLENGE) is None
    assert advance_pin(successor,new,(),challenge=CHALLENGE) is None


def test_no_authority_no_rotation_and_no_replay(handoff):
    pin,p,old,new,proof,_ = handoff
    signature=cert(pin,p,old,new)
    assert rotate(pin,p,old,new,proof,bytes(64)) is None
    assert rotate(pin,p,old,new,proof,NEW_WIT.sign(rotation_bytes(pin,p,old,new,CHALLENGE))) is None
    successor=rotate(pin,p,old,new,proof,signature)
    assert successor is not None
    assert rotate(successor,p,old,new,proof,signature) is None
    assert rotate(pin,p,old,new,(),signature) is None
    assert rotate(pin,p,old,new,proof,signature,b'z'*32) is None
    assert rotate(pin,p,old,replace(new,revision=1),proof,signature) is None


def test_authority_signature_cannot_override_fork_or_rollback(handoff,tmp_path):
    pin,p,old,new,proof,_ = handoff
    for i,leaves in enumerate(((leaf_hash(b'fork'),LEAVES[1]), LEAVES[:1])):
        other=WitnessStore.initialize(tmp_path/f'fork-{i}.db',p,NEW_WIT,note(leaves,NEW_LOG))
        assert rotate(pin,p,old,other.read(CHALLENGE),proof) is None


def test_reject_role_swap_retired_key_and_simulation_to_operational(handoff,tmp_path):
    pin,p,old,new,proof,_=handoff
    swapped=policy(WIT,LOG)
    swap=WitnessStore.initialize(tmp_path/'swap.db',swapped,LOG,note(LEAVES[:2],WIT))
    assert rotate(pin,swapped,old,swap.read(CHALLENGE),proof) is None
    operational=policy(NEW_LOG,NEW_WIT,environment='operational')
    op=WitnessStore.initialize(tmp_path/'op.db',operational,NEW_WIT,note(LEAVES[:2],NEW_LOG))
    assert rotate(pin,operational,old,op.read(CHALLENGE),proof) is None
    successor=rotate(pin,p,old,new,proof)
    back=WitnessStore.initialize(tmp_path/'back.db',policy(LOG,OTHER_WIT),OTHER_WIT,note(LEAVES[:2],LOG))
    fresh=b'c'*32
    assert rotate(successor,policy(LOG,OTHER_WIT),handoff[-1].read(fresh),back.read(fresh),(),challenge=fresh) is None


def test_single_role_rotation_is_supported(handoff,tmp_path):
    pin,_,old,_,proof,_=handoff
    p=policy(LOG,NEW_WIT)
    new=WitnessStore.initialize(tmp_path/'single.db',p,NEW_WIT,note(LEAVES[:2],LOG))
    successor=rotate(pin,p,old,new.read(CHALLENGE),proof)
    assert successor is not None and successor.retired_keys==(pub(WIT),)


def test_offline_authority_must_not_share_roles(handoff):
    pin,_,_,_,_,_=handoff
    with pytest.raises(ValueError): replace(pin,authority_key=pub(LOG))
    with pytest.raises(ValueError): replace(pin,epoch=True)
    with pytest.raises(ValueError): replace(pin,retired_keys=(pub(WIT),))
    with pytest.raises(ValueError): replace(pin,receipt=replace(pin.receipt,signature=bytes(64)))


def test_second_rotation_continues_epoch_and_retirement(handoff,tmp_path):
    pin,p,old,new,proof,store=handoff
    successor=rotate(pin,p,old,new,proof)
    p2=policy(OTHER_LOG,OTHER_WIT)
    w2=WitnessStore.initialize(tmp_path/'epoch2.db',p2,OTHER_WIT,note(LEAVES[:2],OTHER_LOG))
    challenge=b'c'*32
    epoch2=rotate(successor,p2,store.read(challenge),w2.read(challenge),(),challenge=challenge)
    assert epoch2 is not None and epoch2.epoch==2
    assert set(epoch2.retired_keys)=={pub(LOG),pub(WIT),pub(NEW_LOG),pub(NEW_WIT)}
    assert not verify_witness(new,p2,CHALLENGE)


def test_rotated_pin_integrates_existing_v75_anchor(tmp_path):
    from omega_x_evolution.ontos_v72_receipts import ReceiptScope, sign_receipt
    from omega_x_evolution.ontos_v72_merkle import inclusion_proof
    from omega_x_evolution.ontos_v75_anchor import AnchorTrust, AnchorEvidence, GATE_IDS, review_leaf, verify_review_anchor
    # Operational policy protocol exercised with public fixture keys, not live TCB.
    p0=policy(environment='operational')
    p1=policy(NEW_LOG,NEW_WIT,environment='operational')
    w0=WitnessStore.initialize(tmp_path/'old.db',p0,WIT,note(LEAVES[:1],LOG))
    w1=WitnessStore.initialize(tmp_path/'new.db',p1,NEW_WIT,note(LEAVES[:1],NEW_LOG))
    pin=EpochPin(0,p0,pub(ROOT),w0.read(b'a'*32),())
    successor=rotate(pin,p1,w0.read(CHALLENGE),w1.read(CHALLENGE),())
    assert successor is not None
    evaluator=OTHER_LOG
    trust={g:(ReceiptScope('L12',g,'a'*40,'rotation','eval'),pub(evaluator)) for g in GATE_IDS}
    receipts={g:sign_receipt({'decision':'fixture'},scope,evaluator) for g,(scope,_) in trust.items()}
    data=review_leaf(commit_sha='a'*40,tenant='rotation',manifest_pin='b'*64,campaign_pin='c'*64,trust=trust,receipts=receipts)
    leaves=LEAVES[:1]+(leaf_hash(data),)
    proof=consistency_proof(leaves,1)
    assert w1.advance(note(leaves,NEW_LOG),proof,expected_revision=0)=='ADVANCED'
    challenge=b'c'*32
    evidence=AnchorEvidence(w1.read(challenge),proof,inclusion_proof(leaves,1))
    assert verify_review_anchor(data,AnchorTrust(successor.policy,successor.receipt,challenge),evidence,(pub(evaluator),))
    assert not verify_review_anchor(data,AnchorTrust(pin.policy,pin.receipt,challenge),evidence,(pub(evaluator),))
