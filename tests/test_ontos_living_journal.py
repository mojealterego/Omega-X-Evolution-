from dataclasses import replace
import sqlite3
import shutil
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_ontos_living_memory import batch, evidence, boundary
from omega_x_evolution.ontos_living_journal import LivingGenesis, LivingJournal
from omega_x_evolution.ontos_epoch_journal_core import IntegrityError
from omega_x_evolution.ontos_managed_journal import ManagedJournal


def fixture(tmp_path):
    b=batch(); p,t,h=evidence(b); bp,m,bh=boundary(p,b,h,True)
    g=LivingGenesis(b,p,p.sha256,t,h,bp,bp.sha256)
    a=tmp_path/'anchor'; s=tmp_path/'segments'; a.mkdir(mode=0o700);s.mkdir(mode=0o700)
    j=LivingJournal(a/'pin.db',s,g.sha256)
    return j,g,m,a,s


def advance(j,f,m):
    for msg in m:
        u=j.append(f,msg); assert u.status=='COMMITTED'; f=u.snapshot.fence
    return f


def test_durable_lockdown_and_compaction(tmp_path):
    j,g,m,a,s=fixture(tmp_path); f=j.initialize(g).fence
    assert j.diagnostic(f)['decision']=='QUARANTINED_BLOCKED'
    f=advance(j,f,m[:4]); assert j.diagnostic(f)['decision']=='QUARANTINED_DIAGNOSTIC'
    c=j.compact(f); assert c.status=='COMPACTED'
    assert j.verify_sealed(0).fence==f
    f=advance(j,c.snapshot.fence,m[4:]); reopened=LivingJournal(a/'pin.db',s,g.sha256)
    assert reopened.read(f).state.messages==m
    assert reopened.diagnostic(f)['decision']=='QUARANTINED_BLOCKED'
    assert not reopened.diagnostic(f)['promotion_authorized']
    with pytest.raises(IntegrityError): reopened.read(c.snapshot.fence)


def test_reject_bad_signature_stale_and_replay(tmp_path):
    j,g,m,_,_=fixture(tmp_path); f=j.initialize(g).fence
    assert j.append(f,replace(m[0],signature=b'\0'*64)).status=='REJECTED'
    f1=advance(j,f,m[:1]); assert j.append(f,m[0]).status=='STALE'
    assert j.append(f1,m[0]).status=='REJECTED'
    assert j.read(f1).state.messages==m[:1]


def test_concurrent_writers_single_commit(tmp_path):
    j,g,m,_,_=fixture(tmp_path); f=j.initialize(g).fence
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:j.append(f,m[0]),range(2)))
    assert sorted(x.status for x in results)==['COMMITTED','STALE']


def test_prepared_intent_recovery(tmp_path,monkeypatch):
    j,g,m,a,s=fixture(tmp_path); f=j.initialize(g).fence
    def crash(*args): raise RuntimeError('fault after segment commit')
    with monkeypatch.context() as mp:
        mp.setattr(ManagedJournal,'_finish',crash)
        with pytest.raises(RuntimeError): j.append(f,m[0])
    reopened=LivingJournal(a/'pin.db',s,g.sha256)
    recovered=reopened.recover_from_anchor()
    assert recovered.state.messages==m[:1]
    assert reopened.read(recovered.fence)==recovered
    with pytest.raises(IntegrityError): reopened.read(f)


def test_segment_tampering_and_joint_rollback(tmp_path):
    j,g,m,a,s=fixture(tmp_path); f=j.initialize(g).fence
    f1=advance(j,f,m[:1]); shutil.copy2(a/'pin.db',tmp_path/'old-anchor'); shutil.copy2(s/'segment-0000.db',tmp_path/'old-segment')
    f2=advance(j,f1,m[1:2])
    with sqlite3.connect(s/'segment-0000.db') as db: db.execute('UPDATE events SET payload=? WHERE sequence=2',(b'{}',))
    with pytest.raises(IntegrityError): j.read(f2)
    shutil.copy2(tmp_path/'old-anchor',a/'pin.db'); shutil.copy2(tmp_path/'old-segment',s/'segment-0000.db')
    with pytest.raises(IntegrityError): j.read(f2)
    assert j.read(f1).state.messages==m[:1]


def test_genesis_pin_and_corruption(tmp_path):
    j,g,m,a,s=fixture(tmp_path)
    with pytest.raises(ValueError): LivingJournal(a/'pin.db',s,'f'*64).initialize(g)
    with pytest.raises(ValueError): replace(g,evidence_head='f'*64).validate()
    f=j.initialize(g).fence
    with pytest.raises((IntegrityError,ValueError)): LivingJournal(a/'pin.db',s,'f'*64).read(f)
    with pytest.raises(ValueError): j.read(None)


def test_interrupted_rollover_recovered_without_reset(tmp_path,monkeypatch):
    j,g,m,a,s=fixture(tmp_path); f=advance(j,j.initialize(g).fence,m[:4])
    def crash(*args): raise RuntimeError('fault before segment activation')
    with monkeypatch.context() as mp:
        mp.setattr(ManagedJournal,'_activate',crash)
        with pytest.raises(RuntimeError): j.compact(f)
    reopened=LivingJournal(a/'pin.db',s,g.sha256)
    assert reopened.append(f,m[4]).status=='ROLLOVER_PENDING'
    c=reopened.compact(f); assert c.status=='COMPACTED'
    f2=advance(reopened,c.snapshot.fence,m[4:])
    assert reopened.diagnostic(f2)['decision']=='QUARANTINED_BLOCKED'


def test_exhausted_transcript_never_returns_approved_diagnostic(tmp_path,monkeypatch):
    from omega_x_evolution import ontos_living_journal as module
    monkeypatch.setattr(module,'MAX_MESSAGES',4)
    j,g,m,_,_=fixture(tmp_path); f=advance(j,j.initialize(g).fence,m[:4])
    assert j.append(f,m[4]).status=='REJECTED'
    assert j.diagnostic(f)['decision']=='QUARANTINED_BLOCKED'
    assert j.diagnostic(f)['diagnostic'] is None
    c=j.compact(f); assert c.status=='COMPACTED'
    assert j.diagnostic(c.snapshot.fence)['decision']=='QUARANTINED_BLOCKED'
