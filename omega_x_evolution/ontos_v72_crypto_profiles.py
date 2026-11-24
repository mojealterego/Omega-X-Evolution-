"""Bounded v72 HMAC and PQ public verification profiles; no promotion authority.

The OpenSSL executable is trusted deployment configuration, never candidate
input. Private PQ keys are not handled here. ML-KEM admission checks shape only.
"""
from __future__ import annotations

from enum import Enum
import hmac
import os
from pathlib import Path
import subprocess
import tempfile

_MAX_MESSAGE = 1024 * 1024


class Profile(Enum):
    ML_DSA_65 = 'ML-DSA-65'
    SLH_DSA_SHA2_128S = 'SLH-DSA-SHA2-128s'
    ML_KEM_768 = 'ML-KEM-768'


# DER OID last arc, raw public key bytes, signature or ciphertext bytes.
_PROFILES = {
    Profile.ML_DSA_65: (b'\x03\x04\x03\x12', 1952, 3309),
    Profile.SLH_DSA_SHA2_128S: (b'\x03\x04\x03\x14', 32, 7856),
    Profile.ML_KEM_768: (b'\x03\x04\x04\x02', 1184, 1088),
}
_SIGNATURES = frozenset((Profile.ML_DSA_65, Profile.SLH_DSA_SHA2_128S))


def _message(message: bytes) -> None:
    if type(message) is not bytes or len(message) > _MAX_MESSAGE:
        raise ValueError('bounded message bytes required')


def tag(key: bytes, message: bytes, *, test_only: bool) -> bytes:
    """Symmetric authentication, with disjoint test/runtime preimages."""
    _message(message)
    if type(key) is not bytes or len(key) != 32 or type(test_only) is not bool:
        raise ValueError('32-byte key and explicit test-only flag required')
    domain = b'OMEGA-X/v72/HMAC-SHA256\x00' + (b'TEST\x00' if test_only else b'RUNTIME\x00')
    return hmac.digest(key, domain + message, 'sha256')


def verify_tag(key: bytes, message: bytes, mac: bytes, *, test_only: bool) -> bool:
    if type(mac) is not bytes or len(mac) != 32:
        return False
    try:
        return hmac.compare_digest(tag(key, message, test_only=test_only), mac)
    except ValueError:
        return False


def _tlv(kind: int, data: bytes) -> bytes:
    n = len(data)
    length = bytes((n,)) if n < 128 else bytes((0x82,)) + n.to_bytes(2, 'big') if n >= 256 else bytes((0x81,n))
    return bytes((kind,)) + length + data


def public_der(profile: Profile, raw_public: bytes) -> bytes:
    """Construct exact SubjectPublicKeyInfo with absent algorithm parameters."""
    if type(profile) is not Profile or type(raw_public) is not bytes:
        raise ValueError('typed profile and raw public key required')
    oid_suffix, size, _ = _PROFILES[profile]
    if len(raw_public) != size:
        raise ValueError('invalid public key length')
    oid = _tlv(0x06, b'\x60\x86\x48\x01\x65' + oid_suffix)
    return _tlv(0x30, _tlv(0x30, oid) + _tlv(0x03, b'\x00' + raw_public))


def signature_preimage(profile: Profile, message: bytes) -> bytes:
    _message(message)
    if type(profile) is not Profile or profile not in _SIGNATURES:
        raise ValueError('signature profile required, not KEM')
    return b'OMEGA-X/v72/PQ-SIGNATURE\x00' + profile.value.encode('ascii') + b'\x00' + message


def verify_pq_signature(profile: Profile, raw_public: bytes, message: bytes,
                        signature: bytes, *, openssl: str) -> str:
    """PASS means backend accepted signature, not release or FIPS certification.

    FAIL means rejected input/backend nonzero exit; BLOCKED means tool unavailable.
    Only public material reaches a private temporary directory and subprocess.
    """
    try:
        preimage = signature_preimage(profile, message)
        der = public_der(profile, raw_public)
        if type(signature) is not bytes or len(signature) != _PROFILES[profile][2]:
            return 'FAIL'
    except ValueError:
        return 'FAIL'
    if type(openssl) is not str or not os.path.isabs(openssl):
        return 'BLOCKED'
    try:
        with tempfile.TemporaryDirectory(prefix='omega-pq-') as tmp:
            root = Path(tmp)
            key, msg, sig = (root / x for x in ('public.der', 'message', 'signature'))
            key.write_bytes(der); msg.write_bytes(preimage); sig.write_bytes(signature)
            run = subprocess.run(
                [openssl, 'pkeyutl', '-verify', '-rawin', '-pubin', '-keyform', 'DER',
                 '-provider', 'default', '-propquery', 'provider=default',
                 '-inkey', str(key), '-in', str(msg), '-sigfile', str(sig)],
                env={'OPENSSL_CONF': os.devnull, 'LC_ALL': 'C'},
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=10, check=False,
            )
            return 'PASS' if run.returncode == 0 else 'FAIL'
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return 'BLOCKED'


def validate_kem_ciphertext(profile: Profile, ciphertext: bytes) -> bool:
    """Length/role admission only; no claim of ciphertext authentication."""
    return (profile is Profile.ML_KEM_768 and type(ciphertext) is bytes
            and len(ciphertext) == _PROFILES[Profile.ML_KEM_768][2])
