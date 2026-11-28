"""Crash-consistent checkpoint with a separately provisioned durable floor.

The anchor is trusted against rollback independently of the data DB. Prepared
intents roll forward, never abort to an older generation. No joint-rollback or
physical media sanitization guarantee. Cooperating local processes only.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
import fcntl
import hmac
import json
import os
from pathlib import Path
import sqlite3

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .checkpoint import CheckpointError, MAX_PAYLOAD
from .fenced_checkpoint import FencedCheckpointStore, CheckpointPin
from .ontos_epoch_journal_core import _private

DOMAIN = b'OMEGA-X/durable-checkpoint/v1\x00'
ZERO = bytes(32)


def _sync_parent(path):
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def _create(path):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    _sync_parent(path)


class DurableCheckpointStore(FencedCheckpointStore):
    def __init__(self, path, key, *, anchor, anchor_key, run_id):
        super().__init__(path, key, run_id=run_id)
        if type(anchor_key) is not bytes or len(anchor_key) != 32 or hmac.compare_digest(anchor_key,key):
            raise ValueError('independent 256-bit anchor key required')
        self.anchor = Path(anchor).absolute()
        a,b = self.anchor.parent.resolve(), self.path.parent.resolve()
        if a == b or a in b.parents or b in a.parents:
            raise ValueError('separate private anchor and checkpoint directories required')
        self._auth = hmac.digest(anchor_key, DOMAIN+b'auth\x00'+run_id, 'sha256')
        self._cipher = AESGCM(hmac.digest(anchor_key, DOMAIN+b'intent\x00'+run_id, 'sha256'))

    @contextmanager
    def _db(self,path):
        _private(path,file=True)
        with closing(sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=5,isolation_level=None)) as db:
            db.execute('PRAGMA trusted_schema=OFF')
            db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA secure_delete=ON')
            if db.execute('PRAGMA journal_mode').fetchone() != ('delete',):
                raise CheckpointError('DELETE journal mode required')
            yield db

    @contextmanager
    def _locked(self):
        try:
            _private(self.anchor,file=True); _private(self.path,file=False)
            fd=os.open(self.anchor,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            try:
                fcntl.flock(fd,fcntl.LOCK_EX)
                a,b=os.fstat(fd),self.anchor.stat()
                if (a.st_dev,a.st_ino)!=(b.st_dev,b.st_ino): raise CheckpointError('anchor identity changed')
                with self._db(self.anchor) as db: yield db
            finally: os.close(fd)
        except (OSError,sqlite3.Error) as exc:
            raise CheckpointError('durable checkpoint storage failure') from exc

    def _tag(self,g,m,pg,pm,blob):
        raw=g.to_bytes(8,'big',signed=True)+m
        if pg is not None: raw+=pg.to_bytes(8,'big',signed=True)+pm+blob
        return hmac.digest(self._auth,DOMAIN+raw,'sha256')

    def provision(self):
        """Explicit one-time trusted genesis; never auto-recreate missing floor."""
        try:
            _private(self.anchor,file=False); _private(self.path,file=False)
            if os.path.lexists(self.path): raise CheckpointError('data already exists')
            _create(self.anchor)
            with self._locked() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('CREATE TABLE floor(id INTEGER PRIMARY KEY CHECK(id=1),generation INTEGER NOT NULL,mac BLOB NOT NULL,pending INTEGER,pending_mac BLOB,intent BLOB,tag BLOB NOT NULL)')
                db.execute('INSERT INTO floor VALUES(1,-1,?,NULL,NULL,NULL,?)',(ZERO,self._tag(-1,ZERO,None,None,None)))
                db.commit()
        except (OSError,sqlite3.Error) as exc: raise CheckpointError('cannot provision anchor') from exc

    def _floor(self,db):
        row=db.execute('SELECT generation,mac,pending,pending_mac,intent,tag FROM floor WHERE id=1 AND length(mac)=32 AND length(tag)=32 AND (intent IS NULL OR length(intent)<=?)',(MAX_PAYLOAD+28,)).fetchone()
        if row is None: raise CheckpointError('missing or oversized floor')
        g,m,pg,pm,blob,tag=row
        if (type(g) is not int or not -1<=g<2**63 or type(m) is not bytes or len(m)!=32 or (g==-1 and m!=ZERO)
                or type(tag) is not bytes or len(tag)!=32): raise CheckpointError('invalid floor')
        if pg is None:
            if pm is not None or blob is not None: raise CheckpointError('invalid stable floor')
        elif (type(pg) is not int or pg!=g+1 or pg>=2**63 or type(pm) is not bytes or len(pm)!=32
              or type(blob) is not bytes or not 28<len(blob)<=MAX_PAYLOAD+28): raise CheckpointError('invalid intent')
        if not hmac.compare_digest(tag,self._tag(g,m,pg,pm,blob)): raise CheckpointError('anchor authentication failed')
        return g,m,pg,pm,blob

    def _write_floor(self,db,g,m,pg=None,pm=None,blob=None):
        db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE floor SET generation=?,mac=?,pending=?,pending_mac=?,intent=?,tag=? WHERE id=1',
                   (g,m,pg,pm,blob,self._tag(g,m,pg,pm,blob)))
        db.commit()

    def _aad(self,g,m,pg,pm):
        return DOMAIN+self._run_id+g.to_bytes(8,'big',signed=True)+m+pg.to_bytes(8,'big')+pm

    def _read(self):
        if not os.path.lexists(self.path): return None
        with self._db(self.path) as db:
            schema=db.execute('SELECT name,type FROM sqlite_schema WHERE name NOT LIKE \'sqlite_%\'').fetchall()
            if not schema: return None
            if schema != [('checkpoint','table')]: raise CheckpointError('unexpected checkpoint schema')
            row=db.execute('SELECT generation,payload,mac FROM checkpoint WHERE id=1 AND typeof(payload)=\'blob\' AND length(payload)<=? AND typeof(mac)=\'blob\' AND length(mac)=32',(MAX_PAYLOAD,)).fetchone()
            if row is None: raise CheckpointError('missing or oversized checkpoint')
            g,p,m=row
            if type(g) is not int or not 0<=g<2**63 or not hmac.compare_digest(m,self._mac(g,p)):
                raise CheckpointError('checkpoint authentication failed')
            return g,m,p

    def _apply(self,g,m,pg,pm,payload):
        if not os.path.lexists(self.path):
            if g!=-1: raise CheckpointError('missing committed checkpoint')
            _create(self.path)
        with self._db(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            if g==-1:
                if db.execute('SELECT name FROM sqlite_schema').fetchall(): raise CheckpointError('unexpected genesis database')
                db.execute('CREATE TABLE checkpoint(id INTEGER PRIMARY KEY CHECK(id=1),generation INTEGER NOT NULL,payload BLOB NOT NULL,mac BLOB NOT NULL)')
                db.execute('INSERT INTO checkpoint VALUES(1,?,?,?)',(pg,payload,pm))
            elif db.execute('UPDATE checkpoint SET generation=?,payload=?,mac=? WHERE id=1 AND generation=? AND mac=?',(pg,payload,pm,g,m)).rowcount!=1:
                raise CheckpointError('checkpoint CAS failed')
            db.commit()

    def _finish(self,db,pg,pm): self._write_floor(db,pg,pm)

    def _recover(self,db):
        g,m,pg,pm,blob=self._floor(db); row=self._read()
        if pg is None:
            if (g==-1 and row is not None) or (g>=0 and (row is None or row[:2]!=(g,m))):
                raise CheckpointError('checkpoint differs from stable floor')
            return row
        try: payload=self._cipher.decrypt(blob[:12],blob[12:],self._aad(g,m,pg,pm))
        except InvalidTag as exc: raise CheckpointError('intent authentication failed') from exc
        if not hmac.compare_digest(pm,self._mac(pg,payload)): raise CheckpointError('intent checkpoint MAC mismatch')
        if row is not None and row[:2]==(pg,pm):
            if row[2]!=payload: raise CheckpointError('intent payload mismatch')
        elif (g==-1 and row is None) or (row is not None and row[:2]==(g,m)):
            self._apply(g,m,pg,pm,payload)
        else: raise CheckpointError('checkpoint outside prepared transition')
        self._finish(db,pg,pm)
        return pg,pm,payload

    def _commit(self,db,g,m,pg,state):
        if type(state) is not dict: raise CheckpointError('checkpoint state must be an object')
        payload,pm=self._encode(pg,state)
        nonce=os.urandom(12)
        blob=nonce+self._cipher.encrypt(nonce,payload,self._aad(g,m,pg,pm))
        self._write_floor(db,g,m,pg,pm,blob)
        row=self._recover(db)
        self._expected=row[:2]; self._advance()

    def initialize(self,state):
        with self._locked() as db:
            if self._recover(db) is not None or os.path.lexists(self.path): raise CheckpointError('run already initialized')
            self._commit(db,-1,ZERO,0,state)

    def load(self):
        self._expected=None; self._pin=None
        with self._locked() as db:
            row=self._recover(db)
            if row is None: raise CheckpointError('run not initialized')
            g,m,p=row
            try: state=json.loads(p)
            except (ValueError,RecursionError) as exc: raise CheckpointError('invalid checkpoint JSON') from exc
            if type(state) is not dict: raise CheckpointError('invalid checkpoint state')
            self._expected=(g,m); self._advance()
            return g,state

    def save(self,generation,state):
        expected=self._expected
        if expected is None or type(generation) is not int or not 0<generation<2**63 or generation!=expected[0]+1:
            raise CheckpointError('validated sequential checkpoint required')
        self._expected=None; self._pin=None
        with self._locked() as db:
            row=self._recover(db)
            if row is None or row[:2]!=expected: raise CheckpointError('stale checkpoint writer')
            self._commit(db,*expected,generation,state)
