"""Bounded C2SP v1.0.0 checkpoint profile: three body lines, one log signature.

No extensions or witness cosignatures admitted by this deliberately narrow
profile. Authentication is not proof of consistency or rollback protection.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import re
from typing import Any

from .ontos_v72_receipts import strict_verify

_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,254}\Z', re.ASCII)
_SIZE = re.compile(rb'(?:0|[1-9][0-9]{0,18})\Z')
_MAX_SIZE = 2**63 - 1
_MAX_NOTE = 1024
_EMPTY = hashlib.sha256(b'').digest()
_DASH = b'\xe2\x80\x94 '


def _name(value: Any) -> bytes:
    if type(value) is not str or not _NAME.fullmatch(value):
        raise ValueError('invalid ASCII origin or signer name')
    return value.encode('ascii')


@dataclass(frozen=True, slots=True)
class Checkpoint:
    origin: str
    tree_size: int
    root: bytes

    def __post_init__(self) -> None:
        _name(self.origin)
        if type(self.tree_size) is not int or not 0 <= self.tree_size <= _MAX_SIZE:
            raise ValueError('invalid tree size')
        if type(self.root) is not bytes or len(self.root) != 32:
            raise ValueError('invalid SHA-256 root')
        if self.tree_size == 0 and self.root != _EMPTY:
            raise ValueError('invalid empty tree root')


def format_body(checkpoint: Checkpoint) -> bytes:
    if type(checkpoint) is not Checkpoint:
        raise ValueError('typed checkpoint required')
    checkpoint.__post_init__()
    return (_name(checkpoint.origin) + b'\n' + str(checkpoint.tree_size).encode('ascii')
            + b'\n' + base64.b64encode(checkpoint.root) + b'\n')


def _key_id(name: bytes, public: bytes) -> bytes:
    if type(public) is not bytes or len(public) != 32:
        raise ValueError('invalid Ed25519 public key')
    return hashlib.sha256(name + b'\n\x01' + public).digest()[:4]


def sign_note(checkpoint: Checkpoint, key_name: str, private_key: Any) -> bytes:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError('native Ed25519 private key required')
    body, name = format_body(checkpoint), _name(key_name)
    public = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    signature = _key_id(name, public) + private_key.sign(body)
    note = body + b'\n' + _DASH + name + b' ' + base64.b64encode(signature) + b'\n'
    if len(note) > _MAX_NOTE:
        raise ValueError('note exceeds byte budget')
    return note


def _decode(value: bytes, size: int) -> bytes:
    decoded = base64.b64decode(value, validate=True)
    if len(decoded) != size or base64.b64encode(decoded) != value:
        raise ValueError('noncanonical or invalid base64')
    return decoded


def verify_note(note: bytes, *, expected_origin: str, trusted_key_name: str,
                trusted_public_key: bytes) -> Checkpoint | None:
    """Authenticate exact wire bytes against externally pinned origin/name/key."""
    if type(note) is not bytes or len(note) > _MAX_NOTE:
        return None
    try:
        origin, name = _name(expected_origin), _name(trusted_key_name)
        kid = _key_id(name, trusted_public_key)
        lines = note.split(b'\n')
        if len(lines) != 6 or lines[3] or lines[5] or lines[0] != origin:
            return None
        if not _SIZE.fullmatch(lines[1]):
            return None
        checkpoint = Checkpoint(expected_origin, int(lines[1]), _decode(lines[2], 32))
        prefix = _DASH + name + b' '
        if not lines[4].startswith(prefix):
            return None
        signature = _decode(lines[4][len(prefix):], 68)
        if signature[:4] != kid:
            return None
        body = b'\n'.join(lines[:3]) + b'\n'
        if body != format_body(checkpoint) or not strict_verify(trusted_public_key, body, signature[4:]):
            return None
        return checkpoint
    except (ValueError, TypeError):
        return None
