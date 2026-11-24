import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from omega_x_evolution.ontos_v72_checkpoint_note import Checkpoint, sign_note
from omega_x_evolution.ontos_v72_merkle import leaf_hash, merkle_root, consistency_proof
from omega_x_evolution.ontos_v72_witness import (
    WitnessPolicy, WitnessStore, verify_witness, provision_key, load_key,
)

LOG = Ed25519PrivateKey.from_private_bytes(bytes([11])*32)
WIT = Ed25519PrivateKey.from_private_bytes(bytes([12])*32)
ORIGIN = 'omega/witness-test'
LEAVES = tuple(leaf_hash(str(i).encode()) for i in range(5))
CHALLENGE = b'c'*32


def pub(key):
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def policy():
    return WitnessPolicy('simulation', ORIGIN, ORIGIN, pub(LOG), pub(WIT))


def note(leaves):
    return sign_note(Checkpoint(ORIGIN,len(leaves),merkle_root(leaves)),ORIGIN,LOG)


def store(path):
    return WitnessStore(path,policy(),WIT)


@pytest.fixture
def db(tmp_path):
    path = tmp_path/'anchor.sqlite'
    WitnessStore.initialize(path,policy(),WIT,note(LEAVES[:1]))
    return path


def test_persisted_monotonicity_and_log_rollback(db):
    w = store(db)
    assert w.advance(note(LEAVES),consistency_proof(LEAVES,1),expected_revision=0)=='ADVANCED'
    restarted = store(db)
    r = restarted.read(CHALLENGE)
    assert r.revision==1 and r.note==note(LEAVES)
    assert verify_witness(r,policy(),CHALLENGE)
    assert restarted.advance(note(LEAVES[:1]),(),expected_revision=1)=='ROLLBACK'
    assert restarted.advance(note(LEAVES),(),expected_revision=1)=='UNCHANGED'
    assert restarted.read(CHALLENGE)==r


def test_fork_bad_proof_and_signer_rejected(db):
    w=store(db)
    fork=(leaf_hash(b'wrong'),)+LEAVES[1:]
    assert w.advance(note(fork[:1]),(),expected_revision=0)=='EQUIVOCATION'
    assert w.advance(note(fork),consistency_proof(fork,1),expected_revision=0)=='INVALID_PROOF'
    assert w.advance(note(LEAVES)[:-1],(),expected_revision=0)=='INVALID_NOTE'
    assert w.read(CHALLENGE).revision==0


def test_atomic_compare_and_swap(db):
    def submit(leaves):
        return store(db).advance(note(leaves),consistency_proof(leaves,1),expected_revision=0)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(submit,(LEAVES[:2],LEAVES[:3])))
    assert sorted(results)==['ADVANCED','STALE']
    assert store(db).read(CHALLENGE).revision==1


def test_freshness_and_independent_trust(db):
    r=store(db).read(CHALLENGE)
    assert not verify_witness(r,policy(),b'd'*32)
    assert not verify_witness(replace(r,revision=1),policy(),CHALLENGE)
    assert not verify_witness(r,replace(policy(),environment='operational'),CHALLENGE)
    with pytest.raises(ValueError): replace(policy(),witness_key=pub(LOG))
    with pytest.raises(ValueError): WitnessStore(db,policy(),LOG)
    with pytest.raises(ValueError): WitnessStore(db,replace(policy(),environment='operational'),WIT)


def test_missing_and_reinitialization_fail_closed(db):
    with pytest.raises(FileExistsError): WitnessStore.initialize(db,policy(),WIT,note(LEAVES[:1]))
    db.unlink()
    with pytest.raises(FileNotFoundError): store(db)


def test_uncommitted_process_crash(db):
    code='import sqlite3,sys,os; c=sqlite3.connect(sys.argv[1]); c.execute("BEGIN IMMEDIATE"); c.execute("UPDATE anchor SET revision=99"); os._exit(91)'
    assert subprocess.run([sys.executable,'-c',code,str(db)],timeout=10).returncode==91
    assert store(db).read(CHALLENGE).revision==0


