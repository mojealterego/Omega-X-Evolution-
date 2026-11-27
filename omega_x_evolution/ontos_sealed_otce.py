"""Envelope-encrypted OTCE with a separate operator-controlled key vault.

R0/R1 payloads encrypted, metadata public to the journal. Trusted supervisor,
clock, retained fence, filesystem and externally supplied KEK required.
Deletion removes wrapped DEKs from the active vault, not backups or RAM.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from hashlib import sha256
import hmac
import fcntl
import os
from pathlib import Path
import secrets
import sqlite3

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .ontos_epoch_journal_core import IntegrityError, _private
from .ontos_otce import OTCEJournal, Event, event_bytes, _reduce, _time, _name, _pin, _digest, Result
from .ontos_managed_journal import Fence
from .ontos_rcc import Statistics
from .ontos_v72_jcs import canonical_json, parse_json

DOMAIN=b'OMEGA-X/sealed-OTCE/v1\x00'
MAX_PLAINTEXT=512
MAX_KEYS=64
_META=('id','parents','kind','evidence','branch','time','source')


def _hex(value,size):
    return type(value) is str and len(value)==size*2 and all(c in '0123456789abcdef' for c in value)


def _kek(key):
    if type(key) is not bytes or len(key)!=32: raise ValueError('256-bit KEK required')
    return key


def _sealed(b):
    p=b['payload']; fields={'kid','nonce','ciphertext'}
    if b['kind']=='R0':
        fields.add('key')
        if not _name(p.get('key')): raise ValueError('invalid sealed key')
    ct=p.get('ciphertext')
    if (set(p)!=fields or not _pin(p.get('kid')) or not _hex(p.get('nonce'),12)
            or type(ct) is not str or len(ct)%2 or not 32<=len(ct)<=2*(MAX_PLAINTEXT+16)
            or not _hex(ct,len(ct)//2)):
        raise ValueError('invalid sealed payload')


def _plain(kind,p,dimension):
    if type(p) is not dict: raise ValueError('payload object required')
    if kind=='R0':
        if set(p)!={'key','value'} or not _name(p['key']) or type(p['value']) is not str:
            raise ValueError('invalid R0 payload')
    elif kind=='R1':
        if set(p)!={'x','y'} or type(p['x']) is not list: raise ValueError('invalid R1 payload')
        Statistics.zero(dimension).delta(tuple(p['x']),p['y'],1)
    else: raise ValueError('unsupported encrypted operator')
    raw=canonical_json(p)
    if len(raw)>MAX_PLAINTEXT: raise ValueError('plaintext byte budget')
    return raw


def sealed_event_bytes(scope,vault_id,e):
    if not _pin(vault_id): raise ValueError('vault ID required')
    return DOMAIN+b'sign\x00'+bytes.fromhex(_digest(b'sealed-format',[scope.pin,vault_id]))+event_bytes(scope,e)


class SealedOTCEJournal(OTCEJournal):
    def __init__(self,anchor,segments,vault,scope,pin,kek,*,vault_id):
        super().__init__(anchor,segments,scope,pin)
        self._kek=_kek(kek)
        if not _pin(vault_id): raise ValueError('independently provisioned vault ID required')
        self._vault_id=vault_id
        self._vault_path=Path(vault).absolute()
        dirs=[self._vault_path.parent.resolve(),Path(anchor).parent.resolve(),Path(segments).resolve()]
        if any(a==b or a in b.parents or b in a.parents for i,a in enumerate(dirs) for b in dirs[i+1:]):
            raise ValueError('separate private vault, anchor and segment directories required')

    def _state_pin(self): return _digest(b'sealed-format',[self._scope.pin,self._vault_id])

    def _event_bytes(self,e): return sealed_event_bytes(self._scope,self._vault_id,e)

    def _reduce(self,events,*,verify=None):
        nodes,*rest=_reduce(self._scope,events,verify=verify,payload_check=_sealed,
                            event_preimage=lambda scope,e: sealed_event_bytes(scope,self._vault_id,e))
        kids=[n['payload']['kid'] for n in nodes.values()]
        if len(kids)!=len(set(kids)): raise ValueError('reused DEK identifier')
        return nodes,*rest

    def _marker(self,key):
        return hmac.digest(key,DOMAIN+b'vault\x00'+bytes.fromhex(self._state_pin()),'sha256')

    def _wrap_aad(self,kid): return DOMAIN+b'wrap\x00'+bytes.fromhex(self._state_pin())+bytes.fromhex(kid)

    def _aad(self,b,p):
        return DOMAIN+b'payload\x00'+canonical_json([self._state_pin(),{k:b[k] for k in _META},p.get('key'),p['kid']])

    @contextmanager
    def _vault(self,*,initial=False):
        path=self._vault_path; _private(path,file=not initial)
        if initial:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600); os.close(fd)
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX)
            st=os.fstat(fd); named=path.stat()
            if (st.st_dev,st.st_ino)!=(named.st_dev,named.st_ino): raise IntegrityError('vault identity changed')
            with closing(sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=5,isolation_level=None)) as db:
                db.execute('PRAGMA trusted_schema=OFF')
                db.execute('PRAGMA synchronous=FULL')
                db.execute('PRAGMA secure_delete=ON')
                if db.execute('PRAGMA journal_mode').fetchone()!=('delete',): raise IntegrityError('vault journal mode')
                if initial:
                    db.execute('BEGIN IMMEDIATE')
                    db.execute('CREATE TABLE meta(id INTEGER PRIMARY KEY CHECK(id=1), marker BLOB NOT NULL)')
                    db.execute('CREATE TABLE keys(kid TEXT PRIMARY KEY, wrapped BLOB NOT NULL)')
                    db.execute('INSERT INTO meta VALUES(1,?)',(self._marker(self._kek),))
                    db.commit()
                    parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
                    try: os.fsync(parent)
                    finally: os.close(parent)
                row=db.execute('SELECT CASE WHEN length(marker)=32 THEN marker END FROM meta WHERE id=1').fetchone()
                if row is None or type(row[0]) is not bytes or not hmac.compare_digest(row[0],self._marker(self._kek)):
                    raise IntegrityError('vault scope or KEK mismatch')
                yield db
        finally: os.close(fd)

    def _wrap(self,key,kid,dek):
        nonce=os.urandom(12)
        return nonce+AESGCM(key).encrypt(nonce,dek,self._wrap_aad(kid))

    def _unwrap(self,key,kid,wrapped):
        if not _pin(kid) or type(wrapped) is not bytes or len(wrapped)!=60: raise IntegrityError('invalid key envelope')
        try: return AESGCM(key).decrypt(wrapped[:12],wrapped[12:],self._wrap_aad(kid))
        except InvalidTag as exc: raise IntegrityError('key envelope authentication failed') from exc

    def _decrypt(self,db,n):
        p=n['payload']; _sealed(n)
        row=db.execute('SELECT CASE WHEN length(wrapped)=60 THEN wrapped END FROM keys WHERE kid=?',(p['kid'],)).fetchone()
        if row is None: raise IntegrityError('capsule key unavailable')
        dek=self._unwrap(self._kek,p['kid'],row[0])
        try: raw=AESGCM(dek).decrypt(bytes.fromhex(p['nonce']),bytes.fromhex(p['ciphertext']),self._aad(n,p))
        except InvalidTag as exc: raise IntegrityError('capsule authentication failed') from exc
        plain=parse_json(raw)
        if _plain(n['kind'],plain,self._scope.dimension)!=raw or (n['kind']=='R0' and plain['key']!=p['key']):
            raise IntegrityError('invalid decrypted payload')
        return plain

    def initialize(self):
        with self._vault(initial=True): return super().initialize()

    def recover_from_anchor(self):
        with self._vault(): return super().recover_from_anchor()

    def put(self,expected,body,sign):
        """Trusted writer callback signs ciphertext; uncertain commits retain the key."""
        if type(expected) is not Fence or type(body) is not dict or set(body)!=set(_META)|{'payload'} or not callable(sign):
            raise ValueError('typed capsule, fence and signer required')
        # Canonical round trip detaches caller-owned mutable values.
        body=parse_json(canonical_json(body)); plain=_plain(body['kind'],body['payload'],self._scope.dimension)
        with self._vault() as db:
            snap=self._journal.read(expected); head=self._reduce(snap.state)[4]
            if db.execute('SELECT count(*) FROM keys').fetchone()[0]>=MAX_KEYS: raise ValueError('vault capacity; reconcile first')
            dek=AESGCM.generate_key(bit_length=256); nonce=os.urandom(12); kid=secrets.token_hex(32)
            p={'kid':kid,'nonce':nonce.hex()}
            if body['kind']=='R0': p['key']=body['payload']['key']
            p['ciphertext']=AESGCM(dek).encrypt(nonce,plain,self._aad(body,p)).hex()
            body['payload']=p
            e=Event(head,len(snap.state)+1,'put',canonical_json(body),b'\0'*64)
            signature=sign(self._event_bytes(e))
            e=Event(e.previous,e.sequence,e.kind,e.body,signature); e.wire()
            db.execute('INSERT INTO keys VALUES(?,?)',(kid,self._wrap(self._kek,kid,dek)))
            result=super().append(expected,e)
            if result.status in ('REJECTED','STALE','EXHAUSTED'): db.execute('DELETE FROM keys WHERE kid=?',(kid,))
            # ROLLOVER_PENDING or exception: do not destroy a possibly committed key.
            return result

    def append(self,expected,e):
        if type(e) is not Event or e.kind=='put': raise ValueError('use sealed put')
        with self._vault(): return super().append(expected,e)

    def compact(self,expected):
        with self._vault(): return super().compact(expected)

    def read(self,r,*,retained,now):
        if r.operation not in ('recall','weights','explain'): raise ValueError('dedicated operator endpoint required')
        with self._vault() as db:
            selected,evolution=self._selection(r,retained=retained,now=now); q=r.query
            if r.operation=='recall':
                for n in reversed(selected):
                    if n['kind']=='R0' and n['evidence']==('observed' if q.branch=='actual' else 'simulated') and n['payload']['key']==r.key:
                        return self._decrypt(db,n)['value']
                return None
            if r.operation=='weights':
                if q.branch!='actual': raise ValueError('no simulated training')
                stats=Statistics.zero(self._scope.dimension)
                for n in selected:
                    if n['kind']=='R1':
                        p=self._decrypt(db,n); stats=stats.delta(tuple(p['x']),p['y'],1)
                return stats.ridge(1)
            return [{**{k:v for k,v in n.items() if k!='payload'},'view_evolution':evolution} for n in selected]

    def purge(self,retained,*,now):
        """Remove wrapped keys for revoked/expired descendants and abandoned puts.

        Requires newest independent fence and trusted clock; no forensic erasure
        guarantee. Revocation is committed before purge, so a crash is fail closed.
        """
        if type(retained) is not Fence or not _time(now): raise ValueError('trusted fence and clock required')
        with self._vault() as db:
            nodes,revoked,*_=self._reduce(self._journal.read(retained).state)
            dead=set(revoked); keep=set()
            for i,n in nodes.items():
                if n['time']['expires']<=now or dead.intersection(n['parents']): dead.add(i)
                if i not in dead: keep.add(n['payload']['kid'])
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute('SELECT kid FROM keys LIMIT ?',(MAX_KEYS+1,)).fetchall()
            if len(rows)>MAX_KEYS: raise IntegrityError('vault capacity invariant')
            remove=[(kid,) for (kid,) in rows if kid not in keep]
            db.executemany('DELETE FROM keys WHERE kid=?',remove); db.commit()
            return len(remove)

    def rewrap(self,retained,new_kek):
        """Atomically rewrap active-vault DEKs. Caller durably provisions new KEK first."""
        new_kek=_kek(new_kek)
        if type(retained) is not Fence or hmac.compare_digest(new_kek,self._kek): raise ValueError('new KEK and retained fence required')
        with self._vault() as db:
            self._journal.read(retained)
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute('SELECT kid,CASE WHEN length(wrapped)=60 THEN wrapped END FROM keys LIMIT ?',(MAX_KEYS+1,)).fetchall()
            if len(rows)>MAX_KEYS: raise IntegrityError('vault capacity invariant')
            for kid,wrapped in rows:
                dek=self._unwrap(self._kek,kid,wrapped)
                db.execute('UPDATE keys SET wrapped=? WHERE kid=?',(self._wrap(new_kek,kid,dek),kid))
            db.execute('UPDATE meta SET marker=? WHERE id=1',(self._marker(new_kek),)); db.commit()
            self._kek=new_kek
            return len(rows)
