"""ONTOS L12 v72: bounded RFC 6962 SHA-256 Merkle proof primitives.

Proof verification is not authentication of a checkpoint. The caller must
obtain trusted roots separately; no release or production trust is granted.
Generation accepts at most 4096 prehashed leaves; verification accepts tree
sizes up to 2**63-1 and at most 64 proof nodes.
"""
from __future__ import annotations

import hashlib

EMPTY_ROOT = hashlib.sha256(b'').digest()
MAX_LEAVES = 4096
MAX_TREE_SIZE = 2**63 - 1
MAX_PROOF_NODES = 64
MAX_LEAF_BYTES = 1024 * 1024


def _hash(value: object) -> bool:
    return type(value) is bytes and len(value) == 32


def _size(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_TREE_SIZE


def _proof(value: object) -> bool:
    return (type(value) is tuple and len(value) <= MAX_PROOF_NODES
            and all(_hash(item) for item in value))


def _validate_leaves(leaves: tuple[bytes, ...]) -> None:
    if (type(leaves) is not tuple or len(leaves) > MAX_LEAVES
            or not all(_hash(item) for item in leaves)):
        raise ValueError('bounded tuple of SHA-256 leaf hashes required')


def leaf_hash(data: bytes) -> bytes:
    if type(data) is not bytes or len(data) > MAX_LEAF_BYTES:
        raise ValueError('bounded bytes required')
    return hashlib.sha256(b'\x00' + data).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    if not _hash(left) or not _hash(right):
        raise ValueError('SHA-256 child hashes required')
    return hashlib.sha256(b'\x01' + left + right).digest()


def _split(n: int) -> int:
    return 1 << ((n - 1).bit_length() - 1)


def _root(leaves: tuple[bytes, ...]) -> bytes:
    n = len(leaves)
    if n == 0:
        return EMPTY_ROOT
    if n == 1:
        return leaves[0]
    k = _split(n)
    return node_hash(_root(leaves[:k]), _root(leaves[k:]))


def merkle_root(leaves: tuple[bytes, ...]) -> bytes:
    _validate_leaves(leaves)
    return _root(leaves)


def _inclusion(leaves: tuple[bytes, ...], index: int) -> tuple[bytes, ...]:
    if len(leaves) == 1:
        return ()
    k = _split(len(leaves))
    if index < k:
        return _inclusion(leaves[:k], index) + (_root(leaves[k:]),)
    return _inclusion(leaves[k:], index - k) + (_root(leaves[:k]),)


def inclusion_proof(leaves: tuple[bytes, ...], index: int) -> tuple[bytes, ...]:
    _validate_leaves(leaves)
    if not _size(index) or index >= len(leaves):
        raise ValueError('invalid leaf index')
    return _inclusion(leaves, index)


def verify_inclusion(leaf: bytes, index: int, tree_size: int,
                     proof: tuple[bytes, ...], expected_root: bytes) -> bool:
    if (not _hash(leaf) or not _hash(expected_root) or not _size(tree_size)
            or not _size(index) or index >= tree_size or not _proof(proof)):
        return False
    fn, sn, acc = index, tree_size - 1, leaf
    for sibling in proof:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            acc = node_hash(sibling, acc)
            while fn and not fn & 1:
                fn >>= 1
                sn >>= 1
        else:
            acc = node_hash(acc, sibling)
        fn >>= 1
        sn >>= 1
    return sn == 0 and acc == expected_root


def _subproof(m: int, leaves: tuple[bytes, ...], complete: bool) -> tuple[bytes, ...]:
    if m == len(leaves):
        return () if complete else (_root(leaves),)
    k = _split(len(leaves))
    if m <= k:
        return _subproof(m, leaves[:k], complete) + (_root(leaves[k:]),)
    return _subproof(m - k, leaves[k:], False) + (_root(leaves[:k]),)


def consistency_proof(leaves: tuple[bytes, ...], first_size: int) -> tuple[bytes, ...]:
    _validate_leaves(leaves)
    if not _size(first_size) or first_size > len(leaves):
        raise ValueError('invalid prefix size')
    if first_size in (0, len(leaves)):
        return ()
    return _subproof(first_size, leaves, True)


def verify_consistency(first_size: int, second_size: int, first_root: bytes,
                       second_root: bytes, proof: tuple[bytes, ...]) -> bool:
    if (not _size(first_size) or not _size(second_size) or first_size > second_size
            or not _hash(first_root) or not _hash(second_root) or not _proof(proof)):
        return False
    if first_size == 0:
        # The empty prefix is consistent with every authenticated nonempty tree.
        return (not proof and first_root == EMPTY_ROOT
                and (second_size > 0 or second_root == EMPTY_ROOT))
    if first_size == second_size:
        return not proof and first_root == second_root
    if not proof:
        return False
    fn, sn = first_size - 1, second_size - 1
    while fn & 1:
        fn >>= 1
        sn >>= 1
    if fn == 0:
        fr = sr = first_root
        rest = proof
    else:
        fr = sr = proof[0]
        rest = proof[1:]
    for sibling in rest:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            fr = node_hash(sibling, fr)
            sr = node_hash(sibling, sr)
            while fn and not fn & 1:
                fn >>= 1
                sn >>= 1
        else:
            sr = node_hash(sr, sibling)
        fn >>= 1
        sn >>= 1
    return sn == 0 and fr == first_root and sr == second_root
