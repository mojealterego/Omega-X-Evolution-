"""Bounded authenticated SQLite journal; caller retains an independent cursor.

The supplied deterministic replay function authenticates each transition.
The caller owns its code, bootstrap, private directory and external floor.
No keys are persisted here; joint rollback of all trust domains is excluded.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import sqlite3
import stat
from typing import Callable, Generic, Literal, TypeVar

S = TypeVar('S')
MAX_EVENTS = 256
MAX_EVENT = 32768
_DOMAIN = b'OMEGA-X/epoch-journal/v1/'


class IntegrityError(ValueError):
    """Journal cannot be authenticated against the external floor."""


@dataclass(frozen=True, slots=True)
class Cursor:
    sequence: int
    digest: bytes

    def __post_init__(self):
        if (type(self.sequence) is not int or not 0 <= self.sequence <= MAX_EVENTS
                or type(self.digest) is not bytes or len(self.digest) != 32):
            raise ValueError('invalid cursor')


@dataclass(frozen=True, slots=True)
class Snapshot(Generic[S]):
    cursor: Cursor
    state: S


@dataclass(frozen=True, slots=True)
class Update(Generic[S]):
    status: Literal['COMMITTED', 'STALE', 'REJECTED', 'EXHAUSTED']
    snapshot: Snapshot[S]


def _digest(value: bytes) -> bytes:
    if type(value) is not bytes or len(value) != 32:
        raise ValueError('32-byte state digest required')
    return value


def _payload(payload: bytes) -> None:
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_EVENT:
        raise ValueError('bounded event bytes required')


def next_cursor(parent: Cursor, payload: bytes, state_digest: bytes) -> Cursor:
    parent.__post_init__()
    _payload(payload)
    seq = parent.sequence + 1
    return Cursor(seq, sha256(_DOMAIN + b'event\x00' + seq.to_bytes(4, 'big')
                              + parent.digest + sha256(payload).digest()
                              + _digest(state_digest)).digest())


def _private(path: Path, *, file: bool) -> None:
    s = path.parent.stat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.geteuid() or s.st_mode & 0o077:
        raise PermissionError('private operator directory required')
    if file:
        s = path.lstat()
        if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.geteuid()
                or s.st_mode & 0o077 or s.st_nlink != 1):
            raise PermissionError('private regular journal required')


class Journal(Generic[S]):
    def __init__(self, path: Path, bootstrap: S, digest: Callable[[S], bytes],
                 replay: Callable[[S, bytes], S | None]):
        self.path = Path(path).absolute()
        self._bootstrap = bootstrap
        self._digest = digest
        self._replay = replay
        self.genesis = Cursor(0, sha256(_DOMAIN + b'genesis\x00' + _digest(digest(bootstrap))).digest())
        self.read(self.genesis)

    @classmethod
    def initialize(cls, path: Path, bootstrap: S, digest: Callable[[S], bytes],
                   replay: Callable[[S, bytes], S | None]) -> Journal[S]:
        genesis = sha256(_DOMAIN + b'genesis\x00' + _digest(digest(bootstrap))).digest()
        path = Path(path).absolute()
        _private(path, file=False)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        with closing(sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=5,
                                     isolation_level=None)) as db:
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE bootstrap(id INTEGER PRIMARY KEY CHECK(id=1), digest BLOB NOT NULL)')
            db.execute('INSERT INTO bootstrap VALUES(1,?)', (genesis,))
            db.execute('CREATE TABLE events(sequence INTEGER PRIMARY KEY CHECK(sequence>0), payload BLOB NOT NULL, digest BLOB NOT NULL)')
            db.commit()
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return cls(path, bootstrap, digest, replay)

    def _connect(self):
        _private(self.path, file=True)
        db = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=5, isolation_level=None)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA trusted_schema=OFF')
            if db.execute('PRAGMA journal_mode').fetchone() != ('delete',):
                raise IntegrityError('unexpected journal mode')
            return db
        except BaseException:
            db.close()
            raise

    def _apply(self, snapshot: Snapshot[S], payload: bytes) -> Snapshot[S] | None:
        _payload(payload)
        state = self._replay(snapshot.state, payload)
        if state is None:
            return None
        digest = _digest(self._digest(state))
        if digest == _digest(self._digest(snapshot.state)):
            return None
        return Snapshot(next_cursor(snapshot.cursor, payload, digest), state)

    def _scan(self, db, floor: Cursor) -> Snapshot[S]:
        if type(floor) is not Cursor:
            raise ValueError('external cursor required')
        floor.__post_init__()
        if (self.genesis.digest != sha256(_DOMAIN + b'genesis\x00' + _digest(self._digest(self._bootstrap))).digest()
                or db.execute('SELECT CASE WHEN length(digest)=32 THEN digest END FROM bootstrap WHERE id=1').fetchone() != (self.genesis.digest,)):
            raise IntegrityError('bootstrap mismatch')
        snapshot = Snapshot(self.genesis, self._bootstrap)
        matched = floor == snapshot.cursor
        rows = db.execute('SELECT sequence,CASE WHEN length(payload)<=? THEN payload END,CASE WHEN length(digest)=32 THEN digest END FROM events ORDER BY sequence LIMIT ?', (MAX_EVENT, MAX_EVENTS + 1))
        for seq, payload, digest in rows:
            try:
                if type(seq) is not int or seq != snapshot.cursor.sequence + 1 or seq > MAX_EVENTS:
                    raise ValueError('invalid sequence')
                successor = self._apply(snapshot, payload)
                if successor is None or successor.cursor.digest != digest:
                    raise ValueError('invalid transition or digest')
                snapshot = successor
            except (ValueError, TypeError, OverflowError, RecursionError) as exc:
                raise IntegrityError('journal replay failed') from exc
            matched = matched or floor == snapshot.cursor
        if not matched:
            raise IntegrityError('journal behind or divergent from retained floor')
        return snapshot

    def read(self, floor: Cursor) -> Snapshot[S]:
        with closing(self._connect()) as db:
            db.execute('BEGIN')
            return self._scan(db, floor)

    def append(self, expected: Cursor, payload: bytes) -> Update[S]:
        _payload(payload)
        with closing(self._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            current = self._scan(db, expected)
            if current.cursor != expected:
                return Update('STALE', current)
            if current.cursor.sequence == MAX_EVENTS:
                return Update('EXHAUSTED', current)
            try:
                successor = self._apply(current, payload)
            except (ValueError, TypeError, OverflowError, RecursionError):
                successor = None
            if successor is None:
                return Update('REJECTED', current)
            db.execute('INSERT INTO events VALUES(?,?,?)', (successor.cursor.sequence, payload, successor.cursor.digest))
            db.commit()
            return Update('COMMITTED', successor)
