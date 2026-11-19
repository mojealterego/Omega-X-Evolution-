"""Authenticated, crash-consistent generation commits for offline evolution.

The database and its parent directory must be controlled by the operator.
HMAC detects payload modification, not deletion or whole-database rollback.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3


MAX_PAYLOAD = 128 * 1024 * 1024
SCHEMA = 1


class CheckpointError(RuntimeError):
    """Checkpoint is incompatible, corrupted, unavailable or concurrently updated."""


class CheckpointStore:
    def __init__(self, path: Path, key: bytes):
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError('checkpoint key must contain at least 32 bytes')
        self.path = Path(path).absolute()
        self._key = key
        self._expected: tuple[int, bytes] | None = None

    @contextmanager
    def _connect(self):
        try:
            with closing(sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=5)) as conn:
                conn.execute('PRAGMA synchronous=FULL')
                conn.execute('PRAGMA trusted_schema=OFF')
                with conn:
                    yield conn
        except sqlite3.Error as exc:
            raise CheckpointError('checkpoint database operation failed') from exc

    def _mac(self, generation: int, payload: bytes) -> bytes:
        return hmac.digest(self._key, f'omega-checkpoint:{SCHEMA}:{generation}:'.encode() + payload, 'sha256')

    def _encode(self, generation: int, state: dict) -> tuple[bytes, bytes]:
        payload = json.dumps(state, allow_nan=False, separators=(',', ':')).encode('utf-8')
        if len(payload) > MAX_PAYLOAD:
            raise CheckpointError('checkpoint exceeds size limit')
        return payload, self._mac(generation, payload)

    def initialize(self, state: dict) -> None:
        payload, mac = self._encode(0, state)
        # O_EXCL prevents replacing an existing run (including a symlink).
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except OSError as exc:
            raise CheckpointError('cannot create new checkpoint; use a new path or resume') from exc
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('CREATE TABLE checkpoint (id INTEGER PRIMARY KEY CHECK(id=1), generation INTEGER NOT NULL CHECK(generation>=0), payload BLOB NOT NULL, mac BLOB NOT NULL)')
            conn.execute('INSERT INTO checkpoint VALUES (1,0,?,?)', (payload, mac))
        self._expected = (0, mac)

    def load(self) -> tuple[int, dict]:
        with self._connect() as conn:
            # Bound payload before materializing it in Python.
            row = conn.execute('SELECT generation, payload, mac FROM checkpoint WHERE id=1 AND typeof(payload)=\'blob\' AND length(payload)<=? AND typeof(mac)=\'blob\' AND length(mac)=32', (MAX_PAYLOAD,)).fetchone()
        if row is None:
            raise CheckpointError('missing or oversized checkpoint')
        generation, payload, mac = row
        if type(generation) is not int or generation < 0 or not hmac.compare_digest(mac, self._mac(generation, payload)):
            raise CheckpointError('checkpoint authentication failed')
        try:
            state = json.loads(payload)
        except (ValueError, RecursionError) as exc:
            raise CheckpointError('invalid checkpoint JSON') from exc
        if not isinstance(state, dict):
            raise CheckpointError('invalid checkpoint state')
        self._expected = (generation, mac)
        return generation, state

    def save(self, generation: int, state: dict) -> None:
        expected = self._expected
        if expected is None or generation != expected[0] + 1:
            raise CheckpointError('nonsequential checkpoint commit')
        payload, mac = self._encode(generation, state)
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            result = conn.execute('UPDATE checkpoint SET generation=?, payload=?, mac=? WHERE id=1 AND generation=? AND mac=?', (generation, payload, mac, *expected))
            if result.rowcount != 1:
                raise CheckpointError('checkpoint changed concurrently')
        self._expected = (generation, mac)
