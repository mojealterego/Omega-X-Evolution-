"""Bind final L12 evidence admission to a fresh, externally pinned witness tip.

Operational trust here describes the authority, not the experiment mode.
The caller must retain the previous receipt independently and supply a fresh
unpredictable challenge. This is not a key provisioning or deployment service.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from .ontos_v72_checkpoint_note import Checkpoint, verify_note
from .ontos_v72_jcs import canonical_json
from .ontos_v72_merkle import leaf_hash, verify_inclusion
from .ontos_v72_receipts import ReceiptScope, _prime_order_point
from .ontos_v72_witness import WitnessPolicy, WitnessReceipt, verify_witness_transition

from .ontos_v72_quorum import QuorumPolicy, QuorumCertificate, verify_quorum_review

GATE_IDS = tuple(f'GATE-0{i}' for i in range(1, 9))
_HEX = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)


@dataclass(frozen=True, slots=True)
class AnchorTrust:
    policy: WitnessPolicy
    previous: WitnessReceipt
    challenge: bytes


@dataclass(frozen=True, slots=True)
class AnchorEvidence:
    current: WitnessReceipt
    consistency: tuple[bytes, ...]
    inclusion: tuple[bytes, ...]


@dataclass(frozen=True, slots=True)
class QuorumAnchorTrust:
    policy: QuorumPolicy
    previous: Checkpoint
    challenge: bytes


@dataclass(frozen=True, slots=True)
class QuorumAnchorEvidence:
    certificate: QuorumCertificate
    inclusion: tuple[bytes, ...]


def review_leaf(*, commit_sha: str, tenant: str, manifest_pin: str, campaign_pin: str,
                trust: dict[str, tuple[ReceiptScope, bytes]], receipts: dict[str, dict]) -> bytes:
    """Canonical leaf for the exact eight authenticated receipts and trust pins.

    The reducer must authenticate the receipts and artifacts separately; this
    function commits to them, it does not interpret their test results.
    """
    ReceiptScope('L12', 'GATE-01', commit_sha, tenant, 'policy')
    if (any(type(x) is not str or not _HEX.fullmatch(x) for x in (manifest_pin, campaign_pin))
            or type(trust) is not dict or set(trust) != set(GATE_IDS)
            or type(receipts) is not dict or set(receipts) != set(GATE_IDS)):
        raise ValueError('complete pinned review required')
    gates = []
    for gate in GATE_IDS:
        pair = trust[gate]
        if type(pair) is not tuple or len(pair) != 2:
            raise ValueError('trusted evaluator pair required')
        scope, key = pair
        if (type(scope) is not ReceiptScope or scope.level_id != 'L12' or scope.gate_id != gate
                or scope.commit_sha != commit_sha or scope.tenant != tenant
                or not _prime_order_point(key) or type(receipts[gate]) is not dict):
            raise ValueError('invalid review scope or key')
        gates.append({'scope': scope.body(), 'key': key.hex(),
                      'receipt_sha256': sha256(canonical_json(receipts[gate])).hexdigest()})
    return canonical_json({'schema': 'omega-v75-witness-review-v1', 'level': 'L12',
                           'commit_sha': commit_sha, 'tenant': tenant,
                           'manifest_sha256': manifest_pin, 'campaign_sha256': campaign_pin,
                           'gates': gates})


def verify_review_anchor(data: bytes, trust: AnchorTrust | QuorumAnchorTrust,
                         evidence: AnchorEvidence | QuorumAnchorEvidence,
                         evaluator_keys: tuple[bytes, ...]) -> bool:
    """Require operational authority and the exact review at the witness tip.

    A separate retained client pin and challenge are trusted inputs, not values
    learned from the candidate evidence. A newer tip invalidates older reviews.
    """
    # The operator's trusted input selects the mode. Evidence cannot downgrade it.
    if type(trust) is QuorumAnchorTrust:
        return (type(evidence) is QuorumAnchorEvidence and verify_quorum_review(
            data, trust.policy, trust.previous, trust.challenge, evidence.certificate,
            evidence.inclusion, evaluator_keys))
    try:
        if (type(trust) is not AnchorTrust or type(evidence) is not AnchorEvidence
                or type(trust.policy) is not WitnessPolicy or trust.policy.environment != 'operational'
                or type(trust.previous) is not WitnessReceipt or type(evidence.current) is not WitnessReceipt
                or type(trust.challenge) is not bytes or len(trust.challenge) != 32
                or trust.challenge == trust.previous.challenge
                or type(evaluator_keys) is not tuple or not 1 <= len(evaluator_keys) <= 8
                or any(not _prime_order_point(k) for k in evaluator_keys)
                or trust.policy.log_key in evaluator_keys or trust.policy.witness_key in evaluator_keys):
            return False
        digest = leaf_hash(data)
        if not verify_witness_transition(evidence.current, trust.policy, trust.challenge,
                                         trust.previous, evidence.consistency):
            return False
        checkpoint = verify_note(evidence.current.note, expected_origin=trust.policy.origin,
                                 trusted_key_name=trust.policy.log_name,
                                 trusted_public_key=trust.policy.log_key)
        return (checkpoint is not None and checkpoint.tree_size > 0
                and verify_inclusion(digest, checkpoint.tree_size - 1, checkpoint.tree_size,
                                     evidence.inclusion, checkpoint.root))
    except (ValueError, TypeError, OverflowError, RecursionError):
        return False
