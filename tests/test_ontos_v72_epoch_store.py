"""Native SQLite client epoch journal; public deterministic fixture keys only."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import sqlite3
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from omega_x_evolution.ontos_v72_checkpoint_note import Checkpoint, sign_note
from omega_x_evolution.ontos_v72_merkle import leaf_hash, merkle_root, consistency_proof
from omega_x_evolution.ontos_v72_rotation import EpochPin, rotation_bytes
from omega_x_evolution.ontos_v72_witness import WitnessPolicy, WitnessStore
from omega_x_evolution.ontos_v72_epoch_store import EpochStore, EpochIntegrityError, genesis_cursor

ROOT, LOG, WIT, NEW_LOG, NEW_WIT = (Ed25519PrivateKey.from_private_bytes(bytes([i])*32) for i in range(31,36))
ORIGIN='omega/client-epoch'
LEAVES=tuple(leaf_hash(str(i).encode()) for i in range(4))


def policy(log=LOG,wit=WIT):
    return WitnessPolicy('simulation',ORIGIN,ORIGIN,log.public_key().public_bytes_raw(),wit.public_key().public_bytes_raw())


def note(leaves,log=LOG):
    return sign_note(Checkpoint(ORIGIN,len(leaves),merkle_root(leaves)),ORIGIN,log)


@pytest.fixture
def env(tmp_path):
    witness=WitnessStore.initialize(tmp_path/'witness.db',policy(),WIT,note(LEAVES[:1]))
    pin=EpochPin(0,policy(),ROOT.public_key().public_bytes_raw(),witness.read(b'a'*32),())
    path=tmp_path/'client.db'
    store=EpochStore.initialize(path,pin)
    return path,store,pin,witness


def advance(env):
    path,store,pin,witness=env
    proof=consistency_proof(LEAVES[:2],1)
    assert witness.advance(note(LEAVES[:2]),proof,expected_revision=0)=='ADVANCED'
    result=store.append(genesis_cursor(pin),witness.read(b'b'*32),proof,challenge=b'b'*32)
    assert result.status=='ADVANCED'
    return result.snapshot


def test_durable_append_and_noop(env):
    path,store,pin,witness=env
    first=advance(env)
    assert first.cursor.sequence==1
    reopened=EpochStore(path,pin)
    assert reopened.read(first.cursor)==first
    result=reopened.append(first.cursor,witness.read(b'c'*32),(),challenge=b'c'*32)
    assert result.status=='UNCHANGED' and result.snapshot==first
    result=reopened.append(first.cursor,witness.read(b'd'*32),(),challenge=b'e'*32)
    assert result.status=='REJECTED' and reopened.read(first.cursor)==first


def test_rotation_persists_epoch_and_rejects_old_policy(env,tmp_path):
    path,store,pin,witness=env
    first=advance(env)
    proposed=policy(NEW_LOG,NEW_WIT)
    next_witness=WitnessStore.initialize(tmp_path/'next.db',proposed,NEW_WIT,note(LEAVES[:2],NEW_LOG))
    challenge=b'c'*32
    old_tip,new_tip=witness.read(challenge),next_witness.read(challenge)
    signature=ROOT.sign(rotation_bytes(first.pin,proposed,old_tip,new_tip,challenge))
    result=store.rotate(first.cursor,proposed,old_tip,new_tip,(),challenge=challenge,authority_signature=signature)
    assert result.status=='ROTATED' and result.snapshot.pin.epoch==1
    current=result.snapshot
    reopened=EpochStore(path,pin)
    assert reopened.read(current.cursor)==current
    assert reopened.rotate(first.cursor,proposed,old_tip,new_tip,(),challenge=challenge,authority_signature=signature).status=='STALE'
    assert reopened.append(current.cursor,witness.read(b'd'*32),(),challenge=b'd'*32).status=='REJECTED'
    proof=consistency_proof(LEAVES,2)
    assert next_witness.advance(note(LEAVES,NEW_LOG),proof,expected_revision=0)=='ADVANCED'
    result=reopened.append(current.cursor,next_witness.read(b'e'*32),proof,challenge=b'e'*32)
    assert result.status=='ADVANCED' and result.snapshot.pin.epoch==1


def test_restored_client_snapshot_rejected_against_external_cursor(env):
    path,store,pin,_=env
    old=path.read_bytes()
    first=advance(env)
    path.write_bytes(old)
    reopened=EpochStore(path,pin)
    with pytest.raises(EpochIntegrityError): reopened.read(first.cursor)
    assert reopened.read(genesis_cursor(pin)).pin==pin


def test_tamper_and_wrong_genesis_fail_closed(env):
    path,store,pin,_=env
    first=advance(env)
    with sqlite3.connect(path) as db:
        db.execute('UPDATE events SET payload=? WHERE sequence=1',(b'{}',))
    with pytest.raises(EpochIntegrityError): store.read(first.cursor)
    with pytest.raises(EpochIntegrityError): EpochStore(path,replace(pin,epoch=1))


def test_two_competing_updates_use_cas(env):
    path,store,pin,witness=env
    proof=consistency_proof(LEAVES[:2],1)
    assert witness.advance(note(LEAVES[:2]),proof,expected_revision=0)=='ADVANCED'
    receipts=[witness.read(b'b'*32),witness.read(b'c'*32)]
    expected=genesis_cursor(pin)
    def submit(receipt):
        return EpochStore(path,pin).append(expected,receipt,proof,challenge=receipt.challenge)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(submit,receipts))
    assert sorted(r.status for r in results)==['ADVANCED','STALE']
    assert store.read(expected).cursor.sequence==1


def test_process_crash_before_commit(env):
    path,store,pin,_=env
    first=advance(env)
    code='import sqlite3,sys,os;c=sqlite3.connect(sys.argv[1]);c.execute("BEGIN IMMEDIATE");c.execute("DELETE FROM events");os._exit(93)'
    assert subprocess.run([sys.executable,'-c',code,str(path)],timeout=10).returncode==93
    assert EpochStore(path,pin).read(first.cursor)==first


def test_missing_store_cannot_auto_reinitialize(env):
    path,store,pin,_=env
    with pytest.raises(FileExistsError): EpochStore.initialize(path,pin)
    path.unlink()
    with pytest.raises(FileNotFoundError): EpochStore(path,pin)


def test_replay_recovers_commit_before_lost_reply(env):
    path,store,pin,witness=env
    proof=consistency_proof(LEAVES[:2],1)
    assert witness.advance(note(LEAVES[:2]),proof,expected_revision=0)=='ADVANCED'
    code='''import os,sys,runpy
from pathlib import Path
m=runpy.run_path('tests/test_ontos_v72_epoch_store.py')
p=m['policy'](); w=m['WitnessStore'](Path(sys.argv[2]),p,m['WIT'])
from omega_x_evolution.ontos_v72_witness import WitnessReceipt,_message
n=m['note'](m['LEAVES'][:1]); ch=b'a'*32
r=WitnessReceipt(0,n,ch,m['WIT'].sign(_message(p,0,n,ch)))
pin=m['EpochPin'](0,p,m['ROOT'].public_key().public_bytes_raw(),r,())
s=m['EpochStore'](Path(sys.argv[1]),pin)
assert s.append(m['genesis_cursor'](pin),w.read(b'b'*32),m['consistency_proof'](m['LEAVES'][:2],1),challenge=b'b'*32).status=='ADVANCED'
os._exit(94)
'''
    assert subprocess.run([sys.executable,'-c',code,str(path),str(path.parent/'witness.db')],timeout=15).returncode==94
    recovered=EpochStore(path,pin).read(genesis_cursor(pin))
    assert recovered.cursor.sequence==1 and recovered.pin.receipt.revision==1
