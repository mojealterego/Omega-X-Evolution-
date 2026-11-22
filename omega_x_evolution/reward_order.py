"""Finite reward-order inversion check; NOT a proof of universal alignment.

Operationalizes Definition 1 in Skalse et al., arXiv:2209.13085v2.
The reference policy values are caller-supplied and are not independently
attested here. An externally pinned digest protects against silent rewriting
of the declared benchmark but not against dishonest benchmark creation.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import hmac
import json
import re

_SCHEMA = 'omega-reward-order-finite-v1'
_NAME = re.compile(r'[a-z][a-z0-9_]{0,39}\Z', re.ASCII)
_VALUE = re.compile(r'-?(?:0|[1-9][0-9]{0,23})(?:\.[0-9]{1,30})?\Z', re.ASCII)
_MAX_POLICIES = 128


def _number(value: object) -> Decimal:
    if type(value) is not str or _VALUE.fullmatch(value) is None or len(value) > 60:
        raise ValueError('reward must be a bounded decimal string')
    return Decimal(value)


def _sha(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=True,
                     allow_nan=False, separators=(',', ':')).encode('ascii')
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class RewardScore:
    policy_id: str
    value: str

    def __post_init__(self) -> None:
        if type(self.policy_id) is not str or _NAME.fullmatch(self.policy_id) is None:
            raise ValueError('invalid policy_id')
        _number(self.value)


@dataclass(frozen=True, slots=True)
class RewardReference:
    """An operator-defined finite reference ordering, not ground-truth CEV."""
    scores: tuple[RewardScore, ...]

    def __post_init__(self) -> None:
        if (type(self.scores) is not tuple
                or not 2 <= len(self.scores) <= _MAX_POLICIES
                or any(type(s) is not RewardScore for s in self.scores)):
            raise ValueError('reference must contain 2..128 typed policies')
        for row in self.scores:
            row.__post_init__()  # detect mutation via object.__setattr__
        if len({row.policy_id for row in self.scores}) != len(self.scores):
            raise ValueError('duplicate policy_id')

    @property
    def digest(self) -> str:
        self.__post_init__()
        return _sha({'schema': _SCHEMA, 'reference': [
            [r.policy_id, r.value] for r in sorted(self.scores, key=lambda x: x.policy_id)
        ]})


def assess_reward_order(reference: RewardReference, proxy_scores: object, *,
                        trusted_reference_digest: str, witness_limit: int = 16) -> dict:
    """Exhaustively detect strict pairwise ordering inversions on listed policies.

    Given policies i,j, an inversion requires p(i)>p(j) AND r(i)<r(j),
    as in Definition 1 of Skalse et al. Ties are *not* inversions.
    Exact decimal arithmetic makes rounding unable to hide a strict reversal.
    Complexity O(n^2), bounded to n<=128. Returns bounded witnesses.

    A positive result is ONLY a finite mathematical statement about supplied
    values, not evidence of correctness of those values or future policies.
    """
    if type(reference) is not RewardReference:
        raise ValueError('typed reference required')
    reference.__post_init__()
    if (type(trusted_reference_digest) is not str or len(trusted_reference_digest) != 64
            or any(x not in '0123456789abcdef' for x in trusted_reference_digest)
            or not hmac.compare_digest(reference.digest, trusted_reference_digest)):
        raise ValueError('externally anchored reference SHA-256 required')
    if type(witness_limit) is not int or not 1 <= witness_limit <= _MAX_POLICIES:
        raise ValueError('invalid witness limit')
    ids = [r.policy_id for r in sorted(reference.scores, key=lambda x: x.policy_id)]
    base = {'schema': _SCHEMA, 'reference_sha256': trusted_reference_digest,
            'policy_scope': 'FINITE_LIST_ONLY', 'policies': len(ids),
            'pairs_compared': 0, 'inversion_count': 0, 'witnesses': [],
            'reference_attested': False, 'human_values_alignment_proved': False,
            'release_authorized': False}
    if (type(proxy_scores) is not dict or set(proxy_scores) != set(ids)
            or any(type(k) is not str for k in proxy_scores)):
        return {**base, 'status': 'REJECT_INVALID_EVIDENCE',
                'reason': 'missing, extra or malformed policy keys'}
    try:
        proxy = {k: _number(proxy_scores[k]) for k in ids}
    except (ValueError, TypeError):
        return {**base, 'status': 'REJECT_INVALID_EVIDENCE',
                'reason': 'invalid proxy score'}
    truth = {r.policy_id: _number(r.value) for r in reference.scores}
    inversions = 0
    witnesses = []
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            i, j = ids[a], ids[b]
            if ((proxy[i] > proxy[j] and truth[i] < truth[j])
                    or (proxy[j] > proxy[i] and truth[j] < truth[i])):
                inversions += 1
                if len(witnesses) < witness_limit:
                    high_proxy, high_reference = ((i, j) if proxy[i] > proxy[j] else (j, i))
                    witnesses.append({'higher_proxy': high_proxy,
                                      'higher_reference': high_reference})
    outcome = 'REJECT_INVERSION' if inversions else 'PASS_FINITE_NO_INVERSION_UNATTESTED'
    if len(set(truth.values())) <= 1 or len(set(proxy.values())) <= 1:
        if not inversions:
            outcome = 'INCONCLUSIVE_CONSTANT_REWARD'
    return {**base, 'pairs_compared': len(ids) * (len(ids) - 1) // 2,
            'inversion_count': inversions, 'witnesses': witnesses,
            'status': outcome,
            'reason': 'finite pairwise comparison; independently attest reference and scores'}
