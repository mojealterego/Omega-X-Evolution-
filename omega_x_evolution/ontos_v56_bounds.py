"""Binary instrumental-variable bounds by the 16-type Balke-Pearl LP.

Assumptions: exclusion (Z affects Y only through X), independence Z ⟂ U,
consistency, deterministic response functions conditional on U. Both arms
P(X,Y|Z=z) must be present and normalized. Results are *numerical intervals*
for these explicit assumptions, NOT physical safety guarantees.
"""
from __future__ import annotations

from fractions import Fraction
import math

import numpy as np
from scipy.optimize import linprog

from .ontos_v55_scm import response_space

_TYPES = response_space()
_OBJECTIVES = ('ate', 'harm', 'benefit', 'y0', 'y1')


def _validate_table(table: object) -> tuple[tuple[Fraction, ...], ...]:
    if (type(table) is not tuple or len(table) != 2 or any(
            type(row) is not tuple or len(row) != 4 for row in table)):
        raise ValueError('both complete instrument arms required')
    for row in table:
        if (any(type(x) is not Fraction or x < 0 or x > 1
                or x.denominator > 10**9 for x in row)
                or sum(row, Fraction(0)) != 1):
            raise ValueError('conditional joint distribution invalid')
    return table


def _problem(table: tuple[tuple[Fraction, ...], ...], target: str):
    matrix = np.zeros((9, 16), dtype=np.float64)
    matrix[8, :] = 1.
    for j, (x0, x1, y0, y1) in enumerate(_TYPES):
        for z, x in enumerate((x0, x1)):
            y = y1 if x else y0
            matrix[4*z+2*x+y, j] = 1.
    eq = np.array([float(p) for row in table for p in row] + [1.], dtype=np.float64)
    obj = np.empty(16, dtype=np.float64)
    for j, (x0,x1,y0,y1) in enumerate(_TYPES):
        obj[j] = {
            'ate':y1-y0,
            'harm':int(y0 == 1 and y1 == 0),
            'benefit':int(y0 == 0 and y1 == 1),
            'y0':y0,
            'y1':y1,
        }[target]
    return matrix, eq, obj


def iv_bounds(table: tuple[tuple[Fraction, ...], ...], *, target: str = 'harm') -> dict:
    """Identified interval on a finite-response IV model; fail closed on solver errors.

    Uses HiGHS dual simplex and interior point, verifying both primal
    equalities and each objective against the second solver. Exhaustiveness is
    over all 16 deterministic latent types; optimization is numerical (1e-8).
    """
    table = _validate_table(table)
    if type(target) is not str or target not in _OBJECTIVES:
        raise ValueError('unknown causal estimand')
    matrix, eq, objective = _problem(table,target)
    outputs=[]
    max_residual=0.
    for direction in (1.,-1.):
        goal = direction*objective
        runs = [linprog(goal,A_eq=matrix,b_eq=eq,bounds=(0.,1.),method=method,
                        options={'time_limit':2.})
                for method in ('highs-ds','highs-ipm')]
        if all(r.status == 2 for r in runs):
            return {'status':'INFEASIBLE','lower':None,'upper':None,
                    'identified':False,'primal_max_residual':None,
                    'n_response_types':16,'target':target,
                    'assumptions':'randomized Z independent of U; exclusion; consistency'}
        if any(not r.success for r in runs):
            return {'status':'UNKNOWN_SOLVER','lower':None,'upper':None,
                    'identified':False,'primal_max_residual':None,
                    'n_response_types':16,'target':target,
                    'assumptions':'randomized Z independent of U; exclusion; consistency'}
        for r in runs:
            residual = float(np.max(np.abs(matrix @ r.x-eq)))
            max_residual = max(max_residual,residual)
            if (residual > 1e-8 or np.min(r.x) < -1e-8
                    or np.max(r.x) > 1+1e-8):
                return {'status':'UNKNOWN_SOLVER','lower':None,'upper':None,
                        'identified':False,'primal_max_residual':max_residual,
                        'n_response_types':16,'target':target,
                        'assumptions':'randomized Z independent of U; exclusion; consistency'}
        if abs(runs[0].fun-runs[1].fun) > 1e-8:
            return {'status':'UNKNOWN_SOLVER','lower':None,'upper':None,
                    'identified':False,'primal_max_residual':max_residual,
                    'n_response_types':16,'target':target,
                    'assumptions':'randomized Z independent of U; exclusion; consistency'}
        outputs.append(direction*float(runs[0].fun))
    lo,hi=outputs
    cap = 1. if target != 'ate' else 1.
    minimum = -1. if target == 'ate' else 0.
    if lo < minimum-1e-8 or hi > cap+1e-8 or lo>hi+1e-8:
        return {'status':'UNKNOWN_SOLVER','lower':None,'upper':None,
                'identified':False,'primal_max_residual':max_residual,
                'n_response_types':16,'target':target,
                'assumptions':'randomized Z independent of U; exclusion; consistency'}
    return {'status':'PASS', 'lower':max(minimum,lo), 'upper':min(cap,hi),
            'identified':hi-lo<=1e-8,
            'primal_max_residual':max_residual,'n_response_types':16,
            'target':target,'method':'HiGHS dual simplex + interior-point cross-check',
            'assumptions':'randomized Z independent of U; exclusion; consistency',
            'physical_validation':False}
