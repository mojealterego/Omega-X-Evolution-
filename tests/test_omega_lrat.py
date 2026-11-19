"""OMEGA-LRAT: actual SAT certificate production and independent replay."""
import hashlib
import os
import shutil
import pytest
from omega_x_evolution.polyglot import Program
from omega_x_evolution import lrat

X,Y,Z,O=('x',),('y',),('lit',0),('lit',1)
POSITIVE=[(('add',X,Y),('add',Y,X)),(('sub',X,X),Z),
          (('mul',X,O),X),(('xor',X,X),Z),
          (('and',X,X),X),(('or',X,Z),X)]
NEGATIVE=[(('add',X,O),X),(('sub',X,O),X),
          (('mul',X,Z),X),(('xor',X,Y),X),
          (('and',X,Y),X),(('or',X,Y),X)]

def native():
    if os.environ.get('OMEGA_LRAT_NATIVE')!='1':
        pytest.skip('native LRAT runtime not requested')
    assert shutil.which('cadical') and shutil.which('lrat_isa')

@pytest.mark.parametrize('left,right',POSITIVE)
def test_lrat_native_proves_all_operators(left,right):
    native();a,b=Program(left),Program(right)
    report=lrat.prove(a,b)
    assert report['proved'] and report['status']=='checked',report
    assert lrat.verify(a,b,report)

@pytest.mark.parametrize('left,right',NEGATIVE)
def test_lrat_false_equivalence(left,right):
    native();a,b=Program(left),Program(right)
    r=lrat.prove(a,b)
    assert r['status']=='sat' and not r['proved']
    assert not lrat.verify(a,b,r)

def test_lrat_certificate_tampering_even_with_new_hash():
    import base64
    native();a,b=Program(('add',X,Y)),Program(('add',Y,X))
    r=lrat.prove(a,b);assert r['proved']
    raw=b'not an LRAT proof';r['proof']=base64.b64encode(raw).decode()
    r['proof_sha256']=hashlib.sha256(raw).hexdigest()
    assert not lrat.verify(a,b,r)

def test_lrat_replay_without_solver_and_source_binding(monkeypatch):
    native();a,b=Program(('xor',X,X)),Program(Z)
    r=lrat.prove(a,b);assert r['proved']
    original=shutil.which
    monkeypatch.setattr(lrat.shutil,'which',lambda name: None if name=='cadical' else original(name))
    assert lrat.verify(a,b,r)
    assert not lrat.verify(a,Program(O),r)
    assert lrat.prove(a,b)['status']=='unavailable'

def test_lrat_cnf_reproducible_and_reject_invalid_ir():
    a,b=Program(('mul',X,Y)),Program(('add',X,Y))
    raw=lrat.cnf(a,b);assert raw==lrat.cnf(a,b)
    header,*clauses=raw.decode().splitlines();p,fmt,n,m=header.split()
    assert (p,fmt)==('p','cnf') and int(m)==len(clauses)
    assert all(row.endswith(' 0') for row in clauses)
    object.__setattr__(a,'tree',('lit','injection'))
    with pytest.raises(ValueError):lrat.cnf(a,b)

def test_lrat_required_gate_and_replay():
    native();from omega_x_evolution import higher_order
    a,b=Program(('sub',X,X)),Program(Z)
    r=higher_order.prove(a,b,require_lrat=True)
    assert r['proved'] and r['lrat']['proved'] and higher_order.verify(r)
    r['lrat']['proof_sha256']='0'*64
    assert not higher_order.verify(r)


def test_gate09_higher_order_policy_replay():
    if os.environ.get('OMEGA_LRAT_NATIVE')!='1':pytest.skip('native checker not requested')
    from omega_x_evolution import higher_order
    a,b=Program(('add',('and',X,Y),('xor',X,Y))),Program(('or',X,Y)); report=higher_order.prove(a,b,require_lrat=True)
    assert report['proved'] and report['lrat']['proved']
    assert higher_order.verify(report,require_lrat=True)
    ordinary=higher_order.prove(a,b)
    assert not higher_order.verify(ordinary,require_lrat=True)
    report['lrat']['proof_sha256']='0'*64
    assert not higher_order.verify(report,require_lrat=True)


def test_gate09_missing_checker_rejects_policy(monkeypatch):
    from omega_x_evolution import higher_order
    monkeypatch.setattr(shutil,'which',lambda _:None)
    a=Program(X)
    assert not higher_order.prove(a,a,require_lrat=True)['proved']


def test_gate09_isabelle_source_revalidates_ir():
    from omega_x_evolution import higher_order
    a=Program(X); object.__setattr__(a,'tree',('lit','0'))
    with pytest.raises(ValueError):higher_order.isabelle_source(a,Program(X))


@pytest.mark.parametrize('op', ['add','sub','mul','xor','and','or'])
def test_gate09_circuit_and_cnf_semantics(op):
    import itertools
    from omega_x_evolution.polyglot import evaluate
    p=Program((op,X,Y)); c,output=lrat.compile_circuit(p,width=4)
    for x,y in itertools.product(range(16),repeat=2):
        expected=evaluate(p,x,y)&15
        assert c.evaluate(output,x,y)==expected
        # Independently evaluate Tseitin clauses under the gate assignment.
        assignment={1:True,**{b:bool(x>>i&1) for i,b in enumerate(c.x)},
                    **{b:bool(y>>i&1) for i,b in enumerate(c.y)}}
        def val(v):return assignment[abs(v)] != (v<0)
        for gate,a,b,z in c.gates:
            assignment[z]=(val(a) and val(b)) if gate=='and' else (val(a)!=val(b))
        assert all(any(val(v) for v in clause) for clause in c.clauses)
        assert sum(int(val(v))<<i for i,v in enumerate(output))==expected


@pytest.mark.parametrize('op', ['add','sub','mul','xor','and','or'])
def test_gate09_native_width_boundary(op):
    import random
    from omega_x_evolution.polyglot import evaluate
    p=Program((op,('add',X,Y),('xor',X,Y)));c,output=lrat.compile_circuit(p)
    rng=random.Random(42)
    points=[(0,0),(65535,65535),(32768,32768),(1,65535)] + [(rng.randrange(65536),rng.randrange(65536)) for _ in range(64)]
    assert all(c.evaluate(output,x,y)==evaluate(p,x,y) for x,y in points)


def test_cnf_equal_but_ir_binding_different():
    native();a,b=Program(('xor',X,X)),Program(Z);c=Program(('sub',X,X))
    assert lrat.cnf(a,b)==lrat.cnf(c,b)
    report=lrat.prove(a,b)
    assert not lrat.verify(c,b,report)


def test_optimizer_requires_real_certificate():
    native();from omega_x_evolution import higher_order
    p=Program(('or',X,Z))
    report=higher_order.optimize(p,require_lrat=True)
    assert report['promoted'] and higher_order.verify(report['proof'],require_lrat=True)
