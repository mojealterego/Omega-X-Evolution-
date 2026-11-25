from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import shutil

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from omega_x_evolution.ontos_epoch_journal_core import IntegrityError
from omega_x_evolution.ontos_v72_checkpoint_note import Checkpoint, sign_note
from omega_x_evolution.ontos_v72_merkle import leaf_hash, merkle_root, consistency_proof, inclusion_proof
from omega_x_evolution.ontos_v72_quorum import QuorumPolicy, QuorumWitness, QuorumCertificate
from omega_x_evolution.ontos_v72_quorum_rotation import QuorumEpochPin, rotation_challenges, rotation_message
from omega_x_evolution.ontos_v72_quorum_journal import QuorumEpochJournal
from omega_x_evolution.ontos_v75_anchor import review_leaf
from omega_x_evolution.ontos_v72_receipts import ReceiptScope


def key(n):
    return Ed25519PrivateKey.from_private_bytes(bytes([n]) * 32)


def pub(n):
    return key(n).public_key().public_bytes_raw()


@pytest.fixture
def scenario(tmp_path):
    tmp_path.chmod(0o700)
    old = QuorumPolicy('operational', 'omega/journal', 'omega/journal', pub(1), 0,
                       tuple(sorted(pub(i) for i in range(3, 7))))
    retired = pub(3)
    new = replace(old, epoch=1, witness_keys=tuple(sorted((set(old.witness_keys) - {retired}) | {pub(7)})))
    leaves = (leaf_hash(b'genesis'),)
    tip = Checkpoint(old.origin, 1, merkle_root(leaves))
    pin = QuorumEpochPin(old, tip, pub(2), b'g' * 32, ())
    note = sign_note(tip, old.log_name, key(1))
    paths = {pub(i): tmp_path / f'w{i}.db' for i in range(3, 8)}
    signers = {pub(i): key(i) for i in range(3, 8)}
    for k in old.witness_keys:
        QuorumWitness.initialize(paths[k], old, signers[k], note)
    QuorumWitness.initialize(paths[pub(7)], new, key(7), note)
    nonce = b'r' * 32
    oc, nc = rotation_challenges(pin, new, nonce)
    def certificate(policy, challenge, signed_note=note, proof=()):
        return QuorumCertificate(signed_note, tuple(QuorumWitness(paths[k], policy, signers[k]).current(challenge)
                                                   for k in policy.witness_keys), proof)
    a, b = certificate(old, oc), certificate(new, nc)
    signature = key(2).sign(rotation_message(pin, new, tip, nonce))
    journal = QuorumEpochJournal.initialize(tmp_path / 'client.db', pin)
    return journal, pin, new, nonce, a, b, signature, retired, paths, signers, leaves, certificate


def rotate(s):
    j, _, new, nonce, a, b, sig, *_ = s
    return j.rotate(j.genesis, new, a, b, challenge=nonce, authority_signature=sig)


def test_rotate_reopen_and_restore_against_external_floor(scenario, tmp_path):
    j, pin, new, _, _, _, _, retired, *_ = scenario
    path = tmp_path / 'client.db'
    backup = tmp_path / 'copy.db'
    shutil.copyfile(path, backup)
    result = rotate(scenario)
    assert result.status == 'COMMITTED'
    assert result.snapshot.state.policy == new
    assert result.snapshot.state.retired_keys == (retired,)
    reopened = QuorumEpochJournal(path, pin)
    assert reopened.read(result.snapshot.cursor) == result.snapshot
    assert rotate(scenario).status == 'STALE'
    shutil.copyfile(backup, path)
    with pytest.raises(IntegrityError):
        reopened.read(result.snapshot.cursor)


