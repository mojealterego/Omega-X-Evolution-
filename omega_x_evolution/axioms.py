"""Bounded zero-example conjecture synthesis in pure modular arithmetic.
Only independently checked identities enter the theorem register. Finite
algebra models are enumerated, not asserted as new laws of nature.
"""
from __future__ import annotations
import argparse
from itertools import product
import json
import random
from .polyglot import Program, evaluate, ATOMS, OPS
from .proof_kernel import certify, verify_certificate
from .bitproof import _program
from .graph_memory import canonical


def _points(seed):
    rng = random.Random(seed)
    return tuple(product((0, 1, 2, 32768, 65535), repeat=2)) + tuple(
        (rng.randrange(65536), rng.randrange(65536)) for _ in range(32))


def classify(left: Program, right: Program, *, seed: int = 42, smt: bool = False) -> dict:
    if not isinstance(left, Program) or not isinstance(right, Program) or type(seed) is not int or not 0 <= seed < 2**32 or type(smt) is not bool:
        raise ValueError('conjecture contract')
    result = {'left': json.loads(json.dumps(left.tree)), 'right': json.loads(json.dumps(right.tree))}
    for x, y in _points(seed):
        a, b = evaluate(left, x, y), evaluate(right, x, y)
        if a != b:
            return {**result, 'status': 'refuted', 'counterexample': [x, y, a, b]}
    proof = certify(left, right)
    if verify_certificate(left, right, proof):
        return {**result, 'status': 'proved', 'proof': proof}
    if smt:
        from .bitproof import prove
        try:
            evidence = prove(left, right)
        except (OSError, RuntimeError, __import__('subprocess').SubprocessError):
            return {**result, 'status': 'unknown', 'reason': 'solver unavailable or failed'}
        if evidence['proved']:
            return {**result, 'status': 'smt-proved', 'solver': evidence}
        return {**result, 'status': 'unknown', 'reason': 'no checked counterexample', 'solver': evidence}
    return {**result, 'status': 'unknown', 'reason': proof['reason']}


def discover(*, seed: int = 42, budget: int = 256) -> dict:
    if type(seed) is not int or not 0 <= seed < 2**32 or type(budget) is not int or not 16 <= budget <= 1024:
        raise ValueError('conjecture budget')
    rng = random.Random(seed)
    pool = list(ATOMS) + [(op, a, b) for op, a, b in product(OPS, ATOMS, ATOMS)]
    for _ in range(budget):
        pool.append((rng.choice(tuple(OPS)), rng.choice(pool[:155]), rng.choice(pool[:155])))
    programs = [Program(t) for t in dict.fromkeys(pool)]
    groups = {}
    # Small discovery signature is deliberately not a proof; independent
    # adversarial points and the proof kernel qualify each proposed identity.
    for p in programs:
        key = tuple(evaluate(p, x, y) for x, y in ((0,0),(0,1),(1,0),(1,1)))
        groups.setdefault(key, []).append(p)
    candidates = []
    for rows in groups.values():
        rows.sort(key=lambda p: (p.size, repr(p.tree)))
        candidates.extend((rows[0], p) for p in rows[1:])
    rng.shuffle(candidates)
    # Include general grammar pairs, not just collisions, to exercise refutation.
    pairs = candidates[:3*budget//4]
    used = {frozenset((a,b)) for a,b in pairs}
    for _ in range(4*budget):
        if len(pairs) >= budget:
            break
        a,b = rng.sample(programs,2); key=frozenset((a,b))
        if key not in used:
            used.add(key); pairs.append((a,b))
    output = {'schema':'omega-axiom-discovery-v1','seed':seed,'budget':budget,'grammar_programs':len(programs),'proposals':len(pairs),'proved':[],'refuted':[],'unknown':[]}
    for a,b in pairs:
        r=classify(a,b,seed=seed)
        output[r['status']].append(r)
    return output


def verify(report: dict) -> bool:
    """Validate all claims and deterministic search coverage; no theorem injection."""
    try:
        if type(report) is not dict or report.get('schema')!='omega-axiom-discovery-v1' or len(canonical(report).encode())>4*1024*1024 or type(report.get('budget')) is not int or not 16<=report['budget']<=1024 or any(type(report.get(k)) is not list or len(report[k])>report['budget'] for k in ('proved','refuted','unknown')):
            return False
        for r in report['proved']:
            if not verify_certificate(_program(r['left']),_program(r['right']),r['proof']):
                return False
        for r in report['refuted']:
            x,y,a,b=r['counterexample']
            if a==b or evaluate(_program(r['left']),x,y)!=a or evaluate(_program(r['right']),x,y)!=b:
                return False
        return canonical(report)==canonical(discover(seed=report['seed'],budget=report['budget']))
    except (ValueError, TypeError, KeyError, IndexError, ArithmeticError):
        return False


def structures(order: int=2, *, budget: int=19683) -> dict:
    """Enumerate operation tables and mechanically classify finite structures."""
    if type(order) is not int or order not in (2,3) or type(budget) is not int or not 1<=budget<=19683:
        raise ValueError('finite algebra budget')
    from itertools import islice
    models=[]; examined=0; group_count=0; associative_count=0
    for table in islice(product(range(order),repeat=order*order),budget):
        examined+=1
        def op(x,y):return table[x*order+y]
        counter=next(((a,b,c) for a,b,c in product(range(order),repeat=3) if op(op(a,b),c)!=op(a,op(b,c))),None)
        associative=counter is None
        identity=next((e for e in range(order) if all(op(e,x)==op(x,e)==x for x in range(order))),None)
        commutative=all(op(a,b)==op(b,a) for a,b in product(range(order),repeat=2))
        group=associative and identity is not None and all(any(op(a,b)==op(b,a)==identity for b in range(order)) for a in range(order))
        group_count+=group; associative_count+=associative
        # Retain only associative models and a bounded negative witness set.
        if associative or len(models)<8:
            models.append({'table':list(table),'associative':associative,'counterexample':list(counter) if counter is not None else None,'identity':identity,'commutative':commutative,'group':group})
    return {'order':order,'examined':examined,'exhaustive':examined==order**(order*order),'groups':group_count,'associative':associative_count,'models':models}


def publish(memory,report):
    from .graph_memory import GraphMemory
    if not isinstance(memory,GraphMemory) or not verify(report):raise ValueError('unverified discovery report')
    source=memory.add('experiment','bounded modular conjecture discovery',{'seed':report['seed'],'budget':report['budget']})
    ids=[]
    for row in report['proved']:
        node=memory.add('evidence','proved modular identity '+repr(row['left'])+' = '+repr(row['right']),row)
        memory.link(source,'produced',node);ids.append(node)
    return sorted(set(ids))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seed',type=int,default=42);p.add_argument('--budget',type=int);mode=p.add_mutually_exclusive_group();mode.add_argument('--structures',type=int,choices=(2,3));mode.add_argument('--rational',action='store_true',help='discover conditional rational-function identities');a=p.parse_args()
    if a.rational:
        from .rational_axioms import discover as discover_rational
        r=discover_rational(seed=a.seed,budget=64 if a.budget is None else a.budget)
    else:
        budget=256 if a.budget is None else a.budget
        r=structures(a.structures,budget=budget) if a.structures else discover(seed=a.seed,budget=budget)
    print(json.dumps(r,indent=2,allow_nan=False))

if __name__=='__main__':main()
