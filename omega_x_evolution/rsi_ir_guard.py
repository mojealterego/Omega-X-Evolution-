"""Bounded RSI policy-invariant review and authenticated binary transport of u16 IR.

This proves only fixed, formally checked program semantics and monotone machine
policy constraints. It does NOT prove human values, CEV, zero reward hacking,
compiler correctness, Zenoh latency, or authorization to deploy mutations.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import struct

from .epigenetics import MANDATORY
from .polyglot import LANGUAGES, OPS, Program, _validated_tree

CAPABILITIES = ('compiler', 'external_tool', 'filesystem_write', 'local_eval', 'network')
MAGIC = b'OU16'
VERSION = 1
HEADER = struct.Struct('!4sBBQH32s')
TAG_BYTES = 32
MAX_SEQUENCE = (1 << 64) - 1
MAX_PAYLOAD = 256
_CODE = {'x': 0, 'y': 1, 'lit': 2, 'add': 3, 'sub': 4, 'mul': 5,
         'xor': 6, 'and': 7, 'or': 8}
if set(_CODE) != set(OPS) | {'x', 'y', 'lit'}:
    raise RuntimeError('IR schema changed without protocol revision')
_DEC = {v: k for k, v in _CODE.items()}


def _valid_int(value: object, upper: int) -> bool:
    return type(value) is int and 0 <= value <= upper


def _valid_key(key: object) -> bool:
    return type(key) is bytes and 32 <= len(key) <= 4096


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


@dataclass(frozen=True, slots=True)
class Policy:
    """Human/operator baseline is outside the candidate-controlled RSI domain."""
    mandatory: tuple[str, ...] = MANDATORY
    capabilities: tuple[str, ...] = ('local_eval',)
    max_work: int = 100000
    max_memory_bytes: int = 16 * 1024 * 1024
    approval_required: bool = True

    def __post_init__(self) -> None:
        if (type(self.mandatory) is not tuple or self.mandatory != MANDATORY
                or type(self.capabilities) is not tuple
                or any(type(v) is not str or v not in CAPABILITIES for v in self.capabilities)
                or tuple(sorted(set(self.capabilities))) != self.capabilities
                or not _valid_int(self.max_work, 1_000_000_000) or self.max_work == 0
                or not _valid_int(self.max_memory_bytes, 1 << 40) or self.max_memory_bytes == 0
                or self.approval_required is not True):
            raise ValueError('invalid or weakened trusted policy')

    @property
    def digest(self) -> str:
        self.__post_init__()
        return hashlib.sha256(_canonical({'schema': 'omega-rsi-policy-v1',
            'mandatory': self.mandatory, 'capabilities': self.capabilities,
            'max_work': self.max_work, 'max_memory_bytes': self.max_memory_bytes,
            'approval_required': self.approval_required})).hexdigest()


def policy_distance(reference: Policy, candidate: Policy) -> int:
    """Bitwise Hamming distance of *machine permissions*, NOT moral alignment."""
    if type(reference) is not Policy or type(candidate) is not Policy:
        raise ValueError('typed policy required')
    reference.__post_init__(); candidate.__post_init__()
    return sum((k in reference.capabilities) != (k in candidate.capabilities)
               for k in CAPABILITIES)


def review_policy(reference: Policy, candidate: Policy) -> dict:
    """Non-escalation checker; only a trusted human can replace reference."""
    if type(reference) is not Policy or type(candidate) is not Policy:
        raise ValueError('typed policy required')
    reference.__post_init__(); candidate.__post_init__()
    new_rights = set(candidate.capabilities) - set(reference.capabilities)
    eligible = not new_rights and candidate.max_work <= reference.max_work and candidate.max_memory_bytes <= reference.max_memory_bytes
    return {'schema': 'omega-rsi-policy-review-v1', 'eligible': eligible,
            'permission_hamming_distance': policy_distance(reference, candidate),
            'reason': 'monotone non-escalation' if eligible else 'capability or budget escalation',
            'reference_sha256': reference.digest, 'candidate_sha256': candidate.digest,
            'human_values_alignment_proved': False, 'release_authorized': False}


def review_equivalence(reference: Program, candidate: Program, policy: Policy) -> dict:
    """Independent algebraic certificate replay over all (u16,u16) inputs.

    Restricted to polynomial add/sub/mul IR checked by proof_kernel; an
    unsupported operation produces UNKNOWN, never a guessed proof.
    """
    if type(policy) is not Policy:
        raise ValueError('typed policy required')
    policy.__post_init__()
    left = Program(_validated_tree(reference))
    right = Program(_validated_tree(candidate))
    from .proof_kernel import certify, verify_certificate
    result = {'schema': 'omega-rsi-functional-review-v1', 'policy_sha256': policy.digest,
              'program_sha256': hashlib.sha256(_canonical(right.tree)).hexdigest(),
              'status': 'UNKNOWN', 'eligible_for_human_review': False,
              'release_authorized': False, 'human_values_alignment_proved': False}
    try:
        proof = certify(left, right)
        if proof.get('proved') is True and verify_certificate(left, right, proof):
            result.update({'status': 'PROVED_EQUIVALENT', 'eligible_for_human_review': True,
                          'proof_sha256': hashlib.sha256(_canonical(proof)).hexdigest()})
        elif proof.get('reason') == 'unknown: different normal forms':
            result['status'] = 'NOT_EQUIVALENT_OR_UNKNOWN'
    except (ArithmeticError, ValueError, TypeError, RecursionError):
        pass
    return result


def review_candidate(reference: Program, candidate: Program,
                     baseline: Policy, proposed: Policy, *,
                     trusted_baseline_digest: str) -> dict:
    """Composite fail-closed RSI guard; does not authorize deployment.

    The trusted digest must originate outside candidate-controlled storage.
    Proven equivalence is for pure u16 functionality only, NOT ethical values.
    """
    if (type(trusted_baseline_digest) is not str or len(trusted_baseline_digest) != 64
            or any(c not in '0123456789abcdef' for c in trusted_baseline_digest)):
        raise ValueError('external baseline anchor required')
    if type(baseline) is not Policy or not hmac.compare_digest(
            trusted_baseline_digest, baseline.digest):
        raise ValueError('baseline anchor mismatch')
    p = review_policy(baseline, proposed)
    if not p['eligible']:
        return {'schema': 'omega-rsi-composite-v1', 'status': 'REJECT',
                'reason': p['reason'], 'policy': p, 'functional': None,
                'release_authorized': False, 'human_review_required': True}
    f = review_equivalence(reference, candidate, proposed)
    return {'schema': 'omega-rsi-composite-v1',
            'status': 'PROVED_NARROW_INVARIANTS' if f['eligible_for_human_review']
                      else 'UNKNOWN_OR_NOT_EQUIVALENT',
            'reason': 'policy and bounded u16 functional equivalence checked',
            'policy': p, 'functional': f,
            'release_authorized': False, 'human_review_required': True}


def _encode_tree(program: Program) -> bytes:
    tree = _validated_tree(program)
    def visit(t: tuple) -> bytes:
        op = t[0]
        prefix = bytes((_CODE[op],))
        if op == 'lit':
            return prefix + struct.pack('!H', t[1])
        if op in ('x', 'y'):
            return prefix
        return prefix + visit(t[1]) + visit(t[2])
    return visit(tree)


def _decode_tree(raw: bytes) -> Program:
    pos = 0
    def read(depth: int):
        nonlocal pos
        if depth > 8 or pos >= len(raw):
            raise ValueError('invalid IR depth or length')
        code = raw[pos]; pos += 1
        op = _DEC.get(code)
        if op is None:
            raise ValueError('unsupported IR opcode')
        if op == 'lit':
            if pos + 2 > len(raw):
                raise ValueError('truncated literal')
            value = struct.unpack_from('!H', raw, pos)[0]
            pos += 2
            return (op, value)
        if op in ('x', 'y'):
            return (op,)
        return (op, read(depth+1), read(depth+1))
    tree = read(0)
    if pos != len(raw):
        raise ValueError('trailing IR bytes')
    return Program(tree)


@dataclass(frozen=True, slots=True)
class ReceivedIR:
    program: Program
    backend: str
    sequence: int
    policy_sha256: str


def seal_ir(program: Program, policy: Policy, *, backend: str, sequence: int, key: bytes) -> bytes:
    """Binary u16 AST frame, HMAC-bound to trusted policy and sequence."""
    if type(policy) is not Policy or not _valid_key(key) or type(backend) is not str or backend not in LANGUAGES:
        raise ValueError('invalid transport authority or backend')
    if not _valid_int(sequence, MAX_SEQUENCE):
        raise ValueError('invalid frame sequence')
    policy.__post_init__()
    tree = _encode_tree(program)
    if not 1 <= len(tree) <= MAX_PAYLOAD:
        raise ValueError('IR frame too large')
    header = HEADER.pack(MAGIC, VERSION, LANGUAGES.index(backend), sequence,
                         len(tree), bytes.fromhex(policy.digest))
    body = header + tree
    return body + hmac.digest(key, body, 'sha256')


def open_ir(frame: bytes, policy: Policy, *, last_sequence: int, key: bytes) -> ReceivedIR:
    """Fail closed before parsing; caller persists last_sequence outside actor RAM.

    HMAC prevents undetected frame alteration, not compromise of the shared key.
    Cannot prevent replay if both state and monotonic anchor are rolled back.
    """
    if (type(frame) is not bytes or type(policy) is not Policy or not _valid_key(key)
            or not _valid_int(last_sequence, MAX_SEQUENCE)
            or not HEADER.size+TAG_BYTES+1 <= len(frame) <= HEADER.size+TAG_BYTES+MAX_PAYLOAD):
        raise ValueError('invalid IR transport bounds')
    policy.__post_init__()
    magic, version, backend, sequence, length, digest = HEADER.unpack_from(frame)
    if magic != MAGIC or version != VERSION or backend >= len(LANGUAGES):
        raise ValueError('invalid frame header')
    if length < 1 or length > MAX_PAYLOAD or len(frame) != HEADER.size+length+TAG_BYTES:
        raise ValueError('frame length mismatch')
    if not hmac.compare_digest(frame[-TAG_BYTES:], hmac.digest(key, frame[:-TAG_BYTES], 'sha256')):
        raise ValueError('IR authentication failure')
    if digest != bytes.fromhex(policy.digest):
        raise ValueError('policy mismatch')
    if sequence <= last_sequence:
        raise ValueError('stale or replayed IR frame')
    program = _decode_tree(frame[HEADER.size:-TAG_BYTES])
    return ReceivedIR(program, LANGUAGES[backend], sequence, policy.digest)
