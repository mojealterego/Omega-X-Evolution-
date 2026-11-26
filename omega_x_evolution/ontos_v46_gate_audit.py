"""Exact finite-horizon audit of binary multiplicative evidence gates.

Offline diagnostic only. No operational acceptance, memory promotion or
permission grant. Under the declared conditional null P(success | past) <= p,
a fixed nonnegative multiplier pair with win > loss is a supermartingale
iff its expected multiplier at p is <= 1. The crossing probability below is
exact for IID Bernoulli(p), and also bounds the crossing probability for
conditional nulls dominated by p, by monotone coupling. No wealth floor is
included in that calculation. Independence between candidates is not assumed.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

_MAX_HORIZON = 240
_MAX_DENOMINATOR = 10**9
_MAX_FACTOR = 100
_MAX_THRESHOLD = 10**6


def _bounded(x: object, lo: int, hi: int) -> bool:
    return (type(x) is Fraction and lo <= x <= hi
            and x.denominator <= _MAX_DENOMINATOR)


def _validate_factors(p: Fraction, win: Fraction, loss: Fraction) -> None:
    if (not _bounded(p, 0, 1) or not _bounded(win, 1, _MAX_FACTOR)
            or win <= 1 or not _bounded(loss, 0, 1) or loss >= 1):
        raise ValueError('bounded exact probability and success/failure factors required')


@dataclass(frozen=True, slots=True)
class GateAudit:
    maximum_null: Fraction
    expected_multiplier: Fraction
    conditional_supermartingale: bool
    terminal_expectation: Fraction
    crossing_probability: Fraction
    mass: Fraction
    ville_bound: Fraction | None


def audit_gate(p: Fraction, win: Fraction, loss: Fraction, *,
               horizon: int, threshold: Fraction = Fraction(20)) -> GateAudit:
    """Exact first-passage probability without enumerating 2**horizon paths.

    Integer path masses have common denominator p.denominator**t. Surviving
    paths with the same success count at t have identical wealth. Crossed
    paths are absorbed permanently. O(horizon**2) states, O(horizon) live
    storage (excluding bounded-size exact integer arithmetic). The reported
    terminal expectation is for the original unstopped process, not the
    absorbed distribution. The conditional null is a mathematical premise,
    not an empirical claim about correlated observations or selected labels.
    """
    _validate_factors(p, win, loss)
    if (type(horizon) is not int or not 1 <= horizon <= _MAX_HORIZON
            or not _bounded(threshold, 1, _MAX_THRESHOLD) or threshold <= 1):
        raise ValueError('bounded horizon and threshold > 1 required')
    a, b = p.numerator, p.denominator
    wn = [win.numerator**k for k in range(horizon + 1)]
    wd = [win.denominator**k for k in range(horizon + 1)]
    ln = [loss.numerator**k for k in range(horizon + 1)]
    ld = [loss.denominator**k for k in range(horizon + 1)]
    live = {0: 1}
    absorbed = 0
    for t in range(1, horizon + 1):
        absorbed *= b
        following: dict[int, int] = {}
        for successes, mass in live.items():
            for k, weight in ((successes, b-a), (successes+1, a)):
                if not weight:
                    continue
                branch = mass * weight
                failures = t-k
                if (wn[k] * ln[failures] * threshold.denominator
                        >= wd[k] * ld[failures] * threshold.numerator):
                    absorbed += branch
                else:
                    following[k] = following.get(k, 0) + branch
        live = following
    denominator = b**horizon
    total = absorbed + sum(live.values())
    if total != denominator:
        raise ArithmeticError('probability mass conservation failure')
    multiplier = p*win + (1-p)*loss
    valid = multiplier <= 1
    crossing = Fraction(absorbed, denominator)
    bound = 1/threshold if valid else None
    if bound is not None and crossing > bound:
        raise ArithmeticError('exact crossing contradicts Ville inequality')
    return GateAudit((1-loss)/(win-loss), multiplier, valid,
                     multiplier**horizon, crossing, Fraction(total, denominator), bound)


def floored_step_expectation(wealth: Fraction, p: Fraction, win: Fraction,
                             loss: Fraction, *, floor: Fraction) -> Fraction:
    """One-step exact diagnostic for the source's wealth-floor modification."""
    _validate_factors(p, win, loss)
    if not _bounded(wealth, 0, _MAX_THRESHOLD) or not _bounded(floor, 0, _MAX_THRESHOLD):
        raise ValueError('bounded nonnegative wealth and floor required')
    return p*max(floor, wealth*win) + (1-p)*max(floor, wealth*loss)


def family_alpha_bound(alphas: tuple[Fraction, ...]) -> Fraction:
    """Union bound over prespecified per-candidate valid error budgets.

    No independence required. Does not make invalid tests valid or establish
    that an adaptively chosen candidate actually obeys its conditional null.
    """
    if (type(alphas) is not tuple or not 1 <= len(alphas) <= 256
            or any(not _bounded(alpha, 0, 1) for alpha in alphas)):
        raise ValueError('bounded exact alpha budget tuple required')
    return min(Fraction(1), sum(alphas, Fraction(0)))
