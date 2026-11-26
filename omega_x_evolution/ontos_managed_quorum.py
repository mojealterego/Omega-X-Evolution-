"""Managed quorum epoch journal backed by the existing authenticated reducer.

The operator must retain fences independently and use this gateway exclusively.
Initialization is for a fresh trusted genesis, not migration of a legacy journal.
Local fencing does not revoke remote witnesses or establish physical custody.
"""
from __future__ import annotations

from pathlib import Path

from .ontos_managed_journal import Fence, ManagedJournal, ManagedSnapshot, ManagedUpdate
from .ontos_quorum_state_codec import QuorumStateRecord, encode_state, decode_state, MAX_CHALLENGES
from .ontos_v72_checkpoint_note import Checkpoint
from .ontos_v72_quorum import QuorumPolicy, QuorumCertificate
from .ontos_v72_quorum_rotation import QuorumEpochPin
from .ontos_v72_quorum_journal import (
    _State, _bootstrap, _state_digest, _apply, _event, _certificate, _policy, _proof, MAX_REVIEW,
)


def _encode(state: _State) -> bytes:
    if type(state) is not _State or type(state.pin) is not QuorumEpochPin:
        raise ValueError('typed quorum state required')
    pin = state.pin
    pin.__post_init__()
    p = pin.policy
    record = QuorumStateRecord(p.environment, p.origin, p.log_name, p.log_key, p.epoch,
                               p.witness_keys, pin.checkpoint.tree_size, pin.checkpoint.root,
                               pin.authority_key, pin.retired_keys, state.challenges)
    raw = encode_state(record)
    if record.last_challenge != pin.last_challenge:
        raise ValueError('challenge history and epoch pin disagree')
    return raw


def _decode(raw: bytes) -> _State:
    r = decode_state(raw)
    policy = QuorumPolicy(r.environment, r.origin, r.log_name, r.log_key, r.epoch, r.witness_keys)
    checkpoint = Checkpoint(r.origin, r.tree_size, r.root)
    pin = QuorumEpochPin(policy, checkpoint, r.authority_key, r.last_challenge, r.retired_keys)
    return _State(pin, r.challenges)


def _replay(state: _State, payload: bytes) -> _State | None:
    # Never discard an old nonce to make room for a new one.
    if len(state.challenges) >= MAX_CHALLENGES:
        return None
    return _apply(state, payload)


def _snapshot(s: ManagedSnapshot[_State]) -> ManagedSnapshot[QuorumEpochPin]:
    return ManagedSnapshot(s.fence, s.state.pin)


def _update(u: ManagedUpdate[_State]) -> ManagedUpdate[QuorumEpochPin]:
    return ManagedUpdate(u.status, _snapshot(u.snapshot))


class ManagedQuorumEpochJournal:
    """Fenced append, joint rotation, review and non-destructive rollover."""

    def __init__(self, anchor: Path, segments: Path):
        self._journal = ManagedJournal(anchor, segments, _state_digest, _replay, _encode, _decode)

    def initialize(self, bootstrap: QuorumEpochPin) -> ManagedSnapshot[QuorumEpochPin]:
        state = _bootstrap(bootstrap)
        if bootstrap.policy.epoch != 0 or bootstrap.retired_keys:
            raise ValueError('fresh genesis only; legacy state migration is not supported')
        return _snapshot(self._journal.initialize(state))

    def read(self, retained: Fence | None = None) -> ManagedSnapshot[QuorumEpochPin]:
        """Without a retained fence, trust the protected anchor for recovery."""
        return _snapshot(self._journal.read(retained))

    def compact(self, expected: Fence) -> ManagedUpdate[QuorumEpochPin]:
        return _update(self._journal.compact(expected))

    def verify_sealed(self, generation: int) -> ManagedSnapshot[QuorumEpochPin]:
        return _snapshot(self._journal.verify_sealed(generation))

    def append(self, expected: Fence, certificate: QuorumCertificate, *, challenge: bytes) -> ManagedUpdate[QuorumEpochPin]:
        return _update(self._journal.append(expected, _event('append', challenge, certificate=_certificate(certificate))))

    def rotate(self, expected: Fence, proposed: QuorumPolicy, old: QuorumCertificate, new: QuorumCertificate,
               *, challenge: bytes, authority_signature: bytes) -> ManagedUpdate[QuorumEpochPin]:
        if type(authority_signature) is not bytes or len(authority_signature) != 64:
            raise ValueError('bounded authority signature required')
        return _update(self._journal.append(expected, _event('rotate', challenge, policy=_policy(proposed),
                                    old=_certificate(old), new=_certificate(new), authority=authority_signature.hex())))

    def commit_review(self, expected: Fence, data: bytes, certificate: QuorumCertificate,
                      inclusion: tuple[bytes, ...], evaluator_keys: tuple[bytes, ...], *, challenge: bytes) -> ManagedUpdate[QuorumEpochPin]:
        """Persist a canonical review leaf; caller verifies evaluator evidence first."""
        if (type(data) is not bytes or not 0 < len(data) <= MAX_REVIEW
                or type(evaluator_keys) is not tuple or len(evaluator_keys) != 8
                or any(type(k) is not bytes or len(k) != 32 for k in evaluator_keys)):
            raise ValueError('bounded review and evaluator keys required')
        return _update(self._journal.append(expected, _event('review', challenge, certificate=_certificate(certificate),
                                    data=data.hex(), inclusion=_proof(inclusion), evaluators=[k.hex() for k in evaluator_keys])))
