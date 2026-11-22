"""Constrained proof/transport tests using functional polynomial witness checking."""
import hashlib
import hmac
import random
import struct
import pytest

from omega_x_evolution.polyglot import Program, LANGUAGES
from omega_x_evolution.rsi_ir_guard import (
    Policy, CAPABILITIES, HEADER, TAG_BYTES, MAX_SEQUENCE, open_ir,
    seal_ir, review_equivalence, review_policy, policy_distance,
)

KEY = bytes(range(32))
BASE = Program(('add', ('x',), ('y',)))
EQUIV = Program(('sub', ('add', ('x',), ('y',)), ('lit', 0)))
WRONG = Program(('mul', ('x',), ('y',)))


def test_default_trusted_policy_and_hamming_scope():
    p = Policy()
    assert p.mandatory == ('ast', 'formal', 'cascade', 'audit', 'budget', 'quorum')
    assert policy_distance(p, p) == 0
    q = Policy(capabilities=('compiler', 'local_eval'))
    assert policy_distance(p, q) == 1
    assert review_policy(p, q)['eligible'] is False
    assert review_policy(p, q)['human_values_alignment_proved'] is False


def test_tighter_policy_is_eligible_for_human_review_not_auto_deployment():
    p = Policy(capabilities=('compiler', 'local_eval'), max_work=200)
    q = Policy(capabilities=('local_eval',), max_work=100, max_memory_bytes=1024)
    r = review_policy(p, q)
    assert r['eligible'] is True
    assert r['release_authorized'] is False
    assert len(r['reference_sha256']) == 64


@pytest.mark.parametrize('kwargs', [
    {'mandatory': ('ast',)}, {'mandatory': list(Policy().mandatory)},
    {'capabilities': ('network', 'local_eval')}, {'capabilities': ('root',)},
    {'capabilities': ('local_eval', 'local_eval')}, {'max_work': True},
    {'max_work': -1}, {'max_work': 10**400}, {'max_memory_bytes': 0},
    {'approval_required': False}, {'approval_required': 1},
])
def test_reject_policy_weakening_and_malformed_fields(kwargs):
    with pytest.raises(ValueError): Policy(**kwargs)


def test_policy_mutation_after_construction_rejected():
    p = Policy()
    object.__setattr__(p, 'approval_required', False)
    with pytest.raises(ValueError): p.digest
    with pytest.raises(ValueError): seal_ir(BASE, p, backend='go', sequence=1, key=KEY)


def test_proved_functional_equivalence_is_not_human_values_proof():
    r = review_equivalence(BASE, EQUIV, Policy())
    assert r['status'] == 'PROVED_EQUIVALENT'
    assert r['eligible_for_human_review'] is True
    assert r['release_authorized'] is False
    assert r['human_values_alignment_proved'] is False
    assert len(r['proof_sha256']) == 64


def test_semantically_different_and_unsupported_ir_fail_closed():
    wrong = review_equivalence(BASE, WRONG, Policy())
    assert wrong['eligible_for_human_review'] is False
    bitwise = review_equivalence(Program(('xor', ('x',), ('y',))),
                                 Program(('xor', ('x',), ('y',))), Policy())
    assert bitwise['status'] == 'UNKNOWN' and not bitwise['eligible_for_human_review']


def test_mutated_program_rejected_before_proof_or_transport():
    p = Program(('x',))
    object.__setattr__(p, 'tree', ('lit', 'evil'))
    with pytest.raises(ValueError): review_equivalence(p, BASE, Policy())
    with pytest.raises(ValueError): seal_ir(p, Policy(), backend='go', sequence=1, key=KEY)


@pytest.mark.parametrize('lang', LANGUAGES)
def test_binary_roundtrip_each_supported_backend(lang):
    p = Program(('xor', ('mul', ('x',), ('lit', 65535)), ('or', ('y',), ('lit', 10))))
    frame = seal_ir(p, Policy(), backend=lang, sequence=12, key=KEY)
    assert frame.startswith(b'OU16')
    assert len(frame) == HEADER.size + TAG_BYTES + 11
    received = open_ir(frame, Policy(), last_sequence=11, key=KEY)
    assert received.program == p and received.backend == lang and received.sequence == 12
    assert received.policy_sha256 == Policy().digest


def test_hmac_rejects_tampered_payload_header_or_mac():
    f = seal_ir(BASE, Policy(), backend='c', sequence=1, key=KEY)
    for index in (0, 4, 5, 6, HEADER.size, len(f)-1):
        t=bytearray(f);t[index]^=1
        with pytest.raises(ValueError): open_ir(bytes(t), Policy(), last_sequence=0, key=KEY)


