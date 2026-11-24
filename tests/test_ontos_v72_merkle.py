"""RFC 6962 finite proof contracts and adversarial boundary tests."""
import hashlib

import pytest

from omega_x_evolution.ontos_v72_merkle import (
    EMPTY_ROOT, leaf_hash, node_hash, merkle_root, inclusion_proof,
    consistency_proof, verify_inclusion, verify_consistency,
)


def oracle(items):
    if not items:
        return hashlib.sha256(b'').digest()
    if len(items) == 1:
        return hashlib.sha256(b'\x00' + items[0]).digest()
    k = 1 << ((len(items) - 1).bit_length() - 1)
    return hashlib.sha256(b'\x01' + oracle(items[:k]) + oracle(items[k:])).digest()


def test_rfc6962_domain_separation_and_empty():
    assert EMPTY_ROOT == hashlib.sha256(b'').digest()
    assert merkle_root(()) == EMPTY_ROOT
    assert leaf_hash(b'') == hashlib.sha256(b'\x00').digest()
    assert node_hash(EMPTY_ROOT, EMPTY_ROOT) == hashlib.sha256(b'\x01' + EMPTY_ROOT * 2).digest()


def test_all_prefixes_and_leaves_through_32():
    items = tuple(str(i).encode() for i in range(32))
    leaves = tuple(map(leaf_hash, items))
    for n in range(1, 33):
        root = merkle_root(leaves[:n])
        assert root == oracle(items[:n])
        for i in range(n):
            p = inclusion_proof(leaves[:n], i)
            assert verify_inclusion(leaves[i], i, n, p, root)
            assert not verify_inclusion(leaf_hash(b'bad'), i, n, p, root)
            assert not verify_inclusion(leaves[i], i, n, p + (EMPTY_ROOT,), root)
            if p:
                assert not verify_inclusion(leaves[i], i, n, p[:-1], root)
        for m in range(n + 1):
            old = oracle(items[:m])
            p = consistency_proof(leaves[:n], m)
            assert verify_consistency(m, n, old, root, p)
            assert not verify_consistency(m, n, bytes(32), root, p)
            assert not verify_consistency(m, n, old, root, p + (EMPTY_ROOT,))
            if p:
                assert not verify_consistency(m, n, old, root, p[:-1])


@pytest.mark.parametrize('size', [True, -1, 2**64, 1.5, '1', None])
def test_invalid_size_rejected(size):
    assert not verify_inclusion(EMPTY_ROOT, 0, size, (), EMPTY_ROOT)
    assert not verify_consistency(0, size, EMPTY_ROOT, EMPTY_ROOT, ())


def test_empty_checkpoint_must_have_empty_root():
    assert verify_consistency(0, 0, EMPTY_ROOT, EMPTY_ROOT, ())
    assert not verify_consistency(0, 0, EMPTY_ROOT, bytes(32), ())
    assert not verify_consistency(0, 1, bytes(32), EMPTY_ROOT, ())
    assert not verify_consistency(0, 1, EMPTY_ROOT, b'x', ())


def test_invalid_hashes_and_proof_budget():
    assert not verify_inclusion(b'x', 0, 1, (), b'x')
    assert not verify_inclusion(EMPTY_ROOT, True, 2, (EMPTY_ROOT,), EMPTY_ROOT)
    assert not verify_inclusion(EMPTY_ROOT, 0, 2, (b'x',), EMPTY_ROOT)
    assert not verify_consistency(1, 1, b'x', b'x', ())
    assert not verify_consistency(0, 1, EMPTY_ROOT, EMPTY_ROOT, (EMPTY_ROOT,) * 65)
    with pytest.raises(ValueError): merkle_root((b'x',))
    with pytest.raises(ValueError): merkle_root((EMPTY_ROOT,) * 4097)
    with pytest.raises(ValueError): inclusion_proof((EMPTY_ROOT,), True)
    with pytest.raises(ValueError): consistency_proof((EMPTY_ROOT,), -1)


def test_untrusted_iterators_not_invoked():
    class Hostile:
        def __iter__(self): raise AssertionError('untrusted iterator invoked')
    assert not verify_inclusion(EMPTY_ROOT, 0, 1, Hostile(), EMPTY_ROOT)
    assert not verify_consistency(0, 1, EMPTY_ROOT, EMPTY_ROOT, Hostile())
    with pytest.raises(ValueError): merkle_root(Hostile())
