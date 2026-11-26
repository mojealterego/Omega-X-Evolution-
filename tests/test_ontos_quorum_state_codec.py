from dataclasses import replace
from hashlib import sha256
import struct

import pytest

from omega_x_evolution.ontos_quorum_state_codec import (
    QuorumStateRecord, encode_state, decode_state, MAX_CHALLENGES,
)


def token(i):
    return sha256(str(i).encode()).digest()


def record():
    return QuorumStateRecord('operational', 'omega/log', 'omega/signer', token(1), 1,
                             tuple(sorted(token(i) for i in range(3, 7))),
                             2**63 - 1, token(8), token(2), (token(7),),
                             (token(9), token(10), token(11)))


def test_roundtrip_preserves_all_history_and_63bit_checkpoint():
    state = record()
    assert decode_state(encode_state(state)) == state
    assert encode_state(decode_state(encode_state(state))) == encode_state(state)
    assert state.last_challenge == token(11)


@pytest.mark.parametrize('change', [
    {'challenges': ()}, {'challenges': (token(9), token(9))},
    {'retired_keys': (token(1),)}, {'retired_keys': (token(2),)},
    {'retired_keys': (token(3),)}, {'retired_keys': (token(7), token(7))},
    {'epoch': True}, {'epoch': 2**31}, {'tree_size': 2**63},
    {'root': b'x'}, {'origin': 'bad origin'}, {'environment': 'unknown'},
    {'log_key': token(2)}, {'witness_keys': (token(3),)*4},
    {'tree_size': 0}, {'challenges': (b'x',)}, {'retired_keys': [token(7)]},
])
def test_invalid_state_rejected(change):
    with pytest.raises(ValueError):
        encode_state(replace(record(), **change))


def test_empty_checkpoint_and_simulation_roundtrip():
    state = replace(record(), environment='simulation', tree_size=0, root=sha256(b'').digest(),
                    epoch=0, retired_keys=())
    assert decode_state(encode_state(state)) == state


def test_truncated_trailing_and_bad_magic_rejected():
    raw = encode_state(record())
    for n in range(len(raw)):
        with pytest.raises(ValueError):
            decode_state(raw[:n])
    for bad in (raw + b'\0', b'X' + raw[1:], bytearray(raw)):
        with pytest.raises(ValueError):
            decode_state(bad)


def test_nonce_count_cannot_force_unbounded_decode():
    raw = encode_state(record())
    # Count is immediately before the variable-length challenge tail.
    offset = len(raw) - 3*32 - 4
    bad = raw[:offset] + struct.pack('>I', 2**32 - 1) + raw[offset+4:]
    with pytest.raises(ValueError):
        decode_state(bad)


def test_capacity_is_explicit_and_no_history_is_truncated():
    state = replace(record(), challenges=tuple(token(i) for i in range(MAX_CHALLENGES)))
    raw = encode_state(state)
    assert len(raw) <= 1024*1024
    assert decode_state(raw) == state
    with pytest.raises(ValueError):
        encode_state(replace(state, challenges=state.challenges + (token(MAX_CHALLENGES),)))


def test_challenge_order_affects_serialization():
    state = record()
    assert encode_state(state) != encode_state(replace(state, challenges=state.challenges[::-1]))


def test_maximum_fields_fit_budget():
    state = replace(record(), origin='a'*255, log_name='b'*255,
                    retired_keys=tuple(sorted(token(i) for i in range(100000, 100128))),
                    challenges=tuple(token(i) for i in range(MAX_CHALLENGES)))
    raw = encode_state(state)
    assert len(raw) == 4 + 3 + 510 + 12 + 7*32 + 1 + 128*32 + 4 + MAX_CHALLENGES*32
    assert decode_state(raw) == state


def test_noncanonical_roster_and_duplicate_nonce_on_wire_rejected():
    raw = encode_state(record())
    offset = 7 + len(record().origin) + len(record().log_name) + 12 + 96
    swapped = raw[:offset] + raw[offset+32:offset+64] + raw[offset:offset+32] + raw[offset+64:]
    with pytest.raises(ValueError):
        decode_state(swapped)
    with pytest.raises(ValueError):
        decode_state(raw[:-32] + raw[-64:-32])


def test_deterministic_mutation_never_admits_noncanonical_bytes():
    import random
    rng = random.Random(20261126)
    raw = encode_state(record())
    for _ in range(1024):
        candidate = bytearray(raw)
        for _ in range(rng.randrange(1, 5)):
            candidate[rng.randrange(len(candidate))] ^= rng.randrange(1, 256)
        candidate = bytes(candidate)
        try:
            decoded = decode_state(candidate)
        except ValueError:
            continue
        assert encode_state(decoded) == candidate
