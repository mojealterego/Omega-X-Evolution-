from hashlib import sha256
from pathlib import Path
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from omega_x_evolution.ontos_epoch_journal_core import IntegrityError
from omega_x_evolution.ontos_managed_journal import ManagedJournal, Fence


def digest(state):
    return sha256(state).digest()


def replay(state, payload):
    if payload == b'reject':
        return None
    return state + payload


def manager(anchor, segments):
    return ManagedJournal(anchor, segments, digest, replay, bytes, bytes)


@pytest.fixture
def env(tmp_path):
    anchor_dir = tmp_path / 'anchor'; anchor_dir.mkdir(mode=0o700)
    segments = tmp_path / 'segments'; segments.mkdir(mode=0o700)
    anchor = anchor_dir / 'floor.db'
    m = manager(anchor, segments)
    return m, m.initialize(b'genesis'), anchor, segments


def test_fencing_rejects_stale_append_and_rollover(env):
    m, initial, *_ = env
    result = m.append(initial.fence, b'a')
    assert result.status == 'COMMITTED'
    assert m.append(initial.fence, b'b').status == 'STALE'
    assert m.compact(initial.fence).status == 'STALE'
    assert m.read().state == b'genesisa'


def test_separate_anchor_detects_restored_journal(env):
    m, initial, _, segments = env
    path = next(segments.glob('*.db'))
    backup = path.read_bytes()
    result = m.append(initial.fence, b'a')
    path.write_bytes(backup)
    with pytest.raises(IntegrityError):
        m.read()
    with pytest.raises(IntegrityError):
        m.append(result.snapshot.fence, b'b')


def test_compaction_preserves_state_and_archive(env):
    m, initial, anchor, segments = env
    first = m.append(initial.fence, b'a').snapshot
    old = next(segments.glob('*.db'))
    prior = old.read_bytes()
    rolled = m.compact(first.fence)
    assert rolled.status == 'COMPACTED'
    assert rolled.snapshot.fence.generation == 1
    assert rolled.snapshot.fence.cursor.sequence == 0
    assert rolled.snapshot.state == first.state
    assert old.read_bytes() == prior
    assert m.append(first.fence, b'x').status == 'STALE'
    reopened = manager(anchor, segments)
    assert reopened.read() == rolled.snapshot
    assert reopened.append(rolled.snapshot.fence, b'b').snapshot.state == b'genesisab'


def test_concurrent_cas(env):
    m, initial, anchor, segments = env
    def worker(data):
        return manager(anchor, segments).append(initial.fence, data).status
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(worker, (b'a', b'b'))) == ['COMMITTED', 'STALE']


def test_reject_does_not_change_floor(env):
    m, initial, *_ = env
    assert m.append(initial.fence, b'reject').status == 'REJECTED'
    assert m.read() == initial


def test_crash_after_journal_commit_recovers_prepared_intent(env, monkeypatch):
    m, initial, anchor, segments = env
    def fail(*args):
        raise RuntimeError('after journal commit')
    monkeypatch.setattr(m, '_finish', fail)
    with pytest.raises(RuntimeError):
        m.append(initial.fence, b'a')
    restored = manager(anchor, segments).read()
    assert restored.state == b'genesisa'
    assert restored.fence.cursor.sequence == 1


def test_crash_before_journal_commit_recovers_prepared_intent(env, monkeypatch):
    m, initial, anchor, segments = env
    from omega_x_evolution.ontos_epoch_journal_core import Journal
    original = Journal.append
    def fail(*args):
        raise RuntimeError('before journal commit')
    monkeypatch.setattr(Journal, 'append', fail)
    with pytest.raises(RuntimeError):
        m.append(initial.fence, b'a')
    monkeypatch.setattr(Journal, 'append', original)
    assert manager(anchor, segments).read().state == b'genesisa'


def test_compaction_orphan_recovery(env, monkeypatch):
    m, initial, anchor, segments = env
    first = m.append(initial.fence, b'a').snapshot
    def fail(*args):
        raise RuntimeError('after new segment creation')
    monkeypatch.setattr(m, '_activate', fail)
    with pytest.raises(RuntimeError):
        m.compact(first.fence)
    reopened = manager(anchor, segments)
    assert reopened.read() == first
    assert reopened.compact(first.fence).status == 'COMPACTED'


