"""HYPERION-X finite split/weighted conformal calibration and non-authorizing routing.

Weighted threshold uses the calibration atoms plus a test atom at +infinity:
  q_(1-alpha)(sum_i w_i delta_score_i + w_test delta_infinity).
Weights are assumed covariate density ratios; *their origin is not attested*.
Finite-sample coverage requires exchangeability or known-ratio covariate shift and
an unchanged Y|X mechanism. Estimated ratios do not imply exact coverage.

No arbitrary code execution, model promotion, hardware telemetry, or secrets.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
import hashlib
import hmac
import json
import math
import re

_SCHEMA = 'omega-hyperion-conformal-v1'
_SOURCE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z', re.ASCII)
_MAX_N = 4096
_MAX_VALUE = 1e12
_MAX_WEIGHT = 1e6


def _number(x: object, lo: float, hi: float) -> bool:
    return type(x) in (float, int) and math.isfinite(x) and lo <= x <= hi


def _decimal(x: float | int) -> Decimal:
    return Decimal(str(x))


def _digest(pairs: tuple[tuple[float | int, float | int], ...],
            alpha: float, test_weight: float | int, ratio_source: str, source_id: str) -> str:
    body = {'schema':_SCHEMA, 'pairs':pairs, 'alpha':alpha,
            'test_weight':test_weight, 'ratio_source':ratio_source,
            'source_id':source_id}
    raw = json.dumps(body, sort_keys=True, allow_nan=False, ensure_ascii=True,
                     separators=(',', ':')).encode('ascii')
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class Calibration:
    """Immutable numeric evidence; not independently authenticated or privileged."""
    scores: tuple[float | int, ...]
    weights: tuple[float | int, ...]
    alpha: float
    test_weight: float | int
    ratio_source: str
    source_id: str
    threshold: float
    effective_n: float
    status: str
    claim: str
    digest: str
    assumptions_attested: bool = False
    release_authorized: bool = False


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    """Compute routing only. No candidate approval or resource provisioning."""
    base_steps: int
    verify_steps: int
    max_width: float

    def __post_init__(self) -> None:
        if (type(self.base_steps) is not int or type(self.verify_steps) is not int
                or not 1 <= self.base_steps <= self.verify_steps <= 1_000_000
                or not _number(self.max_width, 0, _MAX_VALUE)):
            raise ValueError('invalid bounded compute-routing policy')


@dataclass(frozen=True, slots=True)
class RouteDecision:
    calibration_digest: str
    policy: BudgetPolicy
    action: str
    steps: int
    release_authorized: bool = False
    coverage_certified: bool = False


def calibrate(scores: tuple[float | int, ...], *, alpha: float,
              weights: tuple[float | int, ...] | None = None,
              test_weight: float | int = 1.0, ratio_source: str = 'unweighted',
              source_id: str = 'unweighted') -> Calibration:
    """Return conservative weighted conformal threshold; may be +infinity.

    Standard split conformal is recovered with n unit calibration weights plus
    a unit test atom at infinity. For shifted covariates, the caller is
    responsible for proving/estimating w(x)=p_test(x)/p_cal(x).

    Complexity O(n log n), memory O(n), n<=4096; external coverage assumptions
    are NOT certified by this routine.
    """
    if (type(scores) is not tuple or not 1 <= len(scores) <= _MAX_N
            or any(not _number(x, 0, _MAX_VALUE) for x in scores)):
        raise ValueError('bounded finite nonnegative tuple of scores required')
    if not _number(alpha, .001, .5):
        raise ValueError('alpha outside supported range')
    if not _number(test_weight, 1e-12, _MAX_WEIGHT):
        raise ValueError('test density-ratio weight is invalid')
    if ratio_source not in ('unweighted', 'known_ratio', 'estimated_ratio'):
        raise ValueError('unsupported density-ratio source')
    if type(source_id) is not str or _SOURCE.fullmatch(source_id) is None:
        raise ValueError('invalid source_id')
    if ratio_source == 'unweighted':
        if weights is not None or test_weight != 1.0 or source_id != 'unweighted':
            raise ValueError('unweighted split-conformal requires unit weights')
        weights = (1.0,) * len(scores)
    elif (source_id == 'unweighted' or type(weights) is not tuple or len(weights) != len(scores)
          or any(not _number(w, 0, _MAX_WEIGHT) for w in weights)
          or not any(w > 0 for w in weights)):
        raise ValueError('invalid calibration density-ratio weights')
    pairs = tuple(sorted(zip(scores, weights)))
    with localcontext() as ctx:
        ctx.prec = 60
        total = sum((_decimal(w) for _, w in pairs), Decimal(0))
        threshold_mass = (Decimal(1) - _decimal(alpha)) * (total + _decimal(test_weight))
        mass = Decimal(0)
        bound = math.inf
        for score, w in pairs:
            mass += _decimal(w)
            if mass >= threshold_mass:
                bound = float(score)
                break
        sqsum = sum((_decimal(w) ** 2 for _, w in pairs), Decimal(0))
        effective_n = float(total * total / sqsum)  # positive by validation
    claim = {'unweighted':'CONDITIONAL_EXCHANGEABILITY',
             'known_ratio':'CONDITIONAL_KNOWN_RATIO',
             'estimated_ratio':'ESTIMATED_WEIGHTS_NO_FINITE_SAMPLE_CLAIM'}[ratio_source]
    status = 'UNBOUNDED' if math.isinf(bound) else 'FINITE_THRESHOLD'
    return Calibration(tuple(s for s, _ in pairs), tuple(w for _, w in pairs),
                       float(alpha), test_weight, ratio_source, source_id,
                       bound, effective_n, status, claim,
                       _digest(pairs, float(alpha), test_weight, ratio_source, source_id))


def _revalidate(evidence: Calibration) -> None:
    if type(evidence) is not Calibration:
        raise ValueError('typed calibration required')
    if evidence.assumptions_attested is not False or evidence.release_authorized is not False:
        raise ValueError('caller cannot self-attest validity or promotion')
    fresh = calibrate(evidence.scores, alpha=evidence.alpha,
                      weights=None if evidence.ratio_source == 'unweighted' else evidence.weights,
                      test_weight=evidence.test_weight, ratio_source=evidence.ratio_source,
                      source_id=evidence.source_id)
    if fresh != evidence:
        raise ValueError('calibration report was modified after construction')


def route_budget(evidence: Calibration, policy: BudgetPolicy, *,
                 expected_digest: str) -> RouteDecision:
    """Opt-in compute hint only; SHA pin must come from a trusted outer layer."""
    _revalidate(evidence)
    if type(policy) is not BudgetPolicy:
        raise ValueError('typed routing policy required')
    policy.__post_init__()
    if (type(expected_digest) is not str or not re.fullmatch('[0-9a-f]{64}',expected_digest)
            or not hmac.compare_digest(evidence.digest, expected_digest)):
        raise ValueError('trusted external calibration digest mismatch')
    if evidence.status == 'UNBOUNDED':
        action, steps = 'ABSTAIN_INSUFFICIENT_CALIBRATION', 0
    elif (evidence.ratio_source == 'estimated_ratio'
          or evidence.threshold > policy.max_width):
        action, steps = 'EXTENDED_VERIFICATION', policy.verify_steps
    else:
        action, steps = 'BASELINE_COMPUTE', policy.base_steps
    return RouteDecision(evidence.digest, policy, action, steps)


def export_jsonl(evidence: Calibration, decision: RouteDecision) -> str:
    """One fixed-schema JSONL event; excludes the calibration scores and weights."""
    _revalidate(evidence)
    if type(decision) is not RouteDecision:
        raise ValueError('typed routing decision required')
    expected = route_budget(evidence, decision.policy, expected_digest=evidence.digest)
    if expected != decision:
        raise ValueError('routing decision does not match calibrated evidence')
    return json.dumps({
        'schema':_SCHEMA,
        'calibration_sha256':evidence.digest,
        'ratio_source':evidence.ratio_source,
        'alpha':evidence.alpha,
        'sample_count':len(evidence.scores),
        'effective_sample_size':evidence.effective_n,
        'threshold':None if math.isinf(evidence.threshold) else evidence.threshold,
        'status':evidence.status,
        'claim':evidence.claim,
        'assumptions_attested':False,
        'action':decision.action,
        'steps':decision.steps,
        'release_authorized':False,
        'coverage_certified':False,
    },sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n'
