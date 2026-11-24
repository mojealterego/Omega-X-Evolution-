"""Durable client epoch journal with cryptographic replay and external floor.

The independently trusted caller retains a cursor outside this database and
supplies it on every read/update. A restored database is detected relative to
that floor. Joint rollback of the journal, bootstrap and external floor is
outside this bounded local-storage model. No private keys are stored here.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import re
import sqlite3
from typing import Literal

from .ontos_v72_jcs import canonical_json, parse_json
from .ontos_v72_rotation import EpochPin, advance_pin, rotate_epoch, _receipt_digest
from .ontos_v72_witness import WitnessPolicy, WitnessReceipt, _private_directory, _private_stat, _sync_directory

_MAX_EVENTS = 256
_MAX_EVENT = 16384
_HEX = re.compile(r'[0-9a-f]+\Z', re.ASCII)
_REVISION = re.compile(r'(?:0|[1-9][0-9]{0,18})\Z', re.ASCII)
_DOMAIN = b'OMEGA-X/v72/client-epoch-journal/v1/'


class EpochIntegrityError(ValueError):
    """The journal cannot be authenticated against the supplied trust floor."""


@dataclass(frozen=True, slots=True)
class EpochCursor:
    sequence: int
    digest: str

    def __post_init__(self) -> None:
        if (type(self.sequence) is not int or not 0<=self.sequence<=_MAX_EVENTS
                or type(self.digest) is not str or len(self.digest)!=64 or not _HEX.fullmatch(self.digest)):
            raise ValueError('invalid epoch cursor')


@dataclass(frozen=True, slots=True)
class EpochSnapshot:
    cursor: EpochCursor
    pin: EpochPin


@dataclass(frozen=True, slots=True)
class EpochUpdate:
    status: Literal['ADVANCED','ROTATED','UNCHANGED','STALE','REJECTED','EXHAUSTED']
    snapshot: EpochSnapshot


def genesis_cursor(pin: EpochPin) -> EpochCursor:
    if type(pin) is not EpochPin:
        raise ValueError('externally trusted bootstrap pin required')
    return EpochCursor(0,sha256(_DOMAIN+b'genesis\x00'+bytes.fromhex(pin.digest())).hexdigest())


def _hex(value, size=None, maximum=None):
    if (type(value) is not str or not value or len(value)%2
            or size is not None and len(value)!=2*size
            or maximum is not None and len(value)>2*maximum or not _HEX.fullmatch(value)):
        raise ValueError('invalid bounded hex field')
    return bytes.fromhex(value)


def _shape(obj, keys):
    if type(obj) is not dict or set(obj)!=set(keys):
        raise ValueError('unexpected event shape')


def _receipt(receipt: WitnessReceipt) -> dict:
    _receipt_digest(receipt)
    return {'revision':str(receipt.revision),'note':receipt.note.hex(),
            'challenge':receipt.challenge.hex(),'signature':receipt.signature.hex()}


def _parse_receipt(obj) -> WitnessReceipt:
    _shape(obj,('revision','note','challenge','signature'))
    rev=obj['revision']
    if type(rev) is not str or not _REVISION.fullmatch(rev):
        raise ValueError('invalid revision')
    receipt=WitnessReceipt(int(rev),_hex(obj['note'],maximum=1024),_hex(obj['challenge'],32),_hex(obj['signature'],64))
    _receipt_digest(receipt)
    return receipt


def _policy(policy: WitnessPolicy) -> dict:
    if type(policy) is not WitnessPolicy:
        raise ValueError('typed witness policy required')
    policy.__post_init__()
    return {'environment':policy.environment,'origin':policy.origin,'log_name':policy.log_name,
            'log_key':policy.log_key.hex(),'witness_key':policy.witness_key.hex()}


def _parse_policy(obj) -> WitnessPolicy:
    _shape(obj,('environment','origin','log_name','log_key','witness_key'))
    return WitnessPolicy(obj['environment'],obj['origin'],obj['log_name'],_hex(obj['log_key'],32),_hex(obj['witness_key'],32))


def _proof(proof: tuple[bytes,...]) -> list[str]:
    if type(proof) is not tuple or len(proof)>64 or any(type(x) is not bytes or len(x)!=32 for x in proof):
        raise ValueError('bounded Merkle proof required')
    return [x.hex() for x in proof]


def _apply(snapshot: EpochSnapshot, payload: bytes) -> tuple[str,EpochPin] | None:
    if type(payload) is not bytes or not 1<=len(payload)<=_MAX_EVENT:
        raise ValueError('invalid event size')
    obj=parse_json(payload)
    if canonical_json(obj)!=payload or type(obj) is not dict:
        raise ValueError('noncanonical event')
    kind=obj.get('kind')
    common=('kind','previous','challenge','proof')
    if kind=='append':
        _shape(obj,common+('receipt',))
    elif kind=='rotate':
        _shape(obj,common+('policy','old_tip','new_tip','authority_signature'))
    else:
        raise ValueError('unknown epoch event')
    if obj['previous']!=snapshot.cursor.digest or type(obj['proof']) is not list or len(obj['proof'])>64:
        raise ValueError('invalid event parent or proof')
    proof=tuple(_hex(x,32) for x in obj['proof'])
    challenge=_hex(obj['challenge'],32)
    if kind=='append':
        pin=advance_pin(snapshot.pin,_parse_receipt(obj['receipt']),proof,challenge=challenge)
        if pin is None:
            return None
        if pin.receipt.revision==snapshot.pin.receipt.revision:
            return 'UNCHANGED',snapshot.pin
        return 'ADVANCED',pin
    pin=rotate_epoch(snapshot.pin,_parse_policy(obj['policy']),_parse_receipt(obj['old_tip']),
                     _parse_receipt(obj['new_tip']),proof,challenge=challenge,
                     authority_signature=_hex(obj['authority_signature'],64))
    return None if pin is None else ('ROTATED',pin)


def _next(snapshot: EpochSnapshot, payload: bytes, pin: EpochPin) -> EpochSnapshot:
    seq=snapshot.cursor.sequence+1
    digest=sha256(_DOMAIN+b'event\x00'+seq.to_bytes(4,'big')+bytes.fromhex(snapshot.cursor.digest)
                  +sha256(payload).digest()+bytes.fromhex(pin.digest())).hexdigest()
    return EpochSnapshot(EpochCursor(seq,digest),pin)


class EpochStore:
    """Bounded replay journal; no implicit initialization or trust from SQLite."""

    def __init__(self,path: Path,bootstrap: EpochPin):
        self._path=Path(path).absolute()
        self._genesis=EpochSnapshot(genesis_cursor(bootstrap),bootstrap)
        self.read(self._genesis.cursor)

    @classmethod
    def initialize(cls,path: Path,bootstrap: EpochPin):
        cursor=genesis_cursor(bootstrap)
        path=Path(path).absolute()
        _private_directory(path)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        os.close(fd)
        with closing(sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=5,isolation_level=None)) as db:
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE bootstrap(id INTEGER PRIMARY KEY CHECK(id=1), digest TEXT NOT NULL)')
            db.execute('INSERT INTO bootstrap VALUES(1,?)',(cursor.digest,))
            db.execute('CREATE TABLE events(sequence INTEGER PRIMARY KEY CHECK(sequence>0), payload BLOB NOT NULL, digest TEXT NOT NULL)')
            db.commit()
        _sync_directory(path)
        return cls(path,bootstrap)

    def _connect(self):
        _private_directory(self._path)
        _private_stat(self._path.lstat())
        db=sqlite3.connect(self._path.as_uri()+'?mode=rw',uri=True,timeout=5,isolation_level=None)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA trusted_schema=OFF')
            if db.execute('PRAGMA journal_mode').fetchone()[0]!='delete':
                raise EpochIntegrityError('unexpected journal mode')
            return db
        except BaseException:
            db.close()
            raise

    def _scan(self,db,floor: EpochCursor) -> EpochSnapshot:
        if type(floor) is not EpochCursor:
            raise ValueError('externally retained cursor required')
        floor.__post_init__()
        snapshot=self._genesis
        if (genesis_cursor(snapshot.pin)!=snapshot.cursor
                or db.execute('SELECT digest FROM bootstrap WHERE id=1').fetchone()!=(snapshot.cursor.digest,)):
            raise EpochIntegrityError('bootstrap mismatch')
        matched=floor==snapshot.cursor
        rows=db.execute('SELECT sequence,CASE WHEN length(payload)<=? THEN payload ELSE NULL END,digest FROM events ORDER BY sequence LIMIT ?',(_MAX_EVENT,_MAX_EVENTS+1))
        for seq,payload,digest in rows:
            if type(seq) is not int or seq!=snapshot.cursor.sequence+1 or seq>_MAX_EVENTS:
                raise EpochIntegrityError('journal sequence invalid')
            try:
                result=_apply(snapshot,payload)
                if result is None or result[0]=='UNCHANGED':
                    raise ValueError('invalid persisted transition')
                snapshot=_next(snapshot,payload,result[1])
                if snapshot.cursor.digest!=digest:
                    raise ValueError('event digest mismatch')
            except (ValueError,TypeError,OverflowError,RecursionError) as exc:
                raise EpochIntegrityError('journal replay failed') from exc
            matched=matched or floor==snapshot.cursor
        if not matched:
            raise EpochIntegrityError('journal is behind or diverges from external floor')
        return snapshot

    def read(self,floor: EpochCursor) -> EpochSnapshot:
        with closing(self._connect()) as db:
            db.execute('BEGIN')
            return self._scan(db,floor)

    def _commit(self,expected: EpochCursor,payload: bytes) -> EpochUpdate:
        with closing(self._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            snapshot=self._scan(db,expected)
            if snapshot.cursor!=expected:
                return EpochUpdate('STALE',snapshot)
            try:
                result=_apply(snapshot,payload)
            except (ValueError,TypeError,OverflowError,RecursionError):
                result=None
            if result is None:
                return EpochUpdate('REJECTED',snapshot)
            status,pin=result
            if status=='UNCHANGED':
                return EpochUpdate(status,snapshot)
            if snapshot.cursor.sequence==_MAX_EVENTS:
                return EpochUpdate('EXHAUSTED',snapshot)
            successor=_next(snapshot,payload,pin)
            db.execute('INSERT INTO events VALUES(?,?,?)',(successor.cursor.sequence,payload,successor.cursor.digest))
            db.commit()
            return EpochUpdate(status,successor)

    @staticmethod
    def _event(expected,kind,proof,challenge,**fields):
        if type(expected) is not EpochCursor or type(challenge) is not bytes or len(challenge)!=32:
            raise ValueError('typed cursor and challenge required')
        expected.__post_init__()
        return canonical_json({'kind':kind,'previous':expected.digest,'proof':_proof(proof),
                               'challenge':challenge.hex(),**fields})

    def append(self,expected: EpochCursor,receipt: WitnessReceipt,proof: tuple[bytes,...],*,challenge: bytes) -> EpochUpdate:
        return self._commit(expected,self._event(expected,'append',proof,challenge,receipt=_receipt(receipt)))

    def rotate(self,expected: EpochCursor,proposed: WitnessPolicy,old_tip: WitnessReceipt,new_tip: WitnessReceipt,
               proof: tuple[bytes,...],*,challenge: bytes,authority_signature: bytes) -> EpochUpdate:
        if type(authority_signature) is not bytes or len(authority_signature)!=64:
            raise ValueError('bounded authority signature required')
        return self._commit(expected,self._event(expected,'rotate',proof,challenge,policy=_policy(proposed),
                            old_tip=_receipt(old_tip),new_tip=_receipt(new_tip),authority_signature=authority_signature.hex()))
