"""Durable monotonic witness for a separately administered trust boundary.

The witness database, directory, private key and policy must be inaccessible
for writes by the log/candidate. SQLite durability is local; restoring both
trust domains or compromising the witness is outside this contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import sqlite3
import stat
from contextlib import closing

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, PublicFormat, BestAvailableEncryption, load_pem_private_key,
)
from .ontos_v72_checkpoint_note import _name, verify_note
from .ontos_v72_merkle import verify_consistency
from .ontos_v72_receipts import _prime_order_point, strict_verify
from .ontos_v72_jcs import canonical_json

_MAX_REV = 2**63-1
_DOMAIN = b'OMEGA-X/v72/monotonic-witness/v1\x00'


def _public(key):
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('native Ed25519 signing key required')
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _private_directory(path: Path) -> None:
    s = path.parent.stat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.geteuid() or s.st_mode & 0o077:
        raise PermissionError('operator-owned private directory required')


def _private_stat(s) -> None:
    if not stat.S_ISREG(s.st_mode) or s.st_uid != os.geteuid() or s.st_mode & 0o077 or s.st_nlink != 1:
        raise PermissionError('operator-owned private regular file required')


def _sync_directory(path: Path) -> None:
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _password(password: bytes) -> None:
    if type(password) is not bytes or not 16 <= len(password) <= 1024:
        raise ValueError('operator-provided password length outside bounds')


def provision_key(path: Path, password: bytes) -> bytes:
    """Explicit offline provisioning; CSPRNG, encrypted PKCS8, no replacement.

    Returns only the public key. No secrets are logged or stored in Git.
    The caller owns password entropy, backup, key rotation and key isolation.
    """
    _password(password)
    path = Path(path).absolute()
    _private_directory(path)
    key = Ed25519PrivateKey.generate()
    data = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, BestAvailableEncryption(password))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    _sync_directory(path)
    return _public(key)


def load_key(path: Path, password: bytes, pinned_public: bytes) -> Ed25519PrivateKey:
    _password(password)
    if not _prime_order_point(pinned_public):
        raise ValueError('valid externally pinned public key required')
    path = Path(path).absolute()
    _private_directory(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as f:
        _private_stat(os.fstat(f.fileno()))
        data = f.read(8193)
    if len(data) > 8192 or not data.startswith(b'-----BEGIN ENCRYPTED PRIVATE KEY-----\n'):
        raise ValueError('bounded encrypted PKCS8 key required')
    key = load_pem_private_key(data, password=password)
    if _public(key) != pinned_public:
        raise ValueError('key does not match external pin')
    return key


@dataclass(frozen=True, slots=True)
class WitnessPolicy:
    environment: str
    origin: str
    log_name: str
    log_key: bytes
    witness_key: bytes

    def __post_init__(self):
        if self.environment not in ('simulation', 'operational') or type(self.environment) is not str:
            raise ValueError('explicit trust environment required')
        _name(self.origin)
        _name(self.log_name)
        if (not _prime_order_point(self.log_key) or not _prime_order_point(self.witness_key)
                or self.log_key == self.witness_key):
            raise ValueError('distinct log and witness keys required')

    def digest(self) -> bytes:
        self.__post_init__()
        return sha256(canonical_json({'environment':self.environment,'origin':self.origin,
            'log_name':self.log_name,'log_key':self.log_key.hex(),
            'witness_key':self.witness_key.hex()})).digest()


@dataclass(frozen=True, slots=True)
class WitnessReceipt:
    revision: int
    note: bytes
    challenge: bytes
    signature: bytes


def _message(policy: WitnessPolicy, revision: int, note: bytes, challenge: bytes) -> bytes:
    if (type(revision) is not int or not 0 <= revision <= _MAX_REV
            or type(note) is not bytes or not 1 <= len(note) <= 1024
            or type(challenge) is not bytes or len(challenge) != 32):
        raise ValueError('bounded witness receipt fields required')
    return _DOMAIN + policy.digest() + revision.to_bytes(8,'big') + sha256(note).digest() + challenge


def _checkpoint(policy, note):
    return verify_note(note,expected_origin=policy.origin,trusted_key_name=policy.log_name,
                       trusted_public_key=policy.log_key)


def verify_witness(receipt: WitnessReceipt, policy: WitnessPolicy, challenge: bytes, *,
                   minimum_revision: int = 0) -> bool:
    """Use a fresh unpredictable caller challenge and an externally pinned policy."""
    try:
        if (type(receipt) is not WitnessReceipt or type(policy) is not WitnessPolicy
                or type(minimum_revision) is not int or not 0<=minimum_revision<=_MAX_REV
                or type(receipt.revision) is not int or receipt.revision<minimum_revision
                or receipt.challenge != challenge or _checkpoint(policy,receipt.note) is None):
            return False
        return strict_verify(policy.witness_key,_message(policy,receipt.revision,receipt.note,challenge),receipt.signature)
    except (ValueError,TypeError):
        return False


def verify_witness_transition(receipt: WitnessReceipt, policy: WitnessPolicy, challenge: bytes,
                              previous: WitnessReceipt, proof: tuple[bytes,...]) -> bool:
    """Check a fresh receipt against a previously retained, authenticated client pin."""
    if type(previous) is not WitnessReceipt or not verify_witness(previous,policy,previous.challenge):
        return False
    if not verify_witness(receipt,policy,challenge,minimum_revision=previous.revision):
        return False
    old = _checkpoint(policy,previous.note)
    new = _checkpoint(policy,receipt.note)
    if receipt.revision == previous.revision:
        return receipt.note == previous.note and type(proof) is tuple and not proof
    return (old is not None and new is not None and new.tree_size>old.tree_size
            and verify_consistency(old.tree_size,new.tree_size,old.root,new.root,proof))


class WitnessStore:
    """Explicitly provisioned SQLite witness; separate connections for atomic CAS."""

    def __init__(self, path: Path, policy: WitnessPolicy, signer: Ed25519PrivateKey):
        if type(policy) is not WitnessPolicy or _public(signer)!=policy.witness_key:
            raise ValueError('pinned witness signer required')
        self._policy = policy
        self._pin = policy.digest()
        self._signer = signer
        self._path = Path(path).absolute()
        with closing(self._connect()) as db:
            self._read(db)

    @classmethod
    def initialize(cls, path: Path, policy: WitnessPolicy, signer: Ed25519PrivateKey, genesis_note: bytes):
        if type(policy) is not WitnessPolicy or _public(signer)!=policy.witness_key or _checkpoint(policy,genesis_note) is None:
            raise ValueError('explicit trusted genesis and witness signer required')
        path = Path(path).absolute()
        _private_directory(path)
        fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        os.close(fd)
        # Failure intentionally leaves a fail-closed file, never auto-reinitializes.
        with closing(sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=5,isolation_level=None)) as db:
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE anchor(id INTEGER PRIMARY KEY CHECK(id=1), policy BLOB NOT NULL, revision INTEGER NOT NULL CHECK(revision>=0), note BLOB NOT NULL)')
            db.execute('INSERT INTO anchor VALUES(1,?,0,?)',(policy.digest(),genesis_note))
            db.commit()
        _sync_directory(path)
        return cls(path,policy,signer)

    def _connect(self):
        _private_directory(self._path)
        _private_stat(self._path.lstat())
        db = sqlite3.connect(self._path.as_uri()+'?mode=rw',uri=True,timeout=5,isolation_level=None)
        try:
            db.execute('PRAGMA synchronous=FULL')
            if db.execute('PRAGMA journal_mode').fetchone()[0]!='delete':
                raise ValueError('unexpected witness journal mode')
            return db
        except BaseException:
            db.close()
            raise

    def _read(self, db):
        row = db.execute('SELECT policy,revision,note FROM anchor WHERE id=1').fetchone()
        if row is None or row[0]!=self._pin or self._policy.digest()!=self._pin:
            raise ValueError('witness state/policy mismatch')
        revision,note = row[1:]
        checkpoint = _checkpoint(self._policy,note)
        if type(revision) is not int or not 0<=revision<=_MAX_REV or checkpoint is None:
            raise ValueError('invalid durable witness state')
        return revision,note,checkpoint

    def read(self, challenge: bytes) -> WitnessReceipt:
        if type(challenge) is not bytes or len(challenge)!=32:
            raise ValueError('32-byte challenge required')
        with closing(self._connect()) as db:
            revision,note,_ = self._read(db)
        return WitnessReceipt(revision,note,challenge,self._signer.sign(_message(self._policy,revision,note,challenge)))

    def advance(self, note: bytes, proof: tuple[bytes,...], *, expected_revision: int) -> str:
        if type(expected_revision) is not int or not 0<=expected_revision<=_MAX_REV:
            raise ValueError('invalid expected revision')
        new = _checkpoint(self._policy,note)
        if new is None:
            return 'INVALID_NOTE'
        with closing(self._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            revision,_,old = self._read(db)
            if revision!=expected_revision:
                return 'STALE'
            if new.tree_size<old.tree_size:
                return 'ROLLBACK'
            if new.tree_size==old.tree_size and new.root!=old.root:
                return 'EQUIVOCATION'
            if not verify_consistency(old.tree_size,new.tree_size,old.root,new.root,proof):
                return 'INVALID_PROOF'
            if new.tree_size==old.tree_size:
                return 'UNCHANGED'
            if revision==_MAX_REV:
                return 'EXHAUSTED'
            if db.execute('UPDATE anchor SET revision=?,note=? WHERE id=1 AND revision=?',
                          (revision+1,note,revision)).rowcount!=1:
                raise RuntimeError('witness compare-and-swap failed')
            db.commit()
            return 'ADVANCED'
