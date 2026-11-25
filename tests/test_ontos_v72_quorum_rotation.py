from dataclasses import replace
from itertools import combinations

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from omega_x_evolution.ontos_v72_checkpoint_note import Checkpoint, sign_note
from omega_x_evolution.ontos_v72_merkle import leaf_hash, merkle_root, consistency_proof
from omega_x_evolution.ontos_v72_quorum import QuorumPolicy, QuorumWitness, QuorumCertificate
from omega_x_evolution.ontos_v72_quorum_rotation import (
    QuorumEpochPin, rotation_challenges, rotation_message, rotate_quorum, advance_quorum_pin,
)


def key(n):
    return Ed25519PrivateKey.from_private_bytes(bytes([n]) * 32)


def public(k):
    return k.public_key().public_bytes_raw()


@pytest.fixture
def scenario(tmp_path):
    log, authority = key(1), key(2)
    keys = {public(k): k for k in (key(i) for i in range(3, 9))}
    old_keys = tuple(sorted(public(key(i)) for i in range(3, 7)))
    retired, newcomer = old_keys[0], public(key(7))
    old = QuorumPolicy('simulation', 'omega/quorum', 'omega/quorum', public(log), 4, old_keys)
    new = replace(old, epoch=5, witness_keys=tuple(sorted(set(old_keys[1:]) | {newcomer})))
    leaves = tuple(leaf_hash(bytes([i])) for i in range(1, 4))
    base = Checkpoint(old.origin, 1, merkle_root(leaves[:1]))
    tip = Checkpoint(old.origin, 3, merkle_root(leaves))
    note = sign_note(tip, old.log_name, log)
    genesis = sign_note(base, old.log_name, log)
    proof = consistency_proof(leaves, 1)
    pin = QuorumEpochPin(old, base, public(authority), b'p' * 32, ())
    nonce = b'r' * 32
    oc, nc = rotation_challenges(pin, new, nonce)
    old_votes, new_votes, stores = {}, {}, {}
    for i, k in enumerate(old_keys):
        path = tmp_path / f'w{i}.sqlite'
        witness = QuorumWitness.initialize(path, old, keys[k], genesis)
        stores[k] = path
        old_votes[k] = witness.vote(note, proof, expected_revision=0, challenge=oc)
    for k in new.witness_keys:
        if k in stores:
            witness = QuorumWitness(stores[k], new, keys[k])
        else:
            witness = QuorumWitness.initialize(tmp_path / 'new.sqlite', new, keys[k], note)
        new_votes[k] = witness.current(nc)
    a = QuorumCertificate(note, tuple(old_votes.values()), proof)
    b = QuorumCertificate(note, tuple(new_votes.values()), ())
    signature = authority.sign(rotation_message(pin, new, tip, nonce))
    return pin, new, tip, nonce, a, b, signature, retired, newcomer, authority, old_votes, new_votes


def rotate(s, **kw):
    pin, new, tip, nonce, a, b, signature, *_ = s
    args = dict(current=pin, proposed=new, old_certificate=a, new_certificate=b,
                challenge=nonce, authority_signature=signature)
    args.update(kw)
    return rotate_quorum(**args)


def test_joint_quorum_real_sqlite_and_retirement(scenario):
    pin, new, tip, nonce, a, b, sig, retired, newcomer, *_ = scenario
    result = rotate(scenario)
    assert result == QuorumEpochPin(new, tip, pin.authority_key, nonce, (retired,))
    assert rotate(scenario, current=result) is None
    assert advance_quorum_pin(result, a, challenge=nonce) is None


def test_all_threshold_subsets_and_newcomer_requirement(scenario):
    *_, old_votes, new_votes = scenario
    a, b, newcomer = scenario[4], scenario[5], scenario[8]
    for aa in combinations(old_votes.values(), 3):
        for bb in combinations(new_votes.values(), 3):
            result = rotate(scenario, old_certificate=replace(a, votes=aa),
                            new_certificate=replace(b, votes=bb))
            assert (result is not None) == (newcomer in {v.witness_key for v in bb})


@pytest.mark.parametrize('side', ['old', 'new'])
def test_two_vote_partition_fails_closed(scenario, side):
    cert = scenario[4 if side == 'old' else 5]
    assert rotate(scenario, **{f'{side}_certificate': replace(cert, votes=cert.votes[:2])}) is None


