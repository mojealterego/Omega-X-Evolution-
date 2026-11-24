"""Authenticated append-only transition relative to an externally pinned checkpoint."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from omega_x_evolution.ontos_v72_checkpoint_note import Checkpoint, sign_note
from omega_x_evolution.ontos_v72_merkle import (
    consistency_proof, inclusion_proof, leaf_hash, merkle_root,
)
from omega_x_evolution.ontos_v72_checkpoint_chain import CheckpointChain

KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
PUBLIC = KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
ORIGIN = 'omega.example/main'
LEAVES = tuple(leaf_hash(str(i).encode()) for i in range(16))


def cp(leaves):
    return Checkpoint(ORIGIN, len(leaves), merkle_root(leaves))


def note(leaves, key=KEY):
    return sign_note(cp(leaves), ORIGIN, key)


def chain(leaves=LEAVES[:1]):
    return CheckpointChain(cp(leaves), key_name=ORIGIN, public_key=PUBLIC)


def test_append_inclusion_and_idempotency():
    c = chain()
    for n in range(2, 17):
        leaves = LEAVES[:n]
        assert c.advance(note(leaves), consistency_proof(leaves,n-1)) == 'ADVANCED'
        assert c.current == cp(leaves)
        assert c.includes(b'0',0,inclusion_proof(leaves,0))
        assert not c.includes(b'wrong',0,inclusion_proof(leaves,0))
        assert c.advance(note(leaves), ()) == 'UNCHANGED'
    assert not c.includes(b'0',True,())


def test_rollback_equivocation_and_fork_fail_without_state_change():
    c = chain(LEAVES[:4]); old = c.current
    fork = (leaf_hash(b'fork'),) + LEAVES[1:]
    assert c.advance(note(LEAVES[:3]), ()) == 'ROLLBACK'
    assert c.advance(note(fork[:4]), ()) == 'EQUIVOCATION'
    assert c.advance(note(fork), consistency_proof(fork,4)) == 'INVALID_PROOF'
    assert c.current == old


def test_authentication_before_consistency():
    c = chain(); old = c.current
    other = Ed25519PrivateKey.from_private_bytes(bytes(32))
    assert c.advance(note(LEAVES,other), consistency_proof(LEAVES,1)) == 'INVALID_NOTE'
    assert c.advance(note(LEAVES)[:-1], consistency_proof(LEAVES,1)) == 'INVALID_NOTE'
    assert c.current == old


def test_missing_or_invalid_proof_fail_closed():
    c = chain()
    for proof in ((), (b'x',), (bytes(32),)*65, None, [bytes(32)]):
        assert c.advance(note(LEAVES),proof) == 'INVALID_PROOF'
    assert c.advance(note(LEAVES[:1]), (bytes(32),)) == 'INVALID_PROOF'
    assert c.current == cp(LEAVES[:1])


def test_empty_pin_is_explicit_and_requires_authentication():
    c = chain(())
    assert not c.includes(b'0',0,())
    assert c.advance(note(LEAVES), ()) == 'ADVANCED'
    assert c.advance(note(()), ()) == 'ROLLBACK'
    with pytest.raises(ValueError): CheckpointChain(None,key_name=ORIGIN,public_key=PUBLIC)
    with pytest.raises(ValueError): CheckpointChain(cp(()),key_name=ORIGIN,public_key=bytes(32))


def test_concurrent_competing_append_only_one_branch_advances():
    c = chain()
    a = LEAVES[:2]
    b = (LEAVES[0],leaf_hash(b'alternative'))
    with ThreadPoolExecutor(max_workers=2) as ex:
        results = list(ex.map(lambda leaves: c.advance(note(leaves),consistency_proof(leaves,1)),(a,b)))
    assert sorted(results) == ['ADVANCED','EQUIVOCATION']
    assert c.current in (cp(a),cp(b))
