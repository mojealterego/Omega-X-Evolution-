"""L12 v72: authenticated Merkle transitions relative to a trusted local pin.

The caller provisions the initial pin and signer outside candidate control.
This process-local chain is not a persistent external monotonic witness.
"""
from __future__ import annotations

from threading import Lock
from typing import Literal

from .ontos_v72_checkpoint_note import Checkpoint, _name, verify_note
from .ontos_v72_merkle import leaf_hash, verify_consistency, verify_inclusion
from .ontos_v72_receipts import _prime_order_point

Transition = Literal['ADVANCED', 'UNCHANGED', 'ROLLBACK', 'EQUIVOCATION',
                     'INVALID_PROOF', 'INVALID_NOTE']


class CheckpointChain:
    """Serialize authenticated updates; never learn trust roots from a note."""

    def __init__(self, pin: Checkpoint, *, key_name: str, public_key: bytes) -> None:
        if type(pin) is not Checkpoint or not _prime_order_point(public_key):
            raise ValueError('trusted checkpoint and prime-order public key required')
        _name(key_name)
        self._current = Checkpoint(pin.origin, pin.tree_size, pin.root)
        self._key_name = key_name
        self._public_key = public_key
        self._lock = Lock()

    @property
    def current(self) -> Checkpoint:
        with self._lock:
            p = self._current
            return Checkpoint(p.origin, p.tree_size, p.root)

    def advance(self, note: bytes, proof: tuple[bytes, ...]) -> Transition:
        """Authenticate and atomically compare-and-advance the in-memory pin."""
        with self._lock:
            old = self._current
            new = verify_note(note, expected_origin=old.origin,
                              trusted_key_name=self._key_name,
                              trusted_public_key=self._public_key)
            if new is None:
                return 'INVALID_NOTE'
            if new.tree_size < old.tree_size:
                return 'ROLLBACK'
            if new.tree_size == old.tree_size and new.root != old.root:
                return 'EQUIVOCATION'
            if not verify_consistency(old.tree_size, new.tree_size,
                                      old.root, new.root, proof):
                return 'INVALID_PROOF'
            if new.tree_size == old.tree_size:
                return 'UNCHANGED'
            self._current = new
            return 'ADVANCED'

    def includes(self, data: bytes, index: int, proof: tuple[bytes, ...]) -> bool:
        """Check exact leaf bytes against the currently pinned signed history."""
        try:
            digest = leaf_hash(data)
        except ValueError:
            return False
        with self._lock:
            p = self._current
            return verify_inclusion(digest, index, p.tree_size, proof, p.root)