@pytest.mark.parametrize('failure', ['duplicate', 'forgery', 'missing_consistency', 'replay', 'authority', 'wrong_tip'])
def test_invalid_handoffs_fail_closed(scenario, failure):
    pin, new, tip, nonce, a, b, sig, *_ = scenario
    if failure == 'duplicate':
        kwargs = {'old_certificate': replace(a, votes=(a.votes[0],) * 3)}
    elif failure == 'forgery':
        vote = a.votes[0]
        fake = replace(vote, receipt=replace(vote.receipt, signature=b'\x00' * 64))
        kwargs = {'old_certificate': replace(a, votes=(fake,) + a.votes[1:])}
    elif failure == 'missing_consistency':
        kwargs = {'old_certificate': replace(a, consistency=())}
    elif failure == 'replay':
        kwargs = {'challenge': b'x' * 32}
    elif failure == 'authority':
        kwargs = {'authority_signature': b'\x00' * 64}
    else:
        kwargs = {'new_certificate': replace(b, note=b'not the authenticated note')}
    assert rotate(scenario, **kwargs) is None


def test_reject_epoch_skip_environment_escalation_and_multi_replacement(scenario):
    pin, new, *_ = scenario
    other = tuple(sorted((new.witness_keys[0], new.witness_keys[1], public(key(8)), public(key(9)))))
    for bad in (replace(new, epoch=6), replace(new, environment='operational'),
                replace(new, witness_keys=other), replace(new, log_key=public(key(10)))):
        with pytest.raises(ValueError):
            rotation_challenges(pin, bad, scenario[3])
        assert rotate(scenario, proposed=bad) is None


def test_retired_and_authority_keys_never_reenter(scenario):
    next_pin = rotate(scenario)
    for bad_key in (scenario[7], next_pin.authority_key):
        bad = replace(next_pin.policy, epoch=6,
                      witness_keys=tuple(sorted((set(next_pin.policy.witness_keys) - {next_pin.policy.witness_keys[0]}) | {bad_key})))
        with pytest.raises(ValueError):
            rotation_challenges(next_pin, bad, b'q' * 32)


def test_trusted_floor_and_scope_not_replaceable(scenario):
    pin, new, tip, *_ = scenario
    other = replace(pin, checkpoint=Checkpoint(pin.policy.origin, 4, b'x' * 32))
    assert rotate(scenario, current=other) is None
    with pytest.raises(ValueError):
        QuorumEpochPin(pin.policy, pin.checkpoint, pin.policy.log_key, pin.last_challenge, ())


def test_restart_append_and_old_roster_replay(scenario, tmp_path):
    pin, new, tip, nonce, *_ = scenario
    rotated = rotate(scenario)
    assert rotated is not None
    challenge = b'z' * 32
    leaves = tuple(leaf_hash(bytes([i])) for i in range(1, 5))
    next_tip = Checkpoint(new.origin, 4, merkle_root(leaves))
    note = sign_note(next_tip, new.log_name, key(1))
    proof = consistency_proof(leaves, 3)
    keys = {public(key(i)): key(i) for i in range(3, 8)}
    paths = {k: tmp_path / f'w{i}.sqlite' for i, k in enumerate(pin.policy.witness_keys)}
    paths[scenario[8]] = tmp_path / 'new.sqlite'
    witnesses = [QuorumWitness(paths[k], new, keys[k]) for k in new.witness_keys]
    votes = tuple(w.vote(note, proof, expected_revision=0 if k == scenario[8] else 1,
                         challenge=challenge) for w, k in zip(witnesses, new.witness_keys))
    assert all(v is not None for v in votes)
    certificate = QuorumCertificate(note, votes, proof)
    advanced = advance_quorum_pin(rotated, certificate, challenge=challenge)
    assert advanced == replace(rotated, checkpoint=next_tip, last_challenge=challenge)
    assert advance_quorum_pin(advanced, certificate, challenge=challenge) is None
    old_votes = tuple(QuorumWitness(paths[k], pin.policy, keys[k]).current(challenge)
                      for k in pin.policy.witness_keys if k != scenario[7])
    old_epoch_certificate = QuorumCertificate(note, old_votes, proof)
    assert advance_quorum_pin(rotated, old_epoch_certificate, challenge=challenge) is None