def test_unprepared_append_detected(env):
    m, initial, _, segments = env
    from omega_x_evolution.ontos_epoch_journal_core import Journal
    journal = Journal(next(segments.glob('*.db')), b'genesis', digest, replay)
    assert journal.append(initial.fence.cursor, b'outside').status == 'COMMITTED'
    with pytest.raises(IntegrityError):
        m.read()


def test_anchor_rollback_detected_by_retained_fence(env):
    m, initial, anchor, segments = env
    before = anchor.read_bytes()
    first = m.append(initial.fence, b'a').snapshot
    rolled = m.compact(first.fence).snapshot
    anchor.write_bytes(before)
    with pytest.raises(IntegrityError):
        manager(anchor, segments).read(rolled.fence)


def test_empty_compaction_rejected(env):
    m, initial, *_ = env
    assert m.compact(initial.fence).status == 'REJECTED'


def test_anchor_and_segments_must_be_separate(tmp_path):
    with pytest.raises(ValueError):
        manager(tmp_path / 'floor.db', tmp_path)


def test_full_segment_rolls_over_without_losing_state(env):
    from omega_x_evolution.ontos_epoch_journal_core import MAX_EVENTS
    m, initial, *_ = env
    snap = initial
    for _ in range(MAX_EVENTS):
        snap = m.append(snap.fence, b'x').snapshot
    assert m.append(snap.fence, b'x').status == 'EXHAUSTED'
    assert m.compact(snap.fence).status == 'COMPACTED'
    assert m.verify_sealed(0) == snap
    assert m.append(m.read().fence, b'y').snapshot.state == snap.state + b'y'


def test_sealed_archive_tampering_detected(env):
    m, initial, _, segments = env
    snap = m.append(initial.fence, b'a').snapshot
    m.compact(snap.fence)
    assert m.verify_sealed(0) == snap
    with sqlite3.connect(segments / 'segment-0000.db') as db:
        db.execute("UPDATE events SET payload=X'62' WHERE sequence=1")
    with pytest.raises(IntegrityError):
        m.verify_sealed(0)


@pytest.mark.parametrize('phase', ['before', 'after'])
def test_process_exit_at_commit_boundary(env, phase):
    import os
    import subprocess
    import sys
    m, initial, anchor, segments = env
    code = '''
from pathlib import Path
import os, sys
from hashlib import sha256
from omega_x_evolution.ontos_managed_journal import ManagedJournal
from omega_x_evolution.ontos_epoch_journal_core import Journal
m = ManagedJournal(Path(sys.argv[1]), Path(sys.argv[2]), lambda s: sha256(s).digest(), lambda s,p:s+p, bytes, bytes)
fence = m.read().fence
if sys.argv[3] == 'before':
    Journal.append = lambda *args: os._exit(23)
else:
    m._finish = lambda *args: os._exit(23)
m.append(fence, b'a')
'''
    child = subprocess.run([sys.executable, '-c', code, str(anchor), str(segments), phase], timeout=10)
    assert child.returncode == 23
    snap = m.read()
    assert snap.state == b'genesisa' and snap.fence.cursor.sequence == 1
    assert m.read() == snap


def test_multiple_generations_keep_distinct_fences(env):
    m, initial, *_ = env
    snap = initial
    for i in range(3):
        committed = m.append(snap.fence, bytes([65+i])).snapshot
        snap = m.compact(committed.fence).snapshot
        assert m.verify_sealed(i) == committed
    assert snap.state == b'genesisABC'
    assert snap.fence.generation == 3
    assert m.append(initial.fence, b'old').status == 'STALE'


def test_orphan_rollover_fences_old_generation(env, monkeypatch):
    m, initial, anchor, segments = env
    first = m.append(initial.fence, b'a').snapshot
    def fail(*args):
        raise RuntimeError('after new segment creation')
    monkeypatch.setattr(m, '_activate', fail)
    with pytest.raises(RuntimeError):
        m.compact(first.fence)
    reopened = manager(anchor, segments)
    assert reopened.append(first.fence, b'b').status == 'ROLLOVER_PENDING'
    assert reopened.read() == first
    rolled = reopened.compact(first.fence).snapshot
    assert reopened.append(first.fence, b'b').status == 'STALE'
    assert reopened.append(rolled.fence, b'b').snapshot.state == b'genesisab'
