import math
import random
import struct

import pytest
from omega_x_evolution.engine import Expression
from omega_x_evolution.superopt import optimize, compile_ir


def bits(n): return struct.pack('>d',float(n))


def test_rewrite_reduces_ast_and_cse_reduces_ir():
    source='(-(-(x*1))/1)+(x+y)*(x+y)'
    optimized=optimize(source)
    assert optimized.optimized_operations < optimized.original_operations
    assert optimized.ir.operations < optimized.optimized_operations
    assert optimized.ir.evaluate(.25,.5)==Expression(source).evaluate(.25,.5)


@pytest.mark.parametrize('source',['x*1','-(-x)','x/1','abs(abs(x-y))','(x+y)*(x+y)','x+0','0*x','x/(y-y)','(x*1000000)*1000000*1000000','min(-x,y)+max(y,-x)'])
def test_bit_exact_or_same_failure(source):
    original=Expression(source)
    optimized=optimize(source)
    rewritten=Expression(optimized.source)
    rng=random.Random(5)
    for x,y in [(0.,0.),(-0.,0.),(0.,-0.),(1.,1.),(.5,.5)]+[(rng.random(),rng.random()) for _ in range(50)]:
        try: expected=original.evaluate(x,y)
        except (ValueError,ArithmeticError) as exc:
            with pytest.raises(type(exc)): rewritten.evaluate(x,y)
            with pytest.raises(type(exc)): optimized.ir.evaluate(x,y)
        else:
            assert bits(expected)==bits(rewritten.evaluate(x,y))==bits(optimized.ir.evaluate(x,y))


@pytest.mark.parametrize('source',['__import__("os")','x.__class__','x**2','x'*2049])
def test_unsafe_ast_is_never_compiled(source):
    with pytest.raises(ValueError): compile_ir(source)


def test_ir_rejects_out_of_domain():
    ir=compile_ir('x+y')
    for x in (-1.,2.,float('nan'),float('inf')):
        with pytest.raises(ValueError): ir.evaluate(x,0.)


def test_generated_expressions_and_exception_equivalence():
    rng=random.Random(321)
    def generate(depth):
        if depth==0: return rng.choice(('x','y','0','1','0.001','1000000','-0.0'))
        a=generate(depth-1); b=generate(depth-1)
        return rng.choice((f'({a})*1', f'({a})/(-1)', f'abs(-({a}))',f'min({a},{a})',f'(({a})+({b}))',f'(({a})/({b}))',f'(({a})*({b}))'))
    points=[(-0.,0.),(0.,-0.),(1.,1.),(.01,.5),(.3,.7)]
    for _ in range(150):
        source=generate(3); ref=Expression(source); opt=optimize(source); rewritten=Expression(opt.source)
        assert opt.optimized_operations<=opt.original_operations
        for x,y in points:
            try: expected=ref.evaluate(x,y)
            except (ArithmeticError,ValueError) as e:
                with pytest.raises(type(e)): rewritten.evaluate(x,y)
                with pytest.raises(type(e)): opt.ir.evaluate(x,y)
            else: assert bits(expected)==bits(rewritten.evaluate(x,y))==bits(opt.ir.evaluate(x,y))
