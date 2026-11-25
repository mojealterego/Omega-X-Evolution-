"""Durable quorum epoch journal: authenticated v72 replay and v75 review commit.

The operator retains the cursor independently, quiesces the previous epoch
and serializes authority approvals. No production provisioning is performed.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .ontos_epoch_journal_core import Cursor, Journal, Snapshot, Update
from .ontos_v72_jcs import canonical_json, parse_json
from .ontos_v72_quorum import QuorumPolicy, QuorumCertificate, Vote, verify_quorum_review
from .ontos_v72_quorum_rotation import QuorumEpochPin, advance_quorum_pin, rotate_quorum
from .ontos_v72_witness import WitnessReceipt

MAX_REVIEW = 8192


def _shape(obj, keys):
    if type(obj) is not dict or set(obj) != set(keys):
        raise ValueError('unexpected event shape')


def _hex(raw, size=None, maximum=None):
    if (type(raw) is not str or not raw or len(raw) % 2
            or size is not None and len(raw) != size * 2
            or maximum is not None and len(raw) > maximum * 2
            or any(c not in '0123456789abcdef' for c in raw)):
        raise ValueError('invalid hex field')
    return bytes.fromhex(raw)


def _proof(items):
    if type(items) is not tuple or len(items) > 64 or any(type(x) is not bytes or len(x) != 32 for x in items):
        raise ValueError('bounded hash proof required')
    return [x.hex() for x in items]


def _parse_proof(items):
    if type(items) is not list or len(items) > 64:
        raise ValueError('bounded hash proof required')
    return tuple(_hex(x, 32) for x in items)


def _receipt(r):
    if (type(r) is not WitnessReceipt or type(r.revision) is not int or not 0 <= r.revision < 2**63
            or type(r.note) is not bytes or not 0 < len(r.note) <= 1024
            or type(r.challenge) is not bytes or len(r.challenge) != 32
            or type(r.signature) is not bytes or len(r.signature) != 64):
        raise ValueError('bounded receipt required')
    return {'revision': str(r.revision), 'note': r.note.hex(), 'challenge': r.challenge.hex(),
            'signature': r.signature.hex()}


def _parse_receipt(o):
    _shape(o, ('revision', 'note', 'challenge', 'signature'))
    rev = o['revision']
    if type(rev) is not str or not 0 < len(rev) <= 19 or not rev.isascii() or not rev.isdecimal() or str(int(rev)) != rev:
        raise ValueError('invalid revision')
    r = WitnessReceipt(int(rev), _hex(o['note'], maximum=1024), _hex(o['challenge'], 32), _hex(o['signature'], 64))
    _receipt(r)
    return r


def _certificate(c):
    if (type(c) is not QuorumCertificate or type(c.note) is not bytes or not 0 < len(c.note) <= 1024
            or type(c.votes) is not tuple or not 3 <= len(c.votes) <= 4
            or any(type(v) is not Vote or type(v.witness_key) is not bytes or len(v.witness_key) != 32 for v in c.votes)):
        raise ValueError('bounded quorum certificate required')
    return {'note': c.note.hex(), 'votes': [{'key': v.witness_key.hex(), 'receipt': _receipt(v.receipt)} for v in c.votes],
            'consistency': _proof(c.consistency)}


def _parse_certificate(o):
    _shape(o, ('note', 'votes', 'consistency'))
    if type(o['votes']) is not list or not 3 <= len(o['votes']) <= 4:
        raise ValueError('bounded votes required')
    votes = []
    for v in o['votes']:
        _shape(v, ('key', 'receipt'))
        votes.append(Vote(_hex(v['key'], 32), _parse_receipt(v['receipt'])))
    return QuorumCertificate(_hex(o['note'], maximum=1024), tuple(votes), _parse_proof(o['consistency']))


def _policy(p):
    if type(p) is not QuorumPolicy:
        raise ValueError('typed policy required')
    p.__post_init__()
    return {'environment': p.environment, 'origin': p.origin, 'log_name': p.log_name, 'log_key': p.log_key.hex(),
            'epoch': p.epoch, 'keys': [k.hex() for k in p.witness_keys]}


def _parse_policy(o):
    _shape(o, ('environment', 'origin', 'log_name', 'log_key', 'epoch', 'keys'))
    if type(o['keys']) is not list or len(o['keys']) != 4:
        raise ValueError('fixed roster required')
    return QuorumPolicy(o['environment'], o['origin'], o['log_name'], _hex(o['log_key'], 32), o['epoch'],
                        tuple(_hex(x, 32) for x in o['keys']))


@dataclass(frozen=True, slots=True)
class _State:
    pin: QuorumEpochPin
    challenges: tuple[bytes, ...]


def _bootstrap(pin: QuorumEpochPin) -> _State:
    if type(pin) is not QuorumEpochPin:
        raise ValueError('externally trusted quorum bootstrap required')
    pin.__post_init__()
    return _State(pin, (pin.last_challenge,))


def _state_digest(state: _State) -> bytes:
    return sha256(b'OMEGA-X/quorum-journal-state/v1\x00' + state.pin.digest()
                  + b''.join(state.challenges)).digest()


def _review_keys(data: bytes) -> tuple[bytes, ...]:
    obj = parse_json(data)
    _shape(obj, ('schema', 'level', 'commit_sha', 'tenant', 'manifest_sha256', 'campaign_sha256', 'gates'))
    if (obj['schema'] != 'omega-v75-witness-review-v1' or obj['level'] != 'L12'
            or canonical_json(obj) != data or type(obj['gates']) is not list or len(obj['gates']) != 8):
        raise ValueError('canonical v75 review leaf required')
    keys = []
    for i, gate in enumerate(obj['gates'], 1):
        _shape(gate, ('scope', 'key', 'receipt_sha256'))
        if type(gate['scope']) is not dict or gate['scope'].get('gate_id') != f'GATE-0{i}':
            raise ValueError('review gate order mismatch')
        keys.append(_hex(gate['key'], 32))
    return tuple(keys)


def _event(kind, challenge, **fields):
    if type(challenge) is not bytes or len(challenge) != 32:
        raise ValueError('32-byte challenge required')
    return canonical_json({'kind': kind, 'challenge': challenge.hex(), **fields})


def _transition(pin: QuorumEpochPin, payload: bytes) -> QuorumEpochPin | None:
    obj = parse_json(payload)
    if type(obj) is not dict or canonical_json(obj) != payload:
        raise ValueError('noncanonical event')
    kind = obj.get('kind')
    common = ('kind', 'challenge')
    if kind == 'rotate':
        _shape(obj, common + ('policy', 'old', 'new', 'authority'))
        return rotate_quorum(pin, _parse_policy(obj['policy']), _parse_certificate(obj['old']),
                             _parse_certificate(obj['new']), challenge=_hex(obj['challenge'], 32),
                             authority_signature=_hex(obj['authority'], 64))
    if kind == 'append':
        _shape(obj, common + ('certificate',))
    elif kind == 'review':
        _shape(obj, common + ('certificate', 'data', 'inclusion', 'evaluators'))
    else:
        raise ValueError('unknown quorum journal event')
    challenge = _hex(obj['challenge'], 32)
    certificate = _parse_certificate(obj['certificate'])
    if kind == 'review':
        if type(obj['evaluators']) is not list or len(obj['evaluators']) != 8:
            raise ValueError('bounded evaluator roster required')
        keys = tuple(_hex(k, 32) for k in obj['evaluators'])
        data = _hex(obj['data'], maximum=MAX_REVIEW)
        if keys != _review_keys(data) or pin.authority_key in keys or set(pin.retired_keys).intersection(keys):
            return None
        if not verify_quorum_review(data, pin.policy, pin.checkpoint,
                                    challenge, certificate, _parse_proof(obj['inclusion']), keys):
            return None
    return advance_quorum_pin(pin, certificate, challenge=challenge)


def _apply(state: _State, payload: bytes) -> _State | None:
    obj = parse_json(payload)
    if type(obj) is not dict or 'challenge' not in obj:
        raise ValueError('event challenge required')
    challenge = _hex(obj['challenge'], 32)
    if challenge in state.challenges:
        return None
    successor = _transition(state.pin, payload)
    return None if successor is None else _State(successor, (*state.challenges, challenge))


def _snapshot(s: Snapshot[_State]) -> Snapshot[QuorumEpochPin]:
    return Snapshot(s.cursor, s.state.pin)


def _update(u: Update[_State]) -> Update[QuorumEpochPin]:
    return Update(u.status, _snapshot(u.snapshot))


class QuorumEpochJournal:
    def __init__(self, path: Path, bootstrap: QuorumEpochPin):
        self._journal = Journal(path, _bootstrap(bootstrap), _state_digest, _apply)

    @classmethod
    def initialize(cls, path: Path, bootstrap: QuorumEpochPin) -> QuorumEpochJournal:
        Journal.initialize(path, _bootstrap(bootstrap), _state_digest, _apply)
        return cls(path, bootstrap)

    @property
    def genesis(self) -> Cursor:
        return self._journal.genesis

    def read(self, floor: Cursor) -> Snapshot[QuorumEpochPin]:
        return _snapshot(self._journal.read(floor))

    def append(self, expected: Cursor, certificate: QuorumCertificate, *, challenge: bytes) -> Update[QuorumEpochPin]:
        return _update(self._journal.append(expected, _event('append', challenge, certificate=_certificate(certificate))))

    def rotate(self, expected: Cursor, proposed: QuorumPolicy, old: QuorumCertificate, new: QuorumCertificate,
               *, challenge: bytes, authority_signature: bytes) -> Update[QuorumEpochPin]:
        if type(authority_signature) is not bytes or len(authority_signature) != 64:
            raise ValueError('bounded authority signature required')
        return _update(self._journal.append(expected, _event('rotate', challenge, policy=_policy(proposed),
                                    old=_certificate(old), new=_certificate(new), authority=authority_signature.hex())))

    def commit_review(self, expected: Cursor, data: bytes, certificate: QuorumCertificate,
                      inclusion: tuple[bytes, ...], evaluator_keys: tuple[bytes, ...], *, challenge: bytes) -> Update[QuorumEpochPin]:
        """Commit the exact authenticated review atomically, only for current epoch.

        The caller authenticates the evaluator evidence before supplying its leaf.
        COMMITTED is not production deployment; the new cursor must be retained.
        """
        if (type(data) is not bytes or not 0 < len(data) <= MAX_REVIEW
                or type(evaluator_keys) is not tuple or len(evaluator_keys) != 8
                or any(type(k) is not bytes or len(k) != 32 for k in evaluator_keys)):
            raise ValueError('bounded review and evaluator keys required')
        return _update(self._journal.append(expected, _event('review', challenge, certificate=_certificate(certificate),
                                    data=data.hex(), inclusion=_proof(inclusion), evaluators=[k.hex() for k in evaluator_keys])))
