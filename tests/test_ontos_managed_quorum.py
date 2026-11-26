from dataclasses import replace
from hashlib import sha256
import sqlite3

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from omega_x_evolution.ontos_epoch_journal_core import IntegrityError
from omega_x_evolution.ontos_quorum_state_codec import decode_state, encode_state, MAX_CHALLENGES
from omega_x_evolution.ontos_v72_checkpoint_note import Checkpoint, sign_note
from omega_x_evolution.ontos_v72_merkle import leaf_hash, merkle_root, consistency_proof, inclusion_proof
from omega_x_evolution.ontos_v72_quorum import QuorumPolicy, QuorumWitness, QuorumCertificate
from omega_x_evolution.ontos_v72_quorum_rotation import QuorumEpochPin, rotation_challenges, rotation_message
from omega_x_evolution.ontos_v72_quorum_journal import _State, _state_digest
from omega_x_evolution.ontos_v72_receipts import ReceiptScope, sign_receipt
from omega_x_evolution.ontos_v75_anchor import review_leaf
from omega_x_evolution.ontos_managed_quorum import ManagedQuorumEpochJournal, _encode, _decode, _replay


def key(n):
    return Ed25519PrivateKey.from_private_bytes(bytes([n])*32)


def pub(n):
    return key(n).public_key().public_bytes_raw()


@pytest.fixture
def scenario(tmp_path):
    anchor = tmp_path / 'anchor'; anchor.mkdir(mode=0o700)
    segments = tmp_path / 'segments'; segments.mkdir(mode=0o700)
    witnesses = tmp_path / 'witnesses'; witnesses.mkdir(mode=0o700)
    old = QuorumPolicy('operational', 'omega/test', 'omega/test', pub(1), 0,
                       tuple(sorted(pub(i) for i in range(3, 7))))
    new = replace(old, epoch=1, witness_keys=tuple(sorted((set(old.witness_keys)-{pub(3)}) | {pub(7)})))
    leaves = (leaf_hash(b'genesis'),)
    tip = Checkpoint(old.origin, 1, merkle_root(leaves))
    pin = QuorumEpochPin(old, tip, pub(2), b'g'*32, ())
    note = sign_note(tip, old.log_name, key(1))
    paths = {pub(i): witnesses / f'w{i}.db' for i in range(3, 8)}
    signers = {pub(i): key(i) for i in range(3, 8)}
    for k in old.witness_keys:
        QuorumWitness.initialize(paths[k], old, signers[k], note)
    QuorumWitness.initialize(paths[pub(7)], new, key(7), note)
    def certificate(policy, nonce, signed_note=note, proof=()):
        votes = tuple(QuorumWitness(paths[k], policy, signers[k]).current(nonce)
                      for k in policy.witness_keys)
        return QuorumCertificate(signed_note, votes, proof)
    j = ManagedQuorumEpochJournal(anchor / 'floor.db', segments)
    initial = j.initialize(pin)
    return j, initial, pin, new, paths, signers, leaves, certificate


def rotation(s):
    j, initial, pin, new, _, _, _, cert = s
    nonce = b'r'*32
    oc, nc = rotation_challenges(pin, new, nonce)
    sig = key(2).sign(rotation_message(pin, new, pin.checkpoint, nonce))
    return j.rotate(initial.fence, new, cert(pin.policy, oc), cert(new, nc),
                    challenge=nonce, authority_signature=sig)


def test_actual_quorum_rotation_rollover_reopen_and_replay(scenario, tmp_path):
    j, initial, pin, new, _, _, _, cert = scenario
    rotated = rotation(scenario)
    assert rotated.status == 'COMMITTED'
    assert rotated.snapshot.state.retired_keys == (pub(3),)
    first = j.append(rotated.snapshot.fence, cert(new, b'a'*32), challenge=b'a'*32)
    assert first.status == 'COMMITTED'
    rolled = j.compact(first.snapshot.fence)
    assert rolled.status == 'COMPACTED' and rolled.snapshot.state == first.snapshot.state
    assert rolled.snapshot.fence.generation == 1
    reopened = ManagedQuorumEpochJournal(tmp_path/'anchor'/'floor.db', tmp_path/'segments')
    assert reopened.read(rolled.snapshot.fence) == rolled.snapshot
    assert reopened.verify_sealed(0) == first.snapshot
    assert reopened.append(first.snapshot.fence, cert(new, b'b'*32), challenge=b'b'*32).status == 'STALE'
    assert reopened.append(rolled.snapshot.fence, cert(pin.policy, b'b'*32), challenge=b'b'*32).status == 'REJECTED'
    assert reopened.append(rolled.snapshot.fence, cert(new, b'r'*32), challenge=b'r'*32).status == 'REJECTED'
    fresh = reopened.append(rolled.snapshot.fence, cert(new, b'b'*32), challenge=b'b'*32)
    assert fresh.status == 'COMMITTED'
    assert reopened.append(fresh.snapshot.fence, cert(new, b'a'*32), challenge=b'a'*32).status == 'REJECTED'


