"""L12 v72: detached Ed25519 receipts with strict public-point admission.

The native cryptography backend performs signing and signature verification.
Public-only curve arithmetic checks canonical prime-order points. A valid
receipt authenticates a record and scope, not the truth of a test or promotion.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any

from .ontos_v72_jcs import canonical_json, MAX_BYTES

_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, -1, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)
_IDENTITY = (0, 1, 1, 0)
_SCHEMA = 'omega-v72-detached-receipt-v1'
_DOMAIN = b'OMEGA-X/v72/evidence-receipt\x00'
_HEX40 = re.compile(r'[0-9a-f]{40}\Z', re.ASCII)
_HEX128 = re.compile(r'[0-9a-f]{128}\Z', re.ASCII)
_IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z', re.ASCII)
_LEVEL = re.compile(r'L(?:1[2-9]|[2-9][0-9]|10[0-9]|11[01])\Z', re.ASCII)
_GATES = frozenset(f'GATE-0{i}' for i in range(1, 9))


def _add(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[int, ...]:
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    p = (y1-x1)*(y2-x2) % _P
    q = (y1+x1)*(y2+x2) % _P
    r = 2*_D*t1*t2 % _P
    s = 2*z1*z2 % _P
    e, f, g, h = q-p, s-r, s+r, q+p
    return e*f % _P, g*h % _P, f*g % _P, e*h % _P


def _is_identity(point: tuple[int, ...]) -> bool:
    x, y, z, _ = point
    return z % _P != 0 and x % _P == 0 and (y-z) % _P == 0


def _prime_order_point(raw: bytes) -> bool:
    """Public-data only: decode canonically, exclude identity and torsion."""
    if type(raw) is not bytes or len(raw) != 32:
        return False
    value = int.from_bytes(raw, 'little')
    y, sign = value & (2**255-1), value >> 255
    if y >= _P:
        return False
    den = (_D*y*y + 1) % _P
    if den == 0:
        return False
    xx = (y*y-1)*pow(den, -1, _P) % _P
    x = pow(xx, (_P+3)//8, _P)
    if (x*x-xx) % _P:
        x = x*_I % _P
    if (x*x-xx) % _P or (x == 0 and sign):
        return False
    if x & 1 != sign:
        x = (-x) % _P
    point = (x, y, 1, x*y % _P)
    if _is_identity(point):
        return False
    result, scalar = _IDENTITY, _L
    while scalar:
        if scalar & 1:
            result = _add(result, point)
        point = _add(point, point)
        scalar >>= 1
    return _is_identity(result)


def strict_verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """Stricter than bare backend verification: prime-order A/R, canonical S."""
    if (type(message) is not bytes or len(message) > MAX_BYTES
            or type(signature) is not bytes or len(signature) != 64
            or int.from_bytes(signature[32:], 'little') >= _L
            or not _prime_order_point(public_key) or not _prime_order_point(signature[:32])):
        return False
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return False
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


@dataclass(frozen=True, slots=True)
class ReceiptScope:
    level_id: str
    gate_id: str
    commit_sha: str
    tenant: str
    evaluator_id: str

    def __post_init__(self) -> None:
        if (type(self.level_id) is not str or not _LEVEL.fullmatch(self.level_id)
                or type(self.gate_id) is not str or self.gate_id not in _GATES
                or type(self.commit_sha) is not str or not _HEX40.fullmatch(self.commit_sha)
                or type(self.tenant) is not str or not _IDENTIFIER.fullmatch(self.tenant)
                or type(self.evaluator_id) is not str or not _IDENTIFIER.fullmatch(self.evaluator_id)):
            raise ValueError('invalid evidence scope')

    def body(self) -> dict[str, str]:
        self.__post_init__()
        return {'level_id': self.level_id, 'gate_id': self.gate_id,
                'commit_sha': self.commit_sha, 'tenant': self.tenant,
                'evaluator_id': self.evaluator_id}


def _body(record: dict[str, Any], scope: ReceiptScope) -> dict[str, Any]:
    if type(record) is not dict or type(scope) is not ReceiptScope:
        raise ValueError('typed scope and record required')
    return {'schema': _SCHEMA, 'scope': scope.body(),
            'record_sha256': hashlib.sha256(canonical_json(record)).hexdigest()}


def sign_receipt(record: dict[str, Any], scope: ReceiptScope, private_key: Any) -> dict[str, Any]:
    """For the trusted signer only; never exposes or processes raw secret scalars."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError('native Ed25519 private key required')
    body = _body(record, scope)
    return {**body, 'signature_hex': private_key.sign(_DOMAIN + canonical_json(body)).hex()}


def verify_receipt(receipt: Any, record: dict[str, Any], expected_scope: ReceiptScope,
                   trusted_public_key: bytes) -> bool:
    """Verify against caller-pinned scope/key, never a key supplied by a receipt."""
    if type(receipt) is not dict or len(receipt) != 4:
        return False
    try:
        expected = _body(record, expected_scope)
        if set(receipt) != set(expected) | {'signature_hex'}:
            return False
        sig = receipt['signature_hex']
        if type(sig) is not str or not _HEX128.fullmatch(sig):
            return False
        supplied = {k: receipt[k] for k in expected}
        message = canonical_json(expected)
        if canonical_json(supplied) != message:
            return False
        return strict_verify(trusted_public_key, _DOMAIN + message, bytes.fromhex(sig))
    except (ValueError, TypeError, KeyError, RecursionError):
        return False
