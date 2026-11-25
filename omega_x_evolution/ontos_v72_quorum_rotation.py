"""Planned single-member quorum handoff with joint native certificates.

The operator must quiesce the old epoch, retain the returned pin in an
independently protected compare-and-swap domain, and serialize authority
approvals. This verifier is not distributed consensus or key provisioning.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256

from .ontos_v72_checkpoint_note import Checkpoint
from .ontos_v72_jcs import canonical_json
from .ontos_v72_quorum import QuorumPolicy, QuorumCertificate, verify_quorum
from .ontos_v72_receipts import _prime_order_point, strict_verify

_DOMAIN = b'OMEGA-X/v72/quorum-rotation/v1\x00'
_MAX_RETIRED = 128


@dataclass(frozen=True, slots=True)
class QuorumEpochPin:
    policy: QuorumPolicy
    checkpoint: Checkpoint
    authority_key: bytes
    last_challenge: bytes
    retired_keys: tuple[bytes, ...]

    def __post_init__(self) -> None:
        if (type(self.policy) is not QuorumPolicy or type(self.checkpoint) is not Checkpoint
                or not _prime_order_point(self.authority_key)
                or type(self.last_challenge) is not bytes or len(self.last_challenge) != 32
                or type(self.retired_keys) is not tuple or len(self.retired_keys) > _MAX_RETIRED
                or any(not _prime_order_point(k) for k in self.retired_keys)
                or tuple(sorted(set(self.retired_keys))) != self.retired_keys):
            raise ValueError('invalid trusted quorum epoch pin')
        self.policy.__post_init__()
        self.checkpoint.__post_init__()
        active = (self.authority_key, self.policy.log_key, *self.policy.witness_keys)
        if (self.checkpoint.origin != self.policy.origin or len(set(active)) != len(active)
                or set(active).intersection(self.retired_keys)):
            raise ValueError('invalid key roles or checkpoint scope')

    def digest(self) -> bytes:
        self.__post_init__()
        return sha256(canonical_json({'schema': 'omega-v72-quorum-epoch-pin-v1',
            'policy': self.policy.digest().hex(), 'size': str(self.checkpoint.tree_size),
            'root': self.checkpoint.root.hex(), 'authority': self.authority_key.hex(),
            'last_challenge': self.last_challenge.hex(),
            'retired': [k.hex() for k in self.retired_keys]})).digest()


def _transition(current: QuorumEpochPin, proposed: QuorumPolicy, challenge: bytes) -> tuple[bytes, bytes]:
    if (type(current) is not QuorumEpochPin or type(proposed) is not QuorumPolicy
            or type(challenge) is not bytes or len(challenge) != 32):
        raise ValueError('typed quorum transition and challenge required')
    current.__post_init__()
    proposed.__post_init__()
    old = current.policy
    removed = set(old.witness_keys) - set(proposed.witness_keys)
    added = set(proposed.witness_keys) - set(old.witness_keys)
    if (challenge == current.last_challenge or proposed.epoch != old.epoch + 1
            or (proposed.environment, proposed.origin, proposed.log_name, proposed.log_key)
            != (old.environment, old.origin, old.log_name, old.log_key)
            or len(removed) != 1 or len(added) != 1
            or current.authority_key in added or added.intersection(current.retired_keys)
            or len(current.retired_keys) >= _MAX_RETIRED):
        raise ValueError('only one fresh witness replacement in the next epoch is allowed')
    return next(iter(removed)), next(iter(added))


def rotation_challenges(current: QuorumEpochPin, proposed: QuorumPolicy,
                        challenge: bytes) -> tuple[bytes, bytes]:
    """Bind each side's vote to the same transition and distinct signing domains."""
    _transition(current, proposed, challenge)
    context = current.digest() + proposed.digest() + challenge
    return (sha256(_DOMAIN + b'old\x00' + context).digest(),
            sha256(_DOMAIN + b'new\x00' + context).digest())


def rotation_message(current: QuorumEpochPin, proposed: QuorumPolicy,
                     tip: Checkpoint, challenge: bytes) -> bytes:
    _transition(current, proposed, challenge)
    if type(tip) is not Checkpoint:
        raise ValueError('typed checkpoint required')
    tip.__post_init__()
    if tip.origin != current.policy.origin or tip.tree_size < current.checkpoint.tree_size:
        raise ValueError('invalid handoff checkpoint')
    return _DOMAIN + b'authority\x00' + canonical_json({
        'previous_pin': current.digest().hex(), 'next_policy': proposed.digest().hex(),
        'size': str(tip.tree_size), 'root': tip.root.hex(), 'challenge': challenge.hex()})


def rotate_quorum(current: QuorumEpochPin, proposed: QuorumPolicy,
                  old_certificate: QuorumCertificate, new_certificate: QuorumCertificate,
                  *, challenge: bytes, authority_signature: bytes) -> QuorumEpochPin | None:
    """Require both 3-of-4 certificates, the newcomer vote, and offline approval."""
    try:
        removed, added = _transition(current, proposed, challenge)
        old_ch, new_ch = rotation_challenges(current, proposed, challenge)
        old_tip = verify_quorum(current.policy, current.checkpoint, old_ch, old_certificate)
        if old_tip is None or not strict_verify(current.authority_key,
                rotation_message(current, proposed, old_tip, challenge), authority_signature):
            return None
        new_tip = verify_quorum(proposed, old_tip, new_ch, new_certificate)
        if (new_tip != old_tip or new_certificate.note != old_certificate.note
                or added not in {v.witness_key for v in new_certificate.votes}):
            return None
        retired = tuple(sorted((*current.retired_keys, removed)))
        return QuorumEpochPin(proposed, old_tip, current.authority_key, challenge, retired)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return None


def advance_quorum_pin(current: QuorumEpochPin, certificate: QuorumCertificate,
                       *, challenge: bytes) -> QuorumEpochPin | None:
    """Advance the retained floor using the currently pinned roster only."""
    try:
        if type(current) is not QuorumEpochPin:
            return None
        current.__post_init__()
        if challenge == current.last_challenge:
            return None
        tip = verify_quorum(current.policy, current.checkpoint, challenge, certificate)
        return None if tip is None else replace(current, checkpoint=tip, last_challenge=challenge)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return None