def review_data(evaluator):
    trust = {f'GATE-0{i}': (ReceiptScope('L12', f'GATE-0{i}', 'a'*40, 'fixture', 'reviewer'), evaluator.public_key().public_bytes_raw()) for i in range(1, 9)}
    receipts = {gate: sign_receipt({'fixture': gate}, scope, evaluator) for gate, (scope, _) in trust.items()}
    return review_leaf(commit_sha='a'*40, tenant='fixture', manifest_pin='b'*64,
                       campaign_pin='c'*64, trust=trust, receipts=receipts)


@pytest.mark.parametrize('evaluator,expected', [(3, 'REJECTED'), (8, 'COMMITTED')])
def test_review_after_rollover_retired_key_exclusion(scenario, evaluator, expected):
    j, _, _, new, paths, signers, leaves, _ = scenario
    rotated = rotation(scenario)
    rolled = j.compact(rotated.snapshot.fence).snapshot
    data = review_data(key(evaluator))
    combined = leaves + (leaf_hash(data),)
    tip = Checkpoint(new.origin, 2, merkle_root(combined))
    note = sign_note(tip, new.log_name, key(1))
    proof = consistency_proof(combined, 1)
    challenge = b'v'*32
    votes = tuple(QuorumWitness(paths[k], new, signers[k]).vote(note, proof, expected_revision=0, challenge=challenge)
                  for k in new.witness_keys)
    assert all(v is not None for v in votes)
    result = j.commit_review(rolled.fence, data, QuorumCertificate(note, votes, proof),
                             inclusion_proof(combined, 1), (pub(evaluator),)*8, challenge=challenge)
    assert result.status == expected
    assert j.read(result.snapshot.fence) == result.snapshot
    if expected == 'COMMITTED':
        assert result.snapshot.state.checkpoint == tip
    else:
        assert result.snapshot == rolled


def test_actual_state_codec_digest_and_history_capacity(scenario):
    _, _, pin, *_ = scenario
    history = (b'x'*32, b'y'*32, pin.last_challenge)
    state = _State(pin, history)
    restored = _decode(_encode(state))
    assert restored == state and _state_digest(restored) == _state_digest(state)
    with pytest.raises(ValueError):
        _encode(_State(pin, history[::-1]))
    raw = encode_state(replace(decode_state(_encode(state)), authority_key=b'\0'*32))
    with pytest.raises(ValueError):
        _decode(raw)
    nonces = tuple(sha256(str(i).encode()).digest() for i in range(MAX_CHALLENGES-1)) + (pin.last_challenge,)
    full = _State(pin, nonces)
    assert _decode(_encode(full)) == full
    assert _replay(full, b'not parsed after capacity') is None


def test_prepared_actual_quorum_write_recovers(scenario, tmp_path, monkeypatch):
    j, initial, pin, _, _, _, _, cert = scenario
    def fail(*args):
        raise RuntimeError('injected before anchor finalize')
    monkeypatch.setattr(j._journal, '_finish', fail)
    with pytest.raises(RuntimeError):
        j.append(initial.fence, cert(pin.policy, b'x'*32), challenge=b'x'*32)
    reopened = ManagedQuorumEpochJournal(tmp_path/'anchor'/'floor.db', tmp_path/'segments')
    with pytest.raises(IntegrityError):
        reopened.read(initial.fence)
    recovered = reopened.read()
    assert recovered.state.last_challenge == b'x'*32 and recovered.fence.cursor.sequence == 1
    assert reopened.read(recovered.fence) == recovered


def test_tampered_compacted_bootstrap_rejected(scenario, tmp_path):
    j, _, _, _, _, _, _, _ = scenario
    rotated = rotation(scenario)
    rolled = j.compact(rotated.snapshot.fence).snapshot
    with sqlite3.connect(tmp_path/'anchor'/'floor.db') as db:
        raw, = db.execute('SELECT bootstrap FROM active').fetchone()
        state = decode_state(raw)
        changed = encode_state(replace(state, challenges=state.challenges[1:]))
        db.execute('UPDATE active SET bootstrap=?', (changed,))
    with pytest.raises(IntegrityError):
        j.read(rolled.fence)
