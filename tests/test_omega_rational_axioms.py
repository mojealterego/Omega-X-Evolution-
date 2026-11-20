"""v33: exact conditional identities on a common rational-function domain."""
import copy
from fractions import Fraction
import pytest
from omega_x_evolution.graph_memory import GraphMemory
from omega_x_evolution.infinite_discovery import Polynomial

X,Y,Z,ONE=('x',),('y',),('z',),('lit',1,1)

def quotient(n,d):
    from omega_x_evolution.rational_axioms import Quotient
    return Quotient(Polynomial(n),Polynomial(d))

def test_v33_cancellation_has_explicit_domain():
    from omega_x_evolution.rational_axioms import classify, verify
    a=quotient(('mul',X,Y),X);b=quotient(Y,ONE)
    proof=classify(a,b)
    assert proof['status']=='proved' and verify(a,b,proof)
    assert proof['domain']=='Q and R: both denominators nonzero'
    p=tuple(proof['domain_witness']); assert a.evaluate(p)==b.evaluate(p)
    with pytest.raises(ZeroDivisionError):a.evaluate((0,2,0))
    assert b.evaluate((0,2,0))==2
    assert proof['left']['denominator']==['x']
    bad=copy.deepcopy(proof);bad['domain_witness']=[0,0,0]
    assert not verify(a,b,bad)
    assert not verify(b,a,proof)

def test_v33_zero_denominator_cannot_prove_vacuous_identity():
    from omega_x_evolution.rational_axioms import classify, verify
    bad=quotient(ONE,('sub',X,X));ok=quotient(Y,ONE)
    proof=classify(bad,ok)
    assert proof['status']=='invalid-domain' and not verify(bad,ok,proof)

def test_v33_nonidentity_has_counterexample_outside_poles():
    from omega_x_evolution.rational_axioms import classify, verify
    a=quotient(X,('sub',X,ONE));b=quotient(Y,X)
    proof=classify(a,b)
    assert proof['status']=='refuted' and verify(a,b,proof)
    p=tuple(proof['counterexample'])
    assert p[0] not in (0,1) and a.evaluate(p)!=b.evaluate(p)
    forged=copy.deepcopy(proof);forged['counterexample']=[1,0,0]
    assert not verify(a,b,forged)

def test_v33_fraction_identity_over_three_variables():
    from omega_x_evolution.rational_axioms import classify, verify
    a=quotient(('sub',('mul',X,X),('mul',Y,Y)),('sub',X,Y))
    b=quotient(('mul',('add',X,Y),Z),Z)
    r=classify(a,b);assert r['status']=='proved' and verify(a,b,r)
    assert a.evaluate((Fraction(1,2),Fraction(1,3),2))==Fraction(5,6)
    with pytest.raises(ZeroDivisionError):b.evaluate((1,2,0))

def test_v33_autonomous_discovery_replay_and_publication(tmp_path):
    from omega_x_evolution.rational_axioms import discover,verify_discovery,publish
    r=discover(seed=42,budget=32)
    assert r==discover(seed=42,budget=32)
    assert r['proved'] and r['refuted'] and r['proposals']==32
    assert any(x['left']['denominator']!=x['right']['denominator'] for x in r['proved'])
    assert verify_discovery(r)
    m=GraphMemory(tmp_path/'rational.db',b'k'*32,'a')
    ids=publish(m,r);assert ids and ids==publish(m,r)
    assert all(m.snapshot()[0][i]['kind']=='evidence' for i in ids)
    bad=copy.deepcopy(r);bad['proved'][0]['grid_sha256']='0'*64
    before=m.snapshot()
    assert not verify_discovery(bad)
    with pytest.raises(ValueError):publish(m,bad)
    assert m.snapshot()==before

def test_v33_forged_polynomial_rejected():
    from omega_x_evolution.rational_axioms import Quotient, classify
    p=Polynomial(X);q=Quotient(p,Polynomial(ONE))
    object.__setattr__(p,'tree',('shell',))
    with pytest.raises(ValueError):classify(q,q)


def test_v33_grid_caps_and_typed_decoder():
    from omega_x_evolution.rational_axioms import Quotient, classify, verify
    t=('mul',('mul',X,Y),Z)
    for _ in range(3):t=('mul',t,t)
    q=quotient(ONE,t)
    r=classify(q,q)
    assert r['status']=='unknown' and not verify(q,q,r)
    with pytest.raises(ValueError):Quotient.from_json({'numerator':['lit',True,1],'denominator':['x']})
    with pytest.raises(ValueError):Quotient.from_json({'numerator':['x'],'denominator':['shell']})
    with pytest.raises(ValueError):q.evaluate((True,2,3))


def test_v33_cli_and_budget_extremes():
    import subprocess,sys,json
    from omega_x_evolution.rational_axioms import discover,verify_discovery
    result=subprocess.run([sys.executable,'-m','omega_x_evolution.axioms','--rational'],capture_output=True,text=True,timeout=15,check=True)
    r=json.loads(result.stdout)
    assert r['budget']==64 and verify_discovery(r)
    for seed,budget in ((0,16),(2**32-1,128)):
        report=discover(seed=seed,budget=budget)
        assert report['proposals']==budget and verify_discovery(report)
