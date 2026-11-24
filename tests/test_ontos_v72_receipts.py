"""Ed25519 public-point admission and detached scope-bound evidence receipts."""
import copy
import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from omega_x_evolution.ontos_v72_receipts import (
    ReceiptScope, sign_receipt, verify_receipt, strict_verify,
)

SEED = bytes.fromhex('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60')
PUBLIC = bytes.fromhex('d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a')
SIGNATURE = bytes.fromhex('e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555'
                          'fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b')
L = 2**252 + 27742317777372353535851937790883648493
SCOPE = ReceiptScope('L12', 'GATE-04', 'a' * 40, 'tenant-1', 'eval-1')
RECORD = {'test': {'exit_code': 0}, 'identity': {'source_sha256': 'b' * 64}}


def test_rfc8032_vector_and_native_signing():
    key = Ed25519PrivateKey.from_private_bytes(SEED)
    assert key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw) == PUBLIC
    assert key.sign(b'') == SIGNATURE
    assert strict_verify(PUBLIC, b'', SIGNATURE)
    assert not strict_verify(PUBLIC, b'changed', SIGNATURE)
    assert not strict_verify(PUBLIC, b'', SIGNATURE[:32] + (int.from_bytes(SIGNATURE[32:], 'little') + L).to_bytes(32, 'little'))


@pytest.mark.parametrize('point', [b'\x01' + bytes(31), bytes(32),
    (2**255 - 20).to_bytes(32, 'little'), (2**255 - 19).to_bytes(32, 'little'),
    (2**255 + 1).to_bytes(32, 'little')])
def test_reject_small_order_noncanonical_and_negative_zero(point):
    assert not strict_verify(point, b'', point + bytes(32))
    assert not strict_verify(PUBLIC, b'', point + SIGNATURE[32:])


def test_receipt_binds_record_and_expected_scope():
    key = Ed25519PrivateKey.from_private_bytes(SEED)
    receipt = sign_receipt(RECORD, SCOPE, key)
    assert verify_receipt(receipt, RECORD, SCOPE, PUBLIC)
    assert not verify_receipt(receipt, {'test': {'exit_code': 1}}, SCOPE, PUBLIC)
    for wrong in (ReceiptScope('L13', 'GATE-04', 'a' * 40, 'tenant-1', 'eval-1'),
                  ReceiptScope('L12', 'GATE-05', 'a' * 40, 'tenant-1', 'eval-1'),
                  ReceiptScope('L12', 'GATE-04', 'c' * 40, 'tenant-1', 'eval-1'),
                  ReceiptScope('L12', 'GATE-04', 'a' * 40, 'tenant-2', 'eval-1'),
                  ReceiptScope('L12', 'GATE-04', 'a' * 40, 'tenant-1', 'eval-2')):
        assert not verify_receipt(receipt, RECORD, wrong, PUBLIC)
    assert not verify_receipt(receipt, RECORD, SCOPE, Ed25519PrivateKey.from_private_bytes(bytes(32)).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
    assert 'release_authorized' not in receipt


@pytest.mark.parametrize('field,value', [('schema','other'), ('record_sha256','f'*64),
    ('signature_hex','0'*128), ('signature_hex','AB'*64), ('scope',{}), ('extra',True)])
def test_receipt_tampering_fails_closed(field,value):
    receipt = sign_receipt(RECORD, SCOPE, Ed25519PrivateKey.from_private_bytes(SEED))
    receipt[field] = value
    assert not verify_receipt(receipt, RECORD, SCOPE, PUBLIC)


def test_scope_and_input_validation():
    for bad in ('GATE-09', 'GATE-00', 'unknown'):
        with pytest.raises(ValueError): ReceiptScope('L12', bad, 'a'*40, 'tenant-1', 'eval-1')
    with pytest.raises(ValueError): ReceiptScope('L112', 'GATE-04', 'a'*40, 'tenant-1', 'eval-1')
    with pytest.raises(ValueError): ReceiptScope('L12', 'GATE-04', 'z'*40, 'tenant-1', 'eval-1')
    with pytest.raises(ValueError): ReceiptScope('L12', 'GATE-04', 'a'*40, 'tenant|1', 'eval-1')
    assert not strict_verify(PUBLIC, b'x' * (1024*1024 + 1), SIGNATURE)
    assert not strict_verify(PUBLIC, b'', SIGNATURE[:-1])
    assert not verify_receipt(None, RECORD, SCOPE, PUBLIC)
    assert not verify_receipt({}, RECORD, SCOPE, PUBLIC)
