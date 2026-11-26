"""Fenced, independently anchored segmented journal for trusted replay code.

All writers must use this gateway. The anchor directory is an operator trust
boundary, not hardware tamper resistance. Linux flock serializes cooperating
processes; durable intents bridge the two SQLite commit domains. Segments are
sealed, never deleted. A separately retained exact Fence detects anchor rollback.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
from hashlib import sha256
import fcntl
import os
from pathlib import Path
import sqlite3
from typing import Callable, Generic, Literal, TypeVar

from .ontos_epoch_journal_core import Cursor, IntegrityError, Journal, MAX_EVENTS, _private, _payload

S = TypeVar('S')
MAX_STATE = 1024 * 1024
MAX_GENERATION = 1024
_DOMAIN = b'OMEGA-X/managed-journal/v1\x00'


@dataclass(frozen=True, slots=True)
class Fence:
    generation: int
    cursor: Cursor
    lineage: bytes

    def __post_init__(self):
        if (type(self.generation) is not int or not 0 <= self.generation <= MAX_GENERATION
                or type(self.cursor) is not Cursor or type(self.lineage) is not bytes
                or len(self.lineage) != 32):
            raise ValueError('invalid fence')
        self.cursor.__post_init__()


@dataclass(frozen=True, slots=True)
class ManagedSnapshot(Generic[S]):
    fence: Fence
    state: S


@dataclass(frozen=True, slots=True)
class ManagedUpdate(Generic[S]):
    status: Literal['COMMITTED', 'STALE', 'REJECTED', 'EXHAUSTED', 'COMPACTED']
    snapshot: ManagedSnapshot[S]


class ManagedJournal(Generic[S]):
    def __init__(self, anchor: Path, segments: Path, digest: Callable[[S], bytes],
                 replay: Callable[[S, bytes], S | None], encode: Callable[[S], bytes],
                 decode: Callable[[bytes], S]):
        self.anchor = Path(anchor).absolute()
        self.segments = Path(segments).resolve()
        parent = self.anchor.parent.resolve()
        if parent == self.segments or parent in self.segments.parents or self.segments in parent.parents:
            raise ValueError('anchor and segments require separate directories')
        self.digest, self.replay, self.encode, self.decode = digest, replay, encode, decode

    def _state_bytes(self, state: S) -> bytes:
        raw = self.encode(state)
        if (type(raw) is not bytes or not 0 < len(raw) <= MAX_STATE
                or self.digest(self.decode(raw)) != self.digest(state)
                or self.encode(self.decode(raw)) != raw):
            raise ValueError('bounded canonical state codec required')
        return raw

    def _segment(self, generation: int, raw: bytes) -> Journal[S]:
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_STATE:
            raise IntegrityError('invalid anchor bootstrap bytes')
        state = self.decode(raw)
        if self._state_bytes(state) != raw:
            raise IntegrityError('noncanonical bootstrap')
        return Journal(self._path(generation), state, self.digest, self.replay)

    def _path(self, generation: int) -> Path:
        if type(generation) is not int or not 0 <= generation <= MAX_GENERATION:
            raise IntegrityError('invalid generation')
        return self.segments / f'segment-{generation:04d}.db'

    @contextmanager
    def _locked(self):
        _private(self.anchor, file=True)
        fd = os.open(self.anchor, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            # Replacement of the protected anchor while running is unsupported.
            if os.fstat(fd).st_ino != self.anchor.stat().st_ino or os.fstat(fd).st_dev != self.anchor.stat().st_dev:
                raise IntegrityError('anchor identity changed')
            with closing(sqlite3.connect(self.anchor.as_uri() + '?mode=rw', uri=True,
                                         timeout=5, isolation_level=None)) as db:
                db.execute('PRAGMA trusted_schema=OFF')
                db.execute('PRAGMA synchronous=FULL')
                if db.execute('PRAGMA journal_mode').fetchone() != ('delete',):
                    raise IntegrityError('unexpected anchor journal mode')
                yield db
        finally:
            os.close(fd)

    def initialize(self, state: S) -> ManagedSnapshot[S]:
        raw = self._state_bytes(state)
        _private(self.anchor, file=False)
        _private(self._path(0), file=False)
        fd = os.open(self.anchor, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        with self._locked() as db:
            journal = Journal.initialize(self._path(0), state, self.digest, self.replay)
            lineage = sha256(_DOMAIN + b'genesis' + journal.genesis.digest).digest()
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE active(id INTEGER PRIMARY KEY CHECK(id=1), generation INTEGER NOT NULL, sequence INTEGER NOT NULL, digest BLOB NOT NULL, lineage BLOB NOT NULL, bootstrap BLOB NOT NULL)')
            db.execute('CREATE TABLE pending(id INTEGER PRIMARY KEY CHECK(id=1), payload BLOB NOT NULL, successor BLOB NOT NULL)')
            db.execute('CREATE TABLE sealed(generation INTEGER PRIMARY KEY, sequence INTEGER NOT NULL, digest BLOB NOT NULL, lineage BLOB NOT NULL, bootstrap BLOB NOT NULL)')
            db.execute('INSERT INTO active VALUES(1,0,0,?,?,?)', (journal.genesis.digest, lineage, raw))
            db.commit()
        fd = os.open(self.anchor.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return ManagedSnapshot(Fence(0, journal.genesis, lineage), state)

    def _active(self, db) -> tuple[Fence, bytes]:
        row = db.execute('SELECT generation,sequence,digest,lineage,CASE WHEN length(bootstrap)<=? THEN bootstrap END FROM active WHERE id=1', (MAX_STATE,)).fetchone()
        if row is None:
            raise IntegrityError('missing active anchor')
        try:
            fence = Fence(row[0], Cursor(row[1], row[2]), row[3])
        except ValueError as exc:
            raise IntegrityError('invalid active anchor') from exc
        return fence, row[4]

    def _finish(self, db, fence: Fence, successor: Cursor) -> None:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('UPDATE active SET sequence=?,digest=? WHERE id=1 AND generation=? AND sequence=? AND digest=? AND lineage=?',
                      (successor.sequence, successor.digest, fence.generation, fence.cursor.sequence,
                       fence.cursor.digest, fence.lineage)).rowcount != 1:
            raise IntegrityError('anchor CAS failed')
        if db.execute('DELETE FROM pending WHERE id=1').rowcount != 1:
            raise IntegrityError('missing prepared intent')
        db.commit()

    def _current(self, db):
        fence, raw = self._active(db)
        journal = self._segment(fence.generation, raw)
        actual = journal.read(fence.cursor)
        pending = db.execute('SELECT CASE WHEN length(payload)<=32768 THEN payload END,successor FROM pending WHERE id=1').fetchone()
        if pending is not None:
            payload, successor = pending
            _payload(payload)
            target = Cursor(fence.cursor.sequence + 1, successor)
            if actual.cursor == fence.cursor:
                predicted = journal._apply(actual, payload)
                if predicted is None or predicted.cursor != target:
                    raise IntegrityError('invalid prepared intent')
                result = journal.append(fence.cursor, payload)
                if result.status != 'COMMITTED':
                    raise IntegrityError('prepared append failed')
                actual = result.snapshot
            if actual.cursor != target:
                raise IntegrityError('journal diverges from prepared intent')
            self._finish(db, fence, target)
            fence = Fence(fence.generation, target, fence.lineage)
        if actual.cursor != fence.cursor:
            raise IntegrityError('unprepared journal append')
        return ManagedSnapshot(fence, actual.state), journal, raw

    def read(self, retained: Fence | None = None) -> ManagedSnapshot[S]:
        """Optionally require an exact independently retained current fence."""
        with self._locked() as db:
            snapshot, _, _ = self._current(db)
            if retained is not None and (type(retained) is not Fence or retained != snapshot.fence):
                raise IntegrityError('anchor differs from retained fence')
            return snapshot

    def append(self, expected: Fence, payload: bytes) -> ManagedUpdate[S]:
        if type(expected) is not Fence:
            raise ValueError('typed fence required')
        _payload(payload)
        with self._locked() as db:
            current, journal, _ = self._current(db)
            if expected != current.fence:
                return ManagedUpdate('STALE', current)
            if expected.cursor.sequence == MAX_EVENTS:
                return ManagedUpdate('EXHAUSTED', current)
            try:
                predicted = journal._apply(journal.read(expected.cursor), payload)
                if predicted is not None:
                    self._state_bytes(predicted.state)
            except (ValueError, TypeError, OverflowError, RecursionError):
                predicted = None
            if predicted is None:
                return ManagedUpdate('REJECTED', current)
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO pending VALUES(1,?,?)', (payload, predicted.cursor.digest))
            db.commit()
            successor, _, _ = self._current(db)
            return ManagedUpdate('COMMITTED', successor)

    def _activate(self, db, current: Fence, previous: bytes, successor: Fence, raw: bytes):
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO sealed VALUES(?,?,?,?,?)', (current.generation, current.cursor.sequence,
                    current.cursor.digest, current.lineage, previous))
        if db.execute('UPDATE active SET generation=?,sequence=0,digest=?,lineage=?,bootstrap=? WHERE id=1 AND generation=? AND sequence=? AND digest=? AND lineage=?',
                      (successor.generation, successor.cursor.digest, successor.lineage, raw,
                       current.generation, current.cursor.sequence, current.cursor.digest, current.lineage)).rowcount != 1:
            raise IntegrityError('segment activation CAS failed')
        db.commit()

    def compact(self, expected: Fence) -> ManagedUpdate[S]:
        """Seal active segment; create empty successor using complete trusted state."""
        if type(expected) is not Fence:
            raise ValueError('typed fence required')
        with self._locked() as db:
            current, _, previous = self._current(db)
            if expected != current.fence:
                return ManagedUpdate('STALE', current)
            if not expected.cursor.sequence:
                return ManagedUpdate('REJECTED', current)
            if expected.generation == MAX_GENERATION:
                return ManagedUpdate('EXHAUSTED', current)
            raw = self._state_bytes(current.state)
            gen = expected.generation + 1
            try:
                new = Journal.initialize(self._path(gen), current.state, self.digest, self.replay)
            except FileExistsError:
                # Recover only an exact empty, previously prepared successor.
                new = self._segment(gen, raw)
            if new.read(new.genesis).cursor != new.genesis:
                raise IntegrityError('successor segment is not empty')
            lineage = sha256(_DOMAIN + b'seal' + expected.lineage + expected.generation.to_bytes(4, 'big')
                             + expected.cursor.sequence.to_bytes(4, 'big') + expected.cursor.digest
                             + new.genesis.digest).digest()
            successor = Fence(gen, new.genesis, lineage)
            self._activate(db, expected, previous, successor, raw)
            return ManagedUpdate('COMPACTED', ManagedSnapshot(successor, current.state))

    def verify_sealed(self, generation: int) -> ManagedSnapshot[S]:
        """Replay an archived segment against its retained anchor seal."""
        self._path(generation)
        with self._locked() as db:
            row = db.execute('SELECT sequence,digest,lineage,CASE WHEN length(bootstrap)<=? THEN bootstrap END FROM sealed WHERE generation=?', (MAX_STATE, generation)).fetchone()
            if row is None:
                raise IntegrityError('generation is not sealed')
            fence = Fence(generation, Cursor(row[0], row[1]), row[2])
            actual = self._segment(generation, row[3]).read(fence.cursor)
            if actual.cursor != fence.cursor:
                raise IntegrityError('sealed segment changed')
            return ManagedSnapshot(fence, actual.state)