def test_competing_rotations_and_old_epoch_replay(scenario):
    j, pin, new, _, _, _, _, _, _, _, _, cert = scenario
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: rotate(scenario), range(2)))
    assert sorted(r.status for r in results) == ['COMMITTED', 'STALE']
    floor = j.read(j.genesis).cursor
    assert j.append(floor, cert(pin.policy, b'x' * 32), challenge=b'x' * 32).status == 'REJECTED'
    c = cert(new, b'x' * 32)
    first = j.append(floor, c, challenge=b'x' * 32)
    second = j.append(first.snapshot.cursor, cert(new, b'y' * 32), challenge=b'y' * 32)
    assert second.status == 'COMMITTED'
    assert j.append(second.snapshot.cursor, c, challenge=b'x' * 32).status == 'REJECTED'


def review_data(k):
    trust = {f'GATE-0{i}': (ReceiptScope('L12', f'GATE-0{i}', 'a' * 40, 'fixture', 'reviewer'), k)
             for i in range(1, 9)}
    return review_leaf(commit_sha='a' * 40, tenant='fixture', manifest_pin='b' * 64, campaign_pin='c' * 64,
                       trust=trust, receipts={gate: {'fixture': gate} for gate in trust})


def test_v75_review_leaf_persistence_role_separation_and_cas(scenario, tmp_path):
    j, pin, new, _, _, _, _, retired, paths, signers, leaves, _ = scenario
    rotated = rotate(scenario)
    data = review_data(pub(8))
    combined = leaves + (leaf_hash(data),)
    checkpoint = Checkpoint(new.origin, len(combined), merkle_root(combined))
    note = sign_note(checkpoint, new.log_name, key(1))
    proof = consistency_proof(combined, 1)
    challenge = b'v' * 32
    votes = tuple(QuorumWitness(paths[k], new, signers[k]).vote(note, proof, expected_revision=0, challenge=challenge)
                  for k in new.witness_keys)
    assert all(v is not None for v in votes)
    certificate = QuorumCertificate(note, votes, proof)
    inclusion = inclusion_proof(combined, 1)
    floor = rotated.snapshot.cursor
    for bad in (pin.authority_key, retired, new.log_key, new.witness_keys[0]):
        assert j.commit_review(floor, data, certificate, inclusion, (bad,) * 8, challenge=challenge).status == 'REJECTED'
    assert j.commit_review(floor, data, certificate, (), (pub(8),) * 8, challenge=challenge).status == 'REJECTED'
    assert j.commit_review(floor, data, certificate, inclusion, (pub(9),) * 8, challenge=challenge).status == 'REJECTED'
    result = j.commit_review(floor, data, certificate, inclusion, (pub(8),) * 8, challenge=challenge)
    assert result.status == 'COMMITTED' and result.snapshot.state.checkpoint == checkpoint
    assert QuorumEpochJournal(tmp_path / 'client.db', pin).read(result.snapshot.cursor) == result.snapshot
    assert j.commit_review(floor, data, certificate, inclusion, (pub(8),) * 8, challenge=challenge).status == 'STALE'
    assert j.commit_review(result.snapshot.cursor, data, certificate, inclusion, (pub(8),) * 8, challenge=challenge).status == 'REJECTED'


@pytest.mark.parametrize('role', ['authority', 'retired'])
def test_review_with_actual_forbidden_evaluator_in_leaf(scenario, role):
    j, pin, new, _, _, _, _, retired, paths, signers, leaves, _ = scenario
    rotated = rotate(scenario)
    evaluator = pin.authority_key if role == 'authority' else retired
    data = review_data(evaluator)
    combined = leaves + (leaf_hash(data),)
    checkpoint = Checkpoint(new.origin, 2, merkle_root(combined))
    note = sign_note(checkpoint, new.log_name, key(1))
    proof = consistency_proof(combined, 1)
    challenge = b'f' * 32
    votes = tuple(QuorumWitness(paths[k], new, signers[k]).vote(note, proof, expected_revision=0, challenge=challenge)
                  for k in new.witness_keys)
    assert all(v is not None for v in votes)
    result = j.commit_review(rotated.snapshot.cursor, data, QuorumCertificate(note, votes, proof),
                             inclusion_proof(combined, 1), (evaluator,) * 8, challenge=challenge)
    assert result.status == 'REJECTED' and result.snapshot == rotated.snapshot
