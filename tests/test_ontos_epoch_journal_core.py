from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
import shutil
import sqlite3
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.exceptions import InvalidSignature

from omega_x_evolution.ontos_epoch_journal_core import Journal, IntegrityError

# Independent signed transition contract for exercising the real storage engine.
# Public test fixture, not an operational quorum or a production key.
KEY = Ed25519PrivateKey.from_private_bytes(b'\x19' * 32)
PUB = KEY.public_key()
BOOT = b'genesis'


def digest(state):
    return sha256(state).digest()


def replay(state, payload):
    if len(payload) < 65:
        return None
    signature, successor = payload[:64], payload[64:]
    try:
        PUB.verify(signature, b'journal-test-v1\x00' + digest(state) + successor)
    except InvalidSignature:
        return None
    return successor if state != successor else None


def event(state, successor):
    return KEY.sign(b'journal-test-v1\x00' + digest(state) + successor) + successor


@pytest.fixture
def store(tmp_path):
    tmp_path.chmod(0o700)
    return Journal.initialize(tmp_path / 'state.db', BOOT, digest, replay)


def test_append_reopen_and_stale_cursor(store):
    base = store.genesis
    first = store.append(base, event(BOOT, b'one'))
    assert first.status == 'COMMITTED' and first.snapshot.state == b'one'
    reopened = Journal(store.path, BOOT, digest, replay)
    assert reopened.read(first.snapshot.cursor) == first.snapshot
    assert reopened.read(base) == first.snapshot
    assert reopened.append(base, event(BOOT, b'other')).status == 'STALE'
    assert reopened.append(first.snapshot.cursor, event(b'one', b'two')).snapshot.state == b'two'


def test_invalid_event_does_not_change_state(store):
    before = store.read(store.genesis)
    assert store.append(before.cursor, b'x' * 64).status == 'REJECTED'
    assert store.append(before.cursor, event(b'other', b'one')).status == 'REJECTED'
    assert store.read(before.cursor) == before


def test_two_competing_writers_commit_exactly_one(store):
    base = store.genesis
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda x: store.append(base, event(BOOT, x)), (b'A', b'B')))
    assert sorted(r.status for r in results) == ['COMMITTED', 'STALE']
    assert store.read(base).cursor.sequence == 1


def test_restored_backup_rejected_against_retained_floor(store, tmp_path):
    backup = tmp_path / 'backup.db'
    shutil.copyfile(store.path, backup)
    result = store.append(store.genesis, event(BOOT, b'one'))
    shutil.copyfile(backup, store.path)
    with pytest.raises(IntegrityError):
        store.read(result.snapshot.cursor)


@pytest.mark.parametrize('sql', [
    "UPDATE events SET payload=x'00'", "UPDATE events SET digest=zeroblob(32)",
    "UPDATE events SET sequence=2", "UPDATE bootstrap SET digest=zeroblob(32)",
])
def test_tampered_storage_is_rejected(store, sql):
    store.append(store.genesis, event(BOOT, b'one'))
    with sqlite3.connect(store.path) as db:
        db.execute(sql)
    with pytest.raises(IntegrityError):
        store.read(store.genesis)


def test_wrong_bootstrap_and_divergent_floor(store):
    with pytest.raises(IntegrityError):
        Journal(store.path, b'wrong', digest, replay)
    with pytest.raises(IntegrityError):
        store.read(replace(store.genesis, digest=b'x' * 32))


def test_unsafe_path_and_implicit_initialization(store, tmp_path):
    link = tmp_path / 'link.db'
    link.symlink_to(store.path)
    with pytest.raises(PermissionError):
        Journal(link, BOOT, digest, replay)
    with pytest.raises(FileNotFoundError):
        Journal(tmp_path / 'missing.db', BOOT, digest, replay)
    with pytest.raises(FileExistsError):
        Journal.initialize(store.path, BOOT, digest, replay)


def test_event_size_and_cursor_bounds(store):
    for payload in (b'', b'x' * 32769, bytearray(b'x')):
        with pytest.raises(ValueError):
            store.append(store.genesis, payload)
    with pytest.raises(ValueError):
        replace(store.genesis, sequence=True)


@pytest.mark.parametrize('after_commit', [False, True])
def test_process_exit_during_sqlite_transaction(store, after_commit):
    before = store.read(store.genesis)
    payload = event(BOOT, b'one')
    # Execute real SQLite transaction in a child, kill process at the selected
    # boundary, then replay the actual journal. Digest calculated by core.
    code = '''
import os, sqlite3, sys
from omega_x_evolution.ontos_epoch_journal_core import next_cursor, Cursor
from hashlib import sha256
path, raw, parent, commit = sys.argv[1:]
payload = bytes.fromhex(raw)
cur = next_cursor(Cursor(0, bytes.fromhex(parent)), payload, sha256(b'one').digest())
db = sqlite3.connect(path, isolation_level=None)
db.execute('PRAGMA synchronous=FULL')
db.execute('BEGIN IMMEDIATE')
db.execute('INSERT INTO events VALUES(?,?,?)', (cur.sequence, payload, cur.digest))
if commit == 'yes': db.commit()
os._exit(23)
'''
    run = subprocess.run([sys.executable, '-c', code, str(store.path), payload.hex(),
                          before.cursor.digest.hex(), 'yes' if after_commit else 'no'])
    assert run.returncode == 23
    recovered = Journal(store.path, BOOT, digest, replay).read(before.cursor)
    assert recovered.state == (b'one' if after_commit else BOOT)
    assert recovered.cursor.sequence == int(after_commit)


def test_full_journal_budget_replays_and_cannot_grow(store):
    from omega_x_evolution.ontos_epoch_journal_core import MAX_EVENTS, next_cursor
    cursor, state = store.genesis, BOOT
    with sqlite3.connect(store.path) as db:
        for i in range(MAX_EVENTS):
            successor = f'state-{i}'.encode()
            payload = event(state, successor)
            cursor = next_cursor(cursor, payload, digest(successor))
            db.execute('INSERT INTO events VALUES(?,?,?)', (cursor.sequence, payload, cursor.digest))
            state = successor
    assert store.read(cursor).state == state
    result = store.append(cursor, event(state, b'overflow'))
    assert result.status == 'EXHAUSTED' and result.snapshot.cursor == cursor


def test_oversized_persisted_payload_fails_closed(store):
    with sqlite3.connect(store.path) as db:
        db.execute('INSERT INTO events VALUES(1,?,?)', (b'x' * 32769, b'x' * 32))
    with pytest.raises(IntegrityError):
        store.read(store.genesis)