def test_committed_process_crash_before_reply(db):
    code='''import os,sys
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from omega_x_evolution.ontos_v72_witness import WitnessPolicy,WitnessStore
from omega_x_evolution.ontos_v72_merkle import leaf_hash,merkle_root,consistency_proof
from omega_x_evolution.ontos_v72_checkpoint_note import Checkpoint,sign_note
l=Ed25519PrivateKey.from_private_bytes(bytes([11])*32)
w=Ed25519PrivateKey.from_private_bytes(bytes([12])*32)
p=WitnessPolicy('simulation','omega/witness-test','omega/witness-test',l.public_key().public_bytes_raw(),w.public_key().public_bytes_raw())
a=tuple(leaf_hash(str(i).encode()) for i in range(5))
n=sign_note(Checkpoint(p.origin,len(a),merkle_root(a)),p.log_name,l)
assert WitnessStore(Path(sys.argv[1]),p,w).advance(n,consistency_proof(a,1),expected_revision=0)=='ADVANCED'
os._exit(92)
'''
    assert subprocess.run([sys.executable,'-c',code,str(db)],timeout=10).returncode==92
    assert store(db).read(CHALLENGE).note==note(LEAVES)
    assert store(db).advance(note(LEAVES),(),expected_revision=0)=='STALE'


def test_encrypted_operator_key_lifecycle(tmp_path):
    path=tmp_path/'witness.pem'; other=tmp_path/'log.pem'; password=b'fixture-only-password-123'
    pin=provision_key(path,password); pin2=provision_key(other,password)
    assert pin!=pin2 and path.stat().st_mode & 0o777 == 0o600
    assert b'ENCRYPTED PRIVATE KEY' in path.read_bytes()
    assert pub(load_key(path,password,pin))==pin
    with pytest.raises(ValueError): load_key(path,password,pin2)
    with pytest.raises(ValueError): load_key(path,b'wrong-password-123',pin)
    with pytest.raises(FileExistsError): provision_key(path,password)
    path.chmod(0o644)
    with pytest.raises(PermissionError): load_key(path,password,pin)
    path.chmod(0o600)
    link=tmp_path/'link.pem'; link.symlink_to(path)
    with pytest.raises(OSError): load_key(link,password,pin)


def test_client_floor_detects_witness_snapshot_rollback(db):
    # The operator-controlled database can be restored too; retain a separately
    # trusted client revision and reject the newly signed older state.
    snapshot=db.read_bytes()
    w=store(db)
    assert w.advance(note(LEAVES),consistency_proof(LEAVES,1),expected_revision=0)=='ADVANCED'
    assert verify_witness(w.read(CHALLENGE),policy(),CHALLENGE,minimum_revision=1)
    db.write_bytes(snapshot)
    old=store(db).read(b'n'*32)
    assert verify_witness(old,policy(),b'n'*32)
    assert not verify_witness(old,policy(),b'n'*32,minimum_revision=1)
    assert not verify_witness(old,policy(),b'n'*32,minimum_revision=True)


def test_tampered_database_note_and_permissions_fail_closed(db):
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE anchor SET note=?',(b'invalid',))
    with pytest.raises(ValueError): store(db)
    db.chmod(0o644)
    with pytest.raises(PermissionError): store(db)


def test_client_pin_detects_same_revision_fork_after_witness_restore(db):
    from omega_x_evolution.ontos_v72_witness import verify_witness_transition
    snapshot=db.read_bytes()
    w=store(db)
    assert w.advance(note(LEAVES[:2]),consistency_proof(LEAVES[:2],1),expected_revision=0)=='ADVANCED'
    before=w.read(CHALLENGE)
    assert w.advance(note(LEAVES),consistency_proof(LEAVES,2),expected_revision=1)=='ADVANCED'
    assert verify_witness_transition(w.read(b'n'*32),policy(),b'n'*32,before,consistency_proof(LEAVES,2))
    assert not verify_witness_transition(w.read(b'n'*32),policy(),b'n'*32,before,())
    db.write_bytes(snapshot)
    fork=(LEAVES[0],leaf_hash(b'fork'))+LEAVES[2:]
    w=store(db)
    assert w.advance(note(fork[:2]),consistency_proof(fork[:2],1),expected_revision=0)=='ADVANCED'
    assert not verify_witness_transition(w.read(b'n'*32),policy(),b'n'*32,before,())
    assert w.advance(note(fork),consistency_proof(fork,2),expected_revision=1)=='ADVANCED'
    assert not verify_witness_transition(w.read(b'n'*32),policy(),b'n'*32,before,consistency_proof(fork,2))
