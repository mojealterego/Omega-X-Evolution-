"""Authenticated, bounded sequential review of quarantined v51 memory evidence.

Offline research only: no memory promotion, tool access, or privilege changes.
The fixed factors are 3/2 (positive), 1/2 (negative), 1 (abstention).
Conditional validity requires P(positive|past) <= P(negative|past) on every
registered candidate trial, including the abstention mechanism. Authenticity
and deduplication do not establish this premise or prove evaluator honesty.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import re

from .ontos_v46_gate_audit import family_alpha_bound
from .ontos_v51_skepticism import MemoryEvent
from .ontos_v72_jcs import canonical_json
from .ontos_v72_receipts import _prime_order_point, strict_verify

_MAX_TRIALS = 4096
_MAX_CANDIDATES = 32
_DOMAIN = b'OMEGA-X/v51/sequential-memory/v1\x00'
_HEX = re.compile(r'[a-f0-9]{64}\Z')
_NAME = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')


def _sha(value: object) -> bool:
    return type(value) is str and _HEX.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class ReviewPlan:
    tenant: str
    candidates: tuple[str, ...]
    evaluator_key: bytes
    horizon: int
    alpha: Fraction = Fraction(1, 20)

    def __post_init__(self) -> None:
        if (type(self.tenant) is not str or _NAME.fullmatch(self.tenant) is None
                or type(self.candidates) is not tuple
                or not 1 <= len(self.candidates) <= _MAX_CANDIDATES
                or any(not _sha(c) for c in self.candidates)
                or tuple(sorted(set(self.candidates))) != self.candidates
                or type(self.horizon) is not int or not 1 <= self.horizon <= 240
                or len(self.candidates)*self.horizon > _MAX_TRIALS
                or type(self.alpha) is not Fraction
                or not 0 < self.alpha <= Fraction(1, 20)
                or self.alpha.denominator > 10**6
                or not _prime_order_point(self.evaluator_key)):
            raise ValueError('invalid fixed memory review plan')

    @property
    def sha256(self) -> str:
        self.__post_init__()
        body = {'tenant': self.tenant, 'candidates': list(self.candidates),
                'evaluator_key': self.evaluator_key.hex(), 'horizon': self.horizon,
                'alpha': [self.alpha.numerator, self.alpha.denominator],
                'multipliers': ['3/2', '1/2', '1'],
                'allocation': 'equal-fixed-family-v1'}
        return hashlib.sha256(_DOMAIN+b'plan\x00'+canonical_json(body)).hexdigest()


def signing_payload(plan_sha256: str, previous: str, sequence: int,
                    event: MemoryEvent) -> bytes:
    """Canonical payload for the separately controlled evaluator's signer."""
    if (not _sha(plan_sha256) or not _sha(previous)
            or type(sequence) is not int or not 1 <= sequence <= _MAX_TRIALS
            or type(event) is not MemoryEvent):
        raise ValueError('invalid signed trial envelope')
    event.__post_init__()
    # Encode 63-bit timestamps as canonical decimal strings, avoiding JSON's
    # safe-integer limit without losing information.
    return _DOMAIN+b'trial\x00'+canonical_json({
        'plan': plan_sha256, 'previous': previous, 'sequence': sequence,
        'tenant': event.tenant, 'candidate': event.candidate_sha256,
        'ident': event.ident, 'group': event.group, 'source': event.source_sha256,
        'positive': event.positive, 'valid_from': str(event.valid_from),
        'valid_until': str(event.valid_until), 'recorded_at': str(event.recorded_at),
    })


@dataclass(frozen=True, slots=True)
class SignedTrial:
    previous: str
    sequence: int
    event: MemoryEvent
    signature: bytes

    def sha256(self, plan_sha256: str) -> str:
        if type(self.signature) is not bytes or len(self.signature) != 64:
            raise ValueError('invalid trial signature shape')
        payload = signing_payload(plan_sha256, self.previous, self.sequence, self.event)
        return hashlib.sha256(_DOMAIN+b'link\x00'+payload+self.signature).hexdigest()


@dataclass(frozen=True, slots=True)
class CandidateReview:
    candidate_sha256: str
    count: int
    wealth: Fraction
    status: str


@dataclass(frozen=True, slots=True)
class FamilyReview:
    head: str
    family_alpha: Fraction
    per_candidate_alpha: Fraction
    candidates: tuple[CandidateReview, ...]
    retained_head_verified: bool
    null_verified: bool = False
    promotion_authorized: bool = False


def review_family(plan: ReviewPlan, expected_plan_sha256: str,
                  trials: tuple[SignedTrial, ...], *,
                  expected_head: str | None = None) -> FamilyReview:
    """Replay the complete signed family history, with irreversible stop.

    The plan hash must have been pinned before observing outcomes. An optional
    externally retained exact head detects truncation relative to that head;
    absent a head, completeness/freshness is unproved. Neither hash proves
    that registration predates outcomes. No memory candidate is promoted.
    Reject corrections, duplicate evidence and continuation after a stop.
    """
    if type(plan) is not ReviewPlan or not _sha(expected_plan_sha256):
        raise ValueError('independently pinned review plan required')
    pin = plan.sha256
    if (pin != expected_plan_sha256 or type(trials) is not tuple
            or len(trials) > len(plan.candidates)*plan.horizon
            or expected_head is not None and not _sha(expected_head)):
        raise ValueError('review plan/history bounds or pin mismatch')
    alpha = plan.alpha / len(plan.candidates)
    family_bound = family_alpha_bound((alpha,)*len(plan.candidates))
    threshold = 1/alpha
    results = {c: CandidateReview(c, 0, Fraction(1), 'PENDING') for c in plan.candidates}
    identities: dict[str, set[str]] = {c: set() for c in plan.candidates}
    groups: dict[str, set[str]] = {c: set() for c in plan.candidates}
    sources: dict[str, set[str]] = {c: set() for c in plan.candidates}
    head, last_time = pin, -1
    for seq, trial in enumerate(trials, 1):
        if (type(trial) is not SignedTrial or trial.previous != head
                or type(trial.sequence) is not int or trial.sequence != seq):
            raise ValueError('noncontiguous trial history')
        payload = signing_payload(pin, head, seq, trial.event)
        if not strict_verify(plan.evaluator_key, payload, trial.signature):
            raise ValueError('invalid evaluator signature')
        e = trial.event
        c = e.candidate_sha256
        if (e.tenant != plan.tenant or c not in results
                or e.recorded_at <= last_time or results[c].status != 'PENDING'
                or e.ident in identities[c] or e.group in groups[c]
                or e.source_sha256 in sources[c]):
            raise ValueError('unregistered, replayed, backdated or stopped trial')
        identities[c].add(e.ident)
        groups[c].add(e.group)
        sources[c].add(e.source_sha256)
        count = results[c].count+1
        factor = Fraction(3,2) if e.positive is True else (Fraction(1,2) if e.positive is False else Fraction(1))
        wealth = results[c].wealth*factor
        status = 'REVIEW_THRESHOLD' if wealth >= threshold else ('EXHAUSTED' if count == plan.horizon else 'PENDING')
        results[c] = CandidateReview(c, count, wealth, status)
        head, last_time = trial.sha256(pin), e.recorded_at
    if expected_head is not None and head != expected_head:
        raise ValueError('history does not match independently retained exact head')
    return FamilyReview(head, family_bound, alpha,
                        tuple(results.values()), expected_head is not None)
