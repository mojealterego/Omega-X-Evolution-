"""Canonical bounded binary storage record for complete quorum epoch state.

This is a structural codec, not a signature or point verifier. A trusted
journal adapter must reconstruct and validate the existing QuorumEpochPin,
then authenticate the state against its retained fence before use.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
import struct

MAX_STATE = 1024 * 1024
MAX_CHALLENGES = 32000
MAX_RETIRED = 128
_MAGIC = b'OQS\x01'
_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,254}\Z', re.ASCII)
_EMPTY = sha256(b'').digest()


def _name(value: str) -> bytes:
    if type(value) is not str or not _NAME.fullmatch(value):
        raise ValueError('invalid quorum name')
    return value.encode('ascii')


def _key(value: bytes) -> bool:
    return type(value) is bytes and len(value) == 32


def _integer(value: int, stop: int) -> bool:
    return type(value) is int and 0 <= value < stop


def _vector(value: tuple[bytes, ...], low: int, high: int) -> bool:
    return (type(value) is tuple and low <= len(value) <= high
            and all(_key(x) for x in value) and len(set(value)) == len(value))


@dataclass(frozen=True, slots=True)
class QuorumStateRecord:
    environment: str
    origin: str
    log_name: str
    log_key: bytes
    epoch: int
    witness_keys: tuple[bytes, ...]
    tree_size: int
    root: bytes
    authority_key: bytes
    retired_keys: tuple[bytes, ...]
    challenges: tuple[bytes, ...]

    @property
    def last_challenge(self) -> bytes:
        return self.challenges[-1]

    def validate(self) -> None:
        _name(self.origin)
        _name(self.log_name)
        if (type(self.environment) is not str or self.environment not in ('simulation', 'operational')
                or not _integer(self.epoch, 2**31) or not _integer(self.tree_size, 2**63)
                or not all(_key(x) for x in (self.log_key, self.root, self.authority_key))
                or self.tree_size == 0 and self.root != _EMPTY
                or not _vector(self.witness_keys, 4, 4)
                or not _vector(self.retired_keys, 0, MAX_RETIRED)
                or not _vector(self.challenges, 1, MAX_CHALLENGES)):
            raise ValueError('invalid bounded quorum state')
        active = (self.log_key, self.authority_key, *self.witness_keys)
        if (len(set(active)) != len(active) or set(active).intersection(self.retired_keys)
                or tuple(sorted(self.witness_keys)) != self.witness_keys
                or tuple(sorted(self.retired_keys)) != self.retired_keys):
            raise ValueError('invalid quorum key roles or ordering')


def encode_state(state: QuorumStateRecord) -> bytes:
    if type(state) is not QuorumStateRecord:
        raise ValueError('typed quorum state required')
    state.validate()
    origin, name = _name(state.origin), _name(state.log_name)
    raw = b''.join((_MAGIC, bytes([state.environment == 'operational', len(origin), len(name)]),
                    origin, name, struct.pack('>IQ', state.epoch, state.tree_size),
                    state.log_key, state.root, state.authority_key, *state.witness_keys,
                    bytes([len(state.retired_keys)]), *state.retired_keys,
                    struct.pack('>I', len(state.challenges)), *state.challenges))
    if len(raw) > MAX_STATE:
        raise ValueError('quorum state exceeds byte budget')
    return raw


class _Reader:
    def __init__(self, raw: bytes):
        self.raw = raw
        self.offset = 0

    def take(self, n: int) -> bytes:
        end = self.offset + n
        if end > len(self.raw):
            raise ValueError('truncated quorum state')
        value = self.raw[self.offset:end]
        self.offset = end
        return value

    def vector(self, n: int, low: int, high: int) -> tuple[bytes, ...]:
        if not low <= n <= high or n * 32 > len(self.raw) - self.offset:
            raise ValueError('invalid quorum vector length')
        return tuple(self.take(32) for _ in range(n))


def decode_state(raw: bytes) -> QuorumStateRecord:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_STATE:
        raise ValueError('bounded quorum state bytes required')
    r = _Reader(raw)
    if r.take(len(_MAGIC)) != _MAGIC:
        raise ValueError('unknown quorum state version')
    env, origin_len, name_len = r.take(3)
    if env not in (0, 1):
        raise ValueError('invalid quorum environment')
    try:
        origin = r.take(origin_len).decode('ascii')
        name = r.take(name_len).decode('ascii')
    except UnicodeError as exc:
        raise ValueError('invalid quorum name encoding') from exc
    epoch, size = struct.unpack('>IQ', r.take(12))
    log, root, authority = r.take(32), r.take(32), r.take(32)
    witnesses = r.vector(4, 4, 4)
    retired = r.vector(r.take(1)[0], 0, MAX_RETIRED)
    count, = struct.unpack('>I', r.take(4))
    challenges = r.vector(count, 1, MAX_CHALLENGES)
    if r.offset != len(raw):
        raise ValueError('trailing quorum state data')
    state = QuorumStateRecord('operational' if env else 'simulation', origin, name, log,
                              epoch, witnesses, size, root, authority, retired, challenges)
    state.validate()
    return state
