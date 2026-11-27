"""Native gate/SQLite integration; source campaign and keys are test fixtures."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import shutil

import pytest

from test_ontos_v75_journal_gate import inputs, anchored, audit, CHALLENGE
from omega_x_evolution.ontos_managed_journal import Fence
from omega_x_evolution.ontos_managed_quorum import ManagedQuorumEpochJournal
from omega_x_evolution.ontos_epoch_journal_core import Cursor
from omega_x_evolution.ontos_v75_acceptance import ManagedJournalQuorumAnchorTrust
from omega_x_evolution.ontos_v75_anchor import AnchorEvidence


@pytest.fixture
def managed(tmp_path, anchored):
    _, _, evidence, pin, tip = anchored
    a=tmp_path/'anchor'; s=tmp_path/'segments'
    a.mkdir(mode=0o700); s.mkdir(mode=0o700)
    journal=ManagedQuorumEpochJournal(a/'floor.db',s)
    initial=journal.initialize(pin)
    return journal, ManagedJournalQuorumAnchorTrust(journal,initial.fence,CHALLENGE), evidence, tip, a, s


def fence(result):
    f=result['anchor_fence']
    return Fence(f['generation'],Cursor(f['sequence'],bytes.fromhex(f['digest'])),bytes.fromhex(f['lineage']))


def test_managed_commit_reopen_rollover_and_stale(inputs,managed):
    j,at,e,tip,a,s=managed
    result=audit(inputs,at,e,archive=True)
    assert all(x=='PASS' for x in result['gates'].values())
    assert result['anchor_status']=='PASS' and not result['release_authorized']
    assert 'anchor_cursor' not in result
    committed=fence(result)
    assert committed.generation==0 and committed.cursor.sequence==1
    reopened=ManagedQuorumEpochJournal(a/'floor.db',s)
    assert reopened.read(committed).state.checkpoint==tip
    compacted=reopened.compact(committed)
    assert compacted.status=='COMPACTED'
    assert reopened.verify_sealed(0).fence==committed
    for old in (at.expected,committed):
        r=audit(inputs,replace(at,journal=reopened,expected=old),e)
        assert r['gates']['GATE-09']=='BLOCKED' and r['anchor_fence'] is None
    r=audit(inputs,replace(at,journal=reopened,expected=compacted.snapshot.fence),e)
    assert r['gates']['GATE-09']=='FAIL' and r['anchor_fence'] is None
    assert reopened.read(compacted.snapshot.fence)==compacted.snapshot


def test_managed_missing_gate_and_wrong_proof_no_write(inputs,managed):
    j,at,e,_,_,_=managed
    subs=dict(inputs[-1]);subs.pop('GATE-06')
    r=audit(inputs,at,e,submissions=subs)
    assert r['gates']['GATE-09']=='BLOCKED' and r['anchor_fence'] is None
    wrong=replace(e,inclusion=())
    single=AnchorEvidence(e.certificate.votes[0].receipt,e.certificate.consistency,e.inclusion)
    for bad in (wrong,single):
        r=audit(inputs,at,bad)
        assert r['gates']['GATE-09']=='FAIL' and r['anchor_fence'] is None
    assert j.read(at.expected).fence==at.expected


def test_managed_concurrent_acceptance_single_commit(inputs,managed):
    j,at,e,_,_,_=managed
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:audit(inputs,at,e),range(2)))
    assert sorted(r['gates']['GATE-09'] for r in results)==['BLOCKED','PASS']
    winner=next(r for r in results if r['anchor_status']=='PASS')
    assert j.read(fence(winner)).fence.cursor.sequence==1
    assert all(not r['release_authorized'] for r in results)


def test_managed_joint_restore_and_missing_anchor_no_pass(inputs,managed,tmp_path):
    j,at,e,_,a,s=managed
    olda=tmp_path/'old-anchor'; olds=tmp_path/'old-segment'
    shutil.copy2(a/'floor.db',olda);shutil.copy2(s/'segment-0000.db',olds)
    result=audit(inputs,at,e); retained=fence(result)
    shutil.copy2(olda,a/'floor.db');shutil.copy2(olds,s/'segment-0000.db')
    r=audit(inputs,replace(at,expected=retained),e)
    assert r['gates']['GATE-09'] in ('FAIL','BLOCKED') and r['anchor_fence'] is None
    (a/'floor.db').unlink()
    r=audit(inputs,replace(at,expected=retained),e)
    assert r['gates']['GATE-09']=='BLOCKED' and r['anchor_fence'] is None


def test_managed_typed_trust_contract(managed):
    _,at,_,_,_,_=managed
    for changes in ({'journal':object()},{'expected':at.expected.cursor},{'challenge':b'short'}):
        with pytest.raises(ValueError): replace(at,**changes)
