"""Bounded posterior update with a guaranteed *post-normalization* floor.

A numerical research filter, not an operational Bayesian controller.
Observation probabilities come from an external experiment; the filter has no
access to the environment's true hidden regime or privileged evaluator data.
"""
from __future__ import annotations
from dataclasses import dataclass
import math


def _real(x: object, a: float, b: float) -> bool:
    return type(x) in (int, float) and math.isfinite(x) and a <= x <= b


@dataclass(frozen=True, slots=True)
class BeliefResult:
    posterior: tuple[float, ...]
    abstain: bool
    log_evidence: float | None
    surprise_bits: float | None
    effective_classes: float


class BeliefFilter:
    """Mix in a uniform prior, Bayes-update, then apply a finite floor.

    The floor is implemented as an affine regularization of the *normalized*
    posterior, so it is not falsely interpreted as an exact Bayes posterior.
    """
    __slots__ = ('prior_mix','floor')

    def __init__(self, *, prior_mix: float = .06, floor: float = 1e-4) -> None:
        if not _real(prior_mix, 0, 1) or not _real(floor, 0, .5):
            raise ValueError('belief configuration bounds')
        self.prior_mix = float(prior_mix)
        self.floor = float(floor)

    def update(self, prior: tuple[float, ...], likelihood: tuple[float, ...]) -> BeliefResult:
        # Instance slots are not an authorization or integrity boundary.
        if not _real(self.prior_mix, 0, 1) or not _real(self.floor, 0, .5):
            raise ValueError('corrupted belief configuration')
        if (type(prior) is not tuple or type(likelihood) is not tuple
                or not 2 <= len(prior) <= 64 or len(prior) != len(likelihood)
                or any(not _real(x,0,1) for x in prior)
                or any(not _real(x,0,1) for x in likelihood)
                or not abs(math.fsum(prior) - 1.) <= 1e-12):
            raise ValueError('belief distribution contract')
        n = len(prior)
        if self.floor*n >= 1.:
            raise ValueError('post-normalization floor is impossible')
        total = math.fsum(prior)
        normalized_prior = tuple(p/total for p in prior)
        mixed = tuple((1-self.prior_mix)*p + self.prior_mix/n for p in normalized_prior)
        peak = max(likelihood)
        if peak == 0.:
            normalized, abstain, log_evidence = mixed, True, None
        else:
            scaled = tuple(p*(l/peak) for p,l in zip(mixed,likelihood))
            denominator = math.fsum(scaled)
            if denominator == 0.:
                # No prior support for any possible observation: cannot update.
                normalized, abstain, log_evidence = mixed, True, None
            else:
                normalized = tuple(x/denominator for x in scaled)
                log_evidence = math.log(peak) + math.log(denominator)
                abstain = False
        multiplier = 1 - n*self.floor
        posterior = [self.floor + multiplier*p for p in normalized]
        # Correct finite accumulation drift by adjusting only the largest mass;
        # lower bounds of the other classes remain untouched.
        correction = 1 - math.fsum(posterior)
        j = max(range(n),key=posterior.__getitem__)
        posterior[j] += correction
        if any(not math.isfinite(p) or p < self.floor-1e-15 for p in posterior):
            raise ArithmeticError('posterior numerical budget')
        frozen = tuple(posterior)
        entropy = -math.fsum(p*math.log(p) for p in frozen if p > 0)
        effective_classes = math.exp(entropy)
        return BeliefResult(frozen, abstain, log_evidence,
                            None if log_evidence is None else -log_evidence/math.log(2),
                            effective_classes)
