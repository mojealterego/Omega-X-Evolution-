"""Finite, independent statistical diagnostics for OFFLINE ONTOS research.

These calculations never decide operational acceptance or replace the trusted
security evaluator. In particular, e-values with a post-update floor must not
inherit a Ville bound from the unfloored likelihood-ratio martingale.
"""
from fractions import Fraction
from itertools import product


def enumerate_null(
    p_null: Fraction,
    p_alternative: Fraction,
    *,
    horizon: int,
    threshold: int,
    floor: Fraction | None = None,
) -> dict:
    """Enumerate all short Bernoulli paths exactly under the declared null.

    Units: probabilities and wealth are exact rationals. The optional floor
    is a *counterexample facility*, not an accepted testing procedure.
    """
    if (
        type(p_null) is not Fraction or not Fraction(0) < p_null < Fraction(1)
        or type(p_alternative) is not Fraction
        or not Fraction(0) < p_alternative < Fraction(1)
        or type(horizon) is not int or not 1 <= horizon <= 12
        or type(threshold) is not int or not 1 <= threshold <= 1_000_000
        or (floor is not None and (type(floor) is not Fraction or floor < 0))
    ):
        raise ValueError('invalid bounded statistical experiment')
    likelihood_success = p_alternative / p_null
    likelihood_failure = (1 - p_alternative) / (1 - p_null)
    mass = expectation = crossing = Fraction(0)
    paths = 0
    for bits in product((0, 1), repeat=horizon):
        paths += 1
        successes = sum(bits)
        path_mass = (p_null ** successes) * ((1 - p_null) ** (horizon - successes))
        wealth = Fraction(1)
        crossed = wealth >= threshold
        for bit in bits:
            wealth *= likelihood_success if bit else likelihood_failure
            if floor is not None:
                wealth = max(floor, wealth)
            crossed |= wealth >= threshold
        mass += path_mass
        expectation += path_mass * wealth
        if crossed:
            crossing += path_mass
    return {
        'paths': paths,
        'probability_mass': mass,
        'terminal_expectation': expectation,
        'crossing_probability': crossing,
        'threshold': Fraction(threshold),
        # Unit expectation at a single horizon is necessary but alone not
        # sufficient to establish the full nonnegative supermartingale claim.
        'valid_e_process_at_horizon': floor is None and expectation == 1,
    }


def ood_confusion(truth: tuple[bool, ...], predicted: tuple[bool | None, ...]) -> dict:
    """Offline classification counts, separating abstention from true negatives.

    `truth` belongs only to a scorer; this function is not called by a policy.
    Undefined conditional rates are None instead of an invented zero success.
    """
    if (
        type(truth) is not tuple or type(predicted) is not tuple
        or not 1 <= len(truth) <= 1024 or len(predicted) != len(truth)
        or any(type(x) is not bool for x in truth)
        or any(x is not None and type(x) is not bool for x in predicted)
    ):
        raise ValueError('invalid bounded OOD classification')
    tp = tn = fp = fn = abstain = 0
    for actual, guess in zip(truth, predicted):
        if guess is None:
            abstain += 1
        elif actual and guess:
            tp += 1
        elif actual and not guess:
            fn += 1
        elif not actual and guess:
            fp += 1
        else:
            tn += 1
    return {
        'tp': tp, 'tn': tn, 'fp': fp, 'fn': fn,
        'abstentions': abstain,
        'coverage': (len(truth) - abstain) / len(truth),
        'recall': tp / (tp + fn) if tp + fn else None,
        'false_positive_rate': fp / (fp + tn) if fp + tn else None,
    }
