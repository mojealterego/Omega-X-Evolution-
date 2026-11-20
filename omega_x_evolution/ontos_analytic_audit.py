"""Fixed synthetic numerical audits only; no model loading or runtime adaptation."""
from fractions import Fraction
from itertools import product
import numpy as np


def analytic_audit(seed: int) -> dict:
    """Compare batch ridge and recursive least squares on a known affine fixture."""
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError('seed')
    rng = np.random.default_rng(seed)
    x = rng.uniform(-1., 1., (96, 2))
    exact = np.array([[.7, -.1], [.1, .6], [.2, -.3]])
    design = np.column_stack((x, np.ones(96)))
    y = design @ exact
    a, b = design[:64], y[:64]
    ridge = 1e-6
    batch = np.linalg.solve(a.T @ a + ridge*np.eye(3), a.T @ b)
    cov = np.eye(3)/ridge
    w = np.zeros((3, 2))
    for row, target in zip(a, b):
        v = cov @ row
        den = 1. + row @ v
        gain = v / den
        w += np.outer(gain, target-row @ w)
        cov -= np.outer(v, v)/den
        cov = (cov+cov.T)/2
    # Fixed linear operator, not a pretrained encoder or semantic SAE.
    fixture = np.array([[3., 1.], [1., 2.], [0., 1.]])
    u, s, vt = np.linalg.svd(fixture, full_matrices=False)
    return {'seed': seed, 'train_rows': 64, 'holdout_rows': 32,
            'gradient_steps': 0,
            'svd_reconstruction_error': float(np.linalg.norm((u*s)@vt-fixture)),
            'rls_batch_difference': float(np.max(np.abs(w-batch))),
            'holdout_mse': float(np.mean((design[64:]@batch-y[64:])**2)),
            'persistence_mse': float(np.mean((x[64:]-y[64:])**2))}


def stopping_audit() -> dict:
    """Exact null enumeration for a fixed likelihood ratio and a wealth-floor counterexample."""
    p = Fraction(1, 4)
    bound = 20
    mass = mean = floored_mean = crossing = Fraction(0)
    for path in product((0, 1), repeat=12):
        prob = p**sum(path)*(1-p)**(12-sum(path))
        wealth = floored = Fraction(1)
        hit = False
        for outcome in path:
            factor = Fraction(2) if outcome else Fraction(2, 3)
            wealth *= factor
            floored = max(Fraction(1), floored*factor)
            hit |= wealth >= bound
        mass += prob
        mean += prob*wealth
        floored_mean += prob*floored
        if hit:
            crossing += prob
    return {'paths': 4096, 'null_mass': float(mass),
            'terminal_mean': float(mean), 'floor_terminal_mean': float(floored_mean),
            'crossing_probability': float(crossing), 'ville_bound': 1/bound}
