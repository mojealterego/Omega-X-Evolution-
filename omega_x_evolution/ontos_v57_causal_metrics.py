"""Finite causal-information and bounded decision-theoretic diagnostics.

A causal channel must represent *interventions*, not observational conditionals.
The caller supplies assumptions: this module cannot identify causal effects
from a passive correlation table. No autonomous policy/action execution.
"""
from __future__ import annotations

import math

from .ontos_information import capacity
from .ontos_metabolism import channel, probability, entropy, mix


def channel_measure(interventional_channel: tuple[tuple[float, ...], ...],
                    *, prior: tuple[float, ...]) -> dict:
    """Compare prior-dependent MI, uniform-intervention EI and channel capacity.

    All quantities are measured in bits. Capacity is a Blahut-Arimoto interval,
    not a certified unconstrained-action empowerment value.
    """
    rows = channel(interventional_channel)
    p = probability(prior)
    if len(p) != len(rows):
        raise ValueError('intervention prior does not match channel')
    prior_mi = entropy(mix(p, rows)) - math.fsum(w*entropy(row) for w, row in zip(p, rows))
    uniform = (1 / len(rows),) * len(rows)
    ei = entropy(mix(uniform, rows)) - math.fsum(w*entropy(row) for w,row in zip(uniform, rows))
    cap = capacity(rows, iterations=1024, tolerance=1e-10)
    return {
        'mutual_information_bits': max(0., prior_mi),
        'effective_information_bits': max(0., ei),
        'empowerment_lower_bits': cap['lower_bits'],
        'empowerment_upper_bits': cap['upper_bits'],
        'capacity_converged': cap['converged'],
        'capacity_iterations': cap['iterations'],
        'interventional_input_required': True,
        'units': 'bits',
    }


def value_of_information(prior: tuple[float, ...],
                         observation_channel: tuple[tuple[float, ...], ...],
                         action_state_utility: tuple[tuple[float, ...], ...]) -> dict:
    """Bayesian expected improvement due to an observation on finite states.

    Utilities are bounded, and the action set is explicitly supplied. A result
    here is only an evaluation of the abstract decision problem, not a plan.
    """
    p = probability(prior)
    g = channel(observation_channel, len(p))
    if (type(action_state_utility) is not tuple
            or not 1 <= len(action_state_utility) <= 64
            or any(type(row) is not tuple or len(row) != len(p)
                   or any(type(value) not in (int, float) or not math.isfinite(value)
                          or abs(value) > 1e6 for value in row)
                   for row in action_state_utility)):
        raise ValueError('finite action-state utility matrix required')
    before = max(math.fsum(weight*u for weight,u in zip(p,action))
                 for action in action_state_utility)
    after = math.fsum(max(math.fsum(p[i]*g[i][j]*action[i]
                                      for i in range(len(p)))
                              for action in action_state_utility)
                      for j in range(len(g[0])))
    delta = after - before
    if delta < -1e-8:
        raise ArithmeticError('negative value of information violates basic bound')
    return {'before': before, 'after': after, 'gain': max(0., delta),
            'utilities_unit': 'caller_supplied', 'causal_identification': False}


def bound_summary(bounds: dict) -> dict:
    """Report identification width without promoting UNKNOWN to zero risk."""
    if type(bounds) is not dict or bounds.get('status') not in ('PASS', 'INFEASIBLE', 'UNKNOWN_SOLVER'):
        raise ValueError('known bounds report required')
    if bounds['status'] != 'PASS':
        return {'status':bounds['status'], 'identified':False,
                'width':None, 'causal_effect':None}
    lo, hi = bounds.get('lower'), bounds.get('upper')
    if (type(lo) is not float or type(hi) is not float
            or not math.isfinite(lo) or not math.isfinite(hi) or lo > hi):
        raise ValueError('bounds invalid')
    width = hi - lo
    return {'status':'PASS','identified':width<=1e-8, 'width':width,
            'causal_effect':(lo+hi)/2 if width<=1e-8 else None}
