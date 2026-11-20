"""Zero-example discovery of exact rational-function identities.

Theorems are conditional on BOTH denominators being nonzero. A determining
integer grid certifies a bounded polynomial cross-product identity; independent
coefficient expansion rechecks it before publication. No sampled data alone
can promote a theorem, and an empty domain cannot prove one vacuously.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import product
import hashlib
import json
import math
import random

from .graph_memory import GraphMemory, canonical
from .infinite_discovery import Polynomial, VARIABLES, _normal

MAX_GRID = 4096
MAX_REPORT_BYTES = 2 * 1024 * 1024
DOMAIN = 'Q and R: both denominators nonzero'
SCHEMA = 'omega-rational-discovery-v1'


def _tree(value, *, wire=False):
    """Strict bounded AST snapshot, before constructing any Polynomial."""
    kind = list if wire else tuple
    count = 0

    def walk(t, depth):
        nonlocal count
        count += 1
        if count > 63 or depth > 7 or type(t) is not kind or not t or type(t[0]) is not str:
            raise ValueError('rational polynomial bound or shape')
        op = t[0]
        if op in VARIABLES and len(t) == 1:
            return (op,)
        if op == 'lit' and len(t) == 3 and type(t[1]) is int and type(t[2]) is int:
            if -100 <= t[1] <= 100 and 1 <= t[2] <= 100:
                return (op, t[1], t[2])
        if op in ('add', 'sub', 'mul') and len(t) == 3:
            return (op, walk(t[1], depth+1), walk(t[2], depth+1))
        raise ValueError('rational polynomial grammar')

    return Polynomial(walk(value, 0))


def _poly(p):
    if type(p) is not Polynomial:
        raise ValueError('exact polynomial type required')
    return _tree(p.tree)


@dataclass(frozen=True)
class Quotient:
    numerator: Polynomial
    denominator: Polynomial

    def __post_init__(self):
        _poly(self.numerator)
        _poly(self.denominator)

    @classmethod
    def from_json(cls, value):
        if type(value) is not dict or set(value) != {'numerator', 'denominator'}:
            raise ValueError('rational encoding')
        return cls(_tree(value['numerator'], wire=True), _tree(value['denominator'], wire=True))

    def evaluate(self, coordinates):
        n, d = _parts(self)
        if type(coordinates) is not tuple or len(coordinates) != len(VARIABLES):
            raise ValueError('rational coordinates')
        if any(type(v) not in (int, Fraction) for v in coordinates):
            raise ValueError('exact rational coordinates required')
        if any(max(v.numerator.bit_length(), v.denominator.bit_length()) > 4096 for v in coordinates):
            raise ValueError('coordinate bit bound')
        return n.evaluate(coordinates) / d.evaluate(coordinates)


def _parts(q):
    if type(q) is not Quotient:
        raise ValueError('exact quotient type required')
    return _poly(q.numerator), _poly(q.denominator)


def _wire(n, d):
    return json.loads(canonical({'numerator': n.tree, 'denominator': d.tree}))


def _add_degrees(a, b):
    return tuple(x+y for x, y in zip(a, b))


def _size(degrees):
    return math.prod(d+1 for d in degrees)


def _grid(degrees):
    return product(*(range(d+1) for d in degrees))


def _ratio(x):
    return [x.numerator, x.denominator]


def classify(left: Quotient, right: Quotient) -> dict:
    a, b = _parts(left)
    c, d = _parts(right)
    guard = _add_degrees(b.degrees, d.degrees)
    cross = tuple(max(x,y) for x,y in zip(_add_degrees(a.degrees,d.degrees), _add_degrees(c.degrees,b.degrees)))
    base = {'schema': 'omega-conditional-rational-v1', 'left': _wire(a,b), 'right': _wire(c,d),
            'domain': DOMAIN, 'cross_degrees': list(cross), 'guard_degrees': list(guard)}
    if _size(guard) > MAX_GRID or _size(cross) > MAX_GRID:
        return {**base, 'status': 'unknown', 'reason': 'determining grid cap'}
    # A nonzero polynomial of coordinate-wise degrees d cannot vanish on
    # the grid of d+1 distinct values per variable. Thus a failed guard search
    # establishes that the common nonzero domain is empty (Q and R).
    witness = next((p for p in _grid(guard) if b.evaluate(p) and d.evaluate(p)), None)
    if witness is None:
        return {**base, 'status': 'invalid-domain', 'reason': 'identically zero denominator'}
    base['domain_witness'] = list(witness)
    h = hashlib.sha256()
    nonzero = False

    def counter(p, bv, dv, av, cv):
        return {**base, 'status': 'refuted', 'counterexample': list(p),
                'values': [_ratio(av/bv), _ratio(cv/dv)]}

    for p in _grid(cross):
        av, bv, cv, dv = (poly.evaluate(p) for poly in (a,b,c,d))
        delta = av*dv-cv*bv
        if delta:
            nonzero = True
            if bv and dv:
                return counter(p,bv,dv,av,cv)
        h.update(canonical([p,_ratio(delta)]).encode())
    if not nonzero:
        return {**base, 'status': 'proved', 'grid_points': _size(cross), 'grid_sha256': h.hexdigest()}
    # Difference nonzero at a pole is not a valid counterexample. A grid
    # for (a*d-c*b)*b*d is sufficient to locate a non-pole witness.
    combined = _add_degrees(cross,guard)
    if _size(combined) > MAX_GRID:
        return {**base,'status':'unknown','reason':'counterexample grid cap'}
    for p in _grid(combined):
        bv,dv = b.evaluate(p),d.evaluate(p)
        if bv and dv:
            av,cv = a.evaluate(p),c.evaluate(p)
            if av*dv != cv*bv:
                return counter(p,bv,dv,av,cv)
    raise RuntimeError('inconsistent determining-grid invariant')


def _multiply(a, b):
    """Exact sparse formal multiplication, independent of point evaluation."""
    out = {}
    for i,x in a.items():
        for j,y in b.items():
            k = _add_degrees(i,j)
            out[k] = out.get(k,Fraction(0))+x*y
    return {k:v for k,v in out.items() if v}


def _checked_report(report):
    if type(report) is not dict:
        raise ValueError('report type')
    raw = canonical(report)
    if len(raw.encode()) > MAX_REPORT_BYTES:
        raise ValueError('report size')
    return json.loads(raw)


def verify(left: Quotient, right: Quotient, report: dict) -> bool:
    """Exact replay plus independent coefficient proof or non-pole witness."""
    try:
        report = _checked_report(report)
        if report['status'] not in ('proved','refuted'):
            return False
        a,b = _parts(left)
        c,d = _parts(right)
        if canonical(report) != canonical(classify(Quotient(a,b),Quotient(c,d))):
            return False
        witness = tuple(report['domain_witness'])
        if not b.evaluate(witness) or not d.evaluate(witness):
            return False
        if report['status'] == 'proved':
            bn,dn = _normal(b.tree),_normal(d.tree)
            return bool(bn) and bool(dn) and _multiply(_normal(a.tree),dn)==_multiply(_normal(c.tree),bn)
        p = tuple(report['counterexample'])
        return a.evaluate(p)/b.evaluate(p) != c.evaluate(p)/d.evaluate(p)
    except (ValueError, TypeError, KeyError, IndexError, ArithmeticError, AttributeError, RecursionError):
        return False


def discover(*, seed: int = 42, budget: int = 64) -> dict:
    """Generate quotient conjectures without examples or target identities."""
    if type(seed) is not int or not 0 <= seed < 2**32 or type(budget) is not int or not 16 <= budget <= 128:
        raise ValueError('rational discovery bounds')
    rng = random.Random(seed)
    atoms = [(v,) for v in VARIABLES] + [('lit',1,1),('lit',2,1)]
    variables = atoms[:3]
    trees = atoms + [(op,a,b) for op in ('add','mul') for i,a in enumerate(variables) for b in variables[i:]]
    polynomials = tuple(Polynomial(t) for t in trees)
    probes = ((1,2,3),(2,3,5),(3,5,7),(5,7,11))
    values = {p:tuple(p.evaluate(x) for x in probes) for p in polynomials}
    groups = {}
    pool = []
    # All members of this discovery grammar are positive at the probes.
    # Signatures propose conjectures only: classification determines truth.
    for a,b in product(polynomials,repeat=2):
        sig = tuple(x/y for x,y in zip(values[a],values[b]))
        if len(set(sig)) < 2:
            continue  # seek nonconstant laws rather than x/x=1 tautologies
        q = Quotient(a,b)
        groups.setdefault(sig,[]).append(q)
        pool.append(q)
    collisions = [(rows[0],q) for rows in groups.values() for q in rows[1:]]
    rng.shuffle(collisions)
    pairs = collisions[:budget*3//4]
    seen = {frozenset(p) for p in pairs}
    for _ in range(budget*8):
        if len(pairs) >= budget:
            break
        a,b = rng.sample(pool,2)
        key = frozenset((a,b))
        if key not in seen:
            seen.add(key); pairs.append((a,b))
    if len(pairs) != budget:
        raise RuntimeError('rational proposal budget not reached')
    out = {'schema':SCHEMA,'seed':seed,'budget':budget,'grammar_quotients':len(pool),
           'proposals':len(pairs),'proved':[],'refuted':[],'unknown':[],'invalid-domain':[]}
    for a,b in pairs:
        row = classify(a,b)
        if row['status'] in ('proved','refuted') and not verify(a,b,row):
            raise RuntimeError('independent rational proof failure')
        out[row['status']].append(row)
    return out


def verify_discovery(report: dict) -> bool:
    try:
        report = _checked_report(report)
        if report.get('schema') != SCHEMA or type(report.get('budget')) is not int or not 16 <= report['budget'] <= 128:
            return False
        buckets=('proved','refuted','unknown','invalid-domain')
        if any(type(report.get(k)) is not list or len(report[k])>report['budget'] for k in buckets):
            return False
        if sum(len(report[k]) for k in buckets)!=report['budget']:
            return False
        for row in report['proved']:
            if not verify(Quotient.from_json(row['left']),Quotient.from_json(row['right']),row):
                return False
        return canonical(report)==canonical(discover(seed=report['seed'],budget=report['budget']))
    except (ValueError,TypeError,KeyError,IndexError,ArithmeticError,AttributeError,RecursionError):
        return False


def publish(memory: GraphMemory, report: dict) -> list[str]:
    """Verify before an atomic, idempotent, tenant-bound graph publication."""
    report = _checked_report(report)
    if type(memory) is not GraphMemory or not verify_discovery(report):
        raise ValueError('unverified rational discovery report')
    digest = hashlib.sha256(canonical(report).encode()).hexdigest()
    with memory._db(write=True) as db:
        source = memory._add(db,'experiment','conditional rational-function discovery',
                             {'report_sha256':digest,'seed':report['seed'],'budget':report['budget']})
        ids = []
        for row in report['proved']:
            node = memory._add(db,'evidence','proved rational identity on common nonzero domain',row)
            memory._link(db,source,'produced',node)
            ids.append(node)
    return sorted(set(ids))
