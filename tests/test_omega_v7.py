import pytest
from omega_x_evolution.formal import certify, prove_rules, verify_ir
from omega_x_evolution.superopt import optimize, compile_ir, IR, Instruction

@pytest.mark.parametrize('source', ['-(-(x*1))/1', 'abs(-abs(x-y))', 'min(x/0,x/0)', 'max(-0.0,-0.0)', '(x+y)*(x+y)', '(-1)*x'])
def test_optimization_certificate(source):
    optimized = optimize(source)
    assert certify(source, optimized.source).proved
    assert verify_ir(optimized.source, optimized.ir)

def test_reassociation_and_signed_zero_not_certified():
    assert not certify('x+0.0','x').proved
    assert not certify('x*0','0.0').proved
    assert not certify('x/0','0.0').proved

def test_all_symbolic_rules():
    results=prove_rules()
    assert len(results)==9 and set(results.values())=={'unsat'}

def test_forged_ir_is_rejected():
    ir=compile_ir('x+y')
    assert not verify_ir('x-y',ir)
    assert not verify_ir('x+y',IR(ir.instructions+(Instruction('const',(),1.),),ir.operations))
    assert not verify_ir('x+y',IR(ir.instructions,999))

def test_invalid_source_never_certified():
    with pytest.raises(ValueError): certify('__import__("os")','x')

def test_certified_optimization_fail_closed(monkeypatch):
    from omega_x_evolution import formal
    assert formal.verified_optimize('x*1').source=='x'
    monkeypatch.setattr(formal,'prove_rules',lambda:{'rule':'unknown'})
    with pytest.raises(formal.ProofError): formal.verified_optimize('x*1')
