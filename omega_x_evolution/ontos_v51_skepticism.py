"""Read-only memory skepticism audit; no memory promotion or trust authority.

A verified SHA-256 payload match is not authenticated origin. Separate
independence groups are only caller assertions, NOT proven independence.
Optional stopping, data selection and unregistered hypotheses can invalidate
interpretations of reported e-values. All output remains quarantined.
"""
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
import re

_TOKEN = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')


def _name(x: object) -> bool:
    return type(x) is str and _TOKEN.fullmatch(x) is not None


def _sha(x: object) -> bool:
    return type(x) is str and _SHA.fullmatch(x) is not None


def _timestamp(x: object) -> bool:
    return type(x) is int and 0 <= x < 2**63


@dataclass(frozen=True, slots=True)
class MemoryEvent:
    tenant: str
    candidate_sha256: str
    ident: str
    group: str
    source_sha256: str
    positive: bool | None
    valid_from: int
    valid_until: int
    recorded_at: int

    def __post_init__(self) -> None:
        if (not _name(self.tenant) or not _sha(self.candidate_sha256)
                or not _name(self.ident) or not _name(self.group)
                or not _sha(self.source_sha256)
                or self.positive is not None and type(self.positive) is not bool
                or not all(_timestamp(x) for x in (self.valid_from, self.valid_until, self.recorded_at))
                or self.valid_from >= self.valid_until):
            raise ValueError('invalid bounded evidence event')


def review_evidence(events: tuple[MemoryEvent, ...], *, tenant: str,
                    candidate_sha256: str, valid_at: int, known_at: int,
                    verified_sources: frozenset[str]) -> dict:
    """Bitemporal revision and fixed-horizon likelihood-ratio diagnostic.

    The final likelihood ratio is for a *pre-specified* fixed Bernoulli
    experiment (null p=1/4, alternative p=1/2), not an adaptive PACE e-process.
    No accept/promotion result is emitted. A review hint is not authorization.
    """
    if (type(events) is not tuple or len(events) > 256
            or any(type(e) is not MemoryEvent for e in events)
            or not _name(tenant) or not _sha(candidate_sha256)
            or not _timestamp(valid_at) or not _timestamp(known_at)
            or type(verified_sources) is not frozenset
            or len(verified_sources) > 64
            or any(not _sha(s) for s in verified_sources)):
        raise ValueError('memory audit bounds')
    if any(e.tenant != tenant or e.candidate_sha256 != candidate_sha256 for e in events):
        raise ValueError('tenant/candidate mismatch')

    # Replay protection: latest transaction supersedes its entire previous
    # version, even when the new version no longer covers the requested valid time.
    latest: dict[str, MemoryEvent] = {}
    for raw in events:
        e = MemoryEvent(raw.tenant, raw.candidate_sha256, raw.ident, raw.group,
                        raw.source_sha256, raw.positive, raw.valid_from,
                        raw.valid_until, raw.recorded_at)
        if e.recorded_at > known_at:
            continue
        old = latest.get(e.ident)
        if old is None or e.recorded_at > old.recorded_at:
            latest[e.ident] = e
        elif e.recorded_at == old.recorded_at and e != old:
            raise ValueError('ambiguous same-transaction evidence')
    selected = sorted((e for e in latest.values() if e.valid_from <= valid_at < e.valid_until
                       and e.positive is not None), key=lambda e: (e.group,e.ident))
    if len(selected) > 64:
        raise ValueError('evidence inference budget')
    groups = [e.group for e in selected]
    if len(set(groups)) != len(groups):
        raise ValueError('independence group collision')

    ratio = Fraction(1)
    for event in selected:
        ratio *= Fraction(2) if event.positive else Fraction(2,3)
    sources = tuple(sorted({e.source_sha256 for e in selected}))
    provenance_matches = bool(selected) and all(source in verified_sources for source in sources)
    eligible = provenance_matches and len(selected)>=5 and ratio>=20
    return {
        'decision': ('QUARANTINE_UNVERIFIED_SOURCE' if not provenance_matches
                     else 'QUARANTINED_REVIEW_ONLY'),
        'eligible_for_manual_review': eligible,
        'e_value': ratio,
        'evidence_count': len(selected),
        'positive_count': sum(e.positive for e in selected),
        'negative_count': sum(not e.positive for e in selected),
        'source_digests': sources,
        'independence_verified': False,
        'provenance_payload_hash_matched': provenance_matches,
        'valid_at': valid_at,
        'known_at': known_at,
    }