def test_replay_and_policy_mismatch_and_wrong_keys():
    p = Policy()
    f = seal_ir(BASE, p, backend='python', sequence=42, key=KEY)
    with pytest.raises(ValueError): open_ir(f, p, last_sequence=42, key=KEY)
    with pytest.raises(ValueError): open_ir(f, p, last_sequence=43, key=KEY)
    with pytest.raises(ValueError): open_ir(f, Policy(capabilities=()), last_sequence=0, key=KEY)
    with pytest.raises(ValueError): open_ir(f, p, last_sequence=0, key=b'z'*32)


def test_retagged_malformed_binary_is_rejected_by_decoder():
    raw = seal_ir(BASE, Policy(), backend='go', sequence=1, key=KEY)
    for bad_tree in (b'\xff', b'\x02', b'\x02\x12', b'\x00\x00', b'\x03\x00'):
        prefix=HEADER.pack(b'OU16', 1, LANGUAGES.index('go'), 1, len(bad_tree), bytes.fromhex(Policy().digest))
        body=prefix+bad_tree
        frame=body+hmac.digest(KEY, body, 'sha256')
        with pytest.raises(ValueError):open_ir(frame, Policy(), last_sequence=0, key=KEY)


@pytest.mark.parametrize('bad', [True, -1, 2**64, 1.5, None])
def test_out_of_range_sequence_rejected(bad):
    with pytest.raises(ValueError):seal_ir(BASE, Policy(), backend='go', sequence=bad, key=KEY)


def test_open_rejects_wrong_shape_and_backends():
    with pytest.raises(ValueError):seal_ir(BASE, Policy(), backend='shell', sequence=1, key=KEY)
    with pytest.raises(ValueError):seal_ir(BASE, Policy(), backend='go', sequence=1, key=b'weak')
    with pytest.raises(ValueError):open_ir(bytearray(b'123'), Policy(), last_sequence=0, key=KEY)
    with pytest.raises(ValueError):open_ir(b'123', Policy(), last_sequence=0, key=KEY)
    with pytest.raises(ValueError):open_ir(b'123', Policy(), last_sequence=-1, key=KEY)


def test_deterministic_wire_and_property_roundtrip_seed_41():
    r = random.Random(41)
    for i in range(250):
        tree = ('add', ('lit', r.randrange(65536)), ('xor', ('x',), ('lit', r.randrange(65536))))
        p=Program(tree)
        data=seal_ir(p, Policy(), backend='java', sequence=i+1, key=KEY)
        assert data == seal_ir(p, Policy(), backend='java', sequence=i+1, key=KEY)
        assert open_ir(data, Policy(), last_sequence=i, key=KEY).program == p


def test_policy_restricts_new_rights_while_hamming_can_increase():
    before = Policy(capabilities=('compiler','external_tool','local_eval','network'), max_work=10000)
    after = Policy(capabilities=('local_eval',), max_work=5000)
    assert review_policy(before, after)['eligible']
    assert policy_distance(before, after) == 3
    # Not a surrogate ethical alignment score: smaller permissions -> larger Hamming drift.


def test_composite_guard_requires_trusted_external_anchor_and_equivalence():
    from omega_x_evolution.rsi_ir_guard import review_candidate
    policy = Policy()
    ok = review_candidate(BASE, EQUIV, policy, policy, trusted_baseline_digest=policy.digest)
    assert ok['status'] == 'PROVED_NARROW_INVARIANTS'
    assert not ok['release_authorized'] and ok['human_review_required']
    no = review_candidate(BASE, WRONG, policy, policy, trusted_baseline_digest=policy.digest)
    assert no['status'] == 'UNKNOWN_OR_NOT_EQUIVALENT'
    with pytest.raises(ValueError):
        review_candidate(BASE, EQUIV, policy, policy, trusted_baseline_digest='0'*64)
    with pytest.raises(ValueError):
        review_candidate(BASE, EQUIV, policy, policy, trusted_baseline_digest='AAAA')


def test_composite_guard_rejects_escalation_before_functional_check():
    from omega_x_evolution.rsi_ir_guard import review_candidate
    p=Policy()
    proposal=Policy(capabilities=('compiler','local_eval'))
    out=review_candidate(BASE, EQUIV, p, proposal, trusted_baseline_digest=p.digest)
    assert out['status']=='REJECT' and out['functional'] is None


def test_malformed_capability_values_fail_closed():
    with pytest.raises(ValueError): Policy(capabilities=({'x': 1},))
    with pytest.raises(ValueError): Policy(capabilities=(["network"],))


def test_binary_opcode_schema_pinned():
    f=seal_ir(BASE, Policy(), backend='python', sequence=1, key=KEY)
    assert f[HEADER.size:-TAG_BYTES] == b'\x03\x00\x01'
