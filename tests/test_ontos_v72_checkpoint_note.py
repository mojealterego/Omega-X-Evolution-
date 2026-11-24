import base64
import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from omega_x_evolution.ontos_v72_checkpoint_note import (
    Checkpoint, format_body, sign_note, verify_note,
)

KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
PUBLIC = KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
ROOT = hashlib.sha256(b'fixture').digest()
ORIGIN = 'omega.example/main'
CHECKPOINT = Checkpoint(ORIGIN, 7, ROOT)


def verify(note, origin=ORIGIN, key=PUBLIC):
    return verify_note(note, expected_origin=origin, trusted_key_name=ORIGIN, trusted_public_key=key)


def test_exact_c2sp_body_key_id_and_signature():
    body = ORIGIN.encode() + b'\n7\n' + base64.b64encode(ROOT) + b'\n'
    assert format_body(CHECKPOINT) == body
    key_id = hashlib.sha256(ORIGIN.encode() + b'\n\x01' + PUBLIC).digest()[:4]
    expected = body + b'\n\xe2\x80\x94 ' + ORIGIN.encode() + b' ' + base64.b64encode(key_id+KEY.sign(body)) + b'\n'
    assert sign_note(CHECKPOINT,ORIGIN,KEY) == expected
    assert verify(expected) == CHECKPOINT
    assert sign_note(CHECKPOINT,ORIGIN,KEY) == expected


@pytest.mark.parametrize('size', [True,-1,2**63,1.0])
def test_invalid_size(size):
    with pytest.raises(ValueError): Checkpoint(ORIGIN,size,ROOT)


@pytest.mark.parametrize('origin', ['', 'bad\norigin','bad name','bad+name','x'*256])
def test_invalid_origin(origin):
    with pytest.raises(ValueError): Checkpoint(origin,7,ROOT)


def test_empty_tree_root_and_length():
    empty = Checkpoint(ORIGIN,0,hashlib.sha256(b'').digest())
    assert verify(sign_note(empty,ORIGIN,KEY)) == empty
    with pytest.raises(ValueError): Checkpoint(ORIGIN,0,ROOT)
    with pytest.raises(ValueError): Checkpoint(ORIGIN,7,b'x')


@pytest.mark.parametrize('change', [
    lambda n: n.replace(b'\n7\n',b'\n8\n'),
    lambda n: n.replace(b'\n7\n',b'\n07\n'),
    lambda n: n.replace(b'\n7\n',b'\n+7\n'),
    lambda n: n.replace(b'\n',b'\r\n'),
    lambda n: n[:-1],
    lambda n: n+b'\n',
    lambda n: n.replace(b'\n\n',b'\nextension\n\n'),
    lambda n: n+n.split(b'\n\n')[1],
    lambda n: b'x'*1025,
    lambda n: n.replace(b'\xe2\x80\x94 ',b'- '),
    lambda n: n.replace(base64.b64encode(ROOT),base64.b64encode(bytes(32))),
])
def test_malformed_or_modified_note_rejected(change):
    assert verify(change(sign_note(CHECKPOINT,ORIGIN,KEY))) is None


def test_pinned_name_key_origin_and_key_id():
    note = sign_note(CHECKPOINT,ORIGIN,KEY)
    assert verify(note,origin='another.example') is None
    assert verify(note,key=bytes(32)) is None
    assert verify_note(note,expected_origin=ORIGIN,trusted_key_name='other',trusted_public_key=PUBLIC) is None
    prefix, payload = note.rsplit(b' ',1)
    raw = base64.b64decode(payload.strip())
    for offset in (0,4,67):
        changed = raw[:offset]+bytes([raw[offset]^1])+raw[offset+1:]
        assert verify(prefix+b' '+base64.b64encode(changed)+b'\n') is None
    assert verify(prefix+b' '+base64.b64encode(raw)+b'=\n') is None
