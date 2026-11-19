import asyncio
import random
import pytest
from shinka.omega.engine import (Expression, apply_patch, Audit, Cascade, Archive,
    Artifact, Genome, Router, Arm, run, Config, Distillation, Trial, BASELINE)

@pytest.mark.parametrize('code', ['__import__("os")', 'x.__class__', 'x**999999', '[x for x in y]', 'float("nan")', '1e309', 'True', 'x/0'])
def test_untrusted_expression_rejected(code):
    with pytest.raises((ValueError, ArithmeticError)):
        Expression(code).evaluate(0.2, 0.4)

def test_patch_strict_and_atomic():
    patch = '<<<<<<< SEARCH\nx+y\n=======\nx*y\n>>>>>>> REPLACE'
    assert apply_patch('x+y', patch) == 'x*y'
    with pytest.raises(ValueError): apply_patch('x+y+x+y', patch)
    with pytest.raises(ValueError): apply_patch('x+y', patch+'\nextra')

def test_receipt_binds_candidate_and_replay():
    a = Audit(b'x'*32, 'task-v1'); t = a.issue('s', 'x+y', (1.,1.,1.,1.))
    assert not a.verify(t, 's', 'x*y', (1.,1.,1.,1.))
    assert a.verify(t, 's', 'x+y', (1.,1.,1.,1.))
    assert not a.verify(t, 's', 'x+y', (1.,1.,1.,1.))

def test_cascade_rejects_asymmetry_and_scores_baseline():
    c = Cascade(5)
    assert c.evaluate('x').stage == 2
    assert c.evaluate('x/0').stage == 1
    assert c.evaluate(BASELINE).stage == 3

def test_archive_pareto_and_duplicate():
    a = Archive(2); g = Genome()
    p = Artifact('p',None,0,0,BASELINE,g,(.5,.8,.7,1.))
    assert a.add(p)
    assert not a.add(p)
    with pytest.raises(ValueError): a.add(Artifact('bad','missing',0,1,BASELINE,g,(1.,1.,1.,1.)))
    assert a.add(Artifact('c','p',0,1,BASELINE,g,(.7,.8,.7,1.)))
    assert [i.id for i in a.cells[0][Expression(BASELINE).descriptor]] == ['c']
    assert len(a.lineage) == 2

def test_router_never_exceeds_budget():
    r = Router([Arm('a', 'fast', 3)], 5)
    assert r.select(random.Random(1),False).id == 'a'
    assert r.select(random.Random(1),False) is None
    assert r.spent == 3

def test_distillation_comparable_only():
    d=Distillation(.01)
    d.add(Trial('p','prompt','a',.6,.5,True,'v1'))
    d.add(Trial('p','prompt','b',.2,.5,False,'v2'))
    assert len(d.sft)==1 and not d.pairs()
    d.add(Trial('p','prompt','c',.2,.5,False,'v1'))
    assert len(d.pairs())==1

def test_simulation_reproducible_and_improves():
    cfg=Config(seed=5,generations=5,islands=3,workers=3,budget=1000)
    a=asyncio.run(run(cfg)); b=asyncio.run(run(cfg))
    assert a==b
    assert a['champion_score'] > a['baseline_score']
    assert a['attempts'] <= cfg.generations*cfg.islands*cfg.workers
    assert a['spent'] <= cfg.budget
    assert a['rejections'] > 0

def test_adapter_uses_existing_client_contract():
    from shinka.omega.providers import ShinkaProposal
    class Fake:
        async def query(self, **kwargs):
            assert kwargs['msg']=='p' and 'SEARCH' in kwargs['system_msg']
            return type('Result',(),{'content':'patch','cost':.01,'num_tool_calls':0})()
    p = ShinkaProposal({'fast':'model-a','deep':'model-b'}, client_factory=lambda _:Fake())
    assert asyncio.run(p('fast','p',1))=='patch'
    assert p.reported_cost == .01
    with pytest.raises(ValueError): ShinkaProposal({'fast':'headless/agent','deep':'b'},client_factory=lambda _:Fake())

def test_evaluator_source_integrity(tmp_path):
    f=tmp_path/'evaluator.py'; f.write_text('trusted')
    a=Audit(b'x'*32,'v1',source_path=f)
    assert a.integrity_ok()
    f.write_text('changed')
    assert not a.integrity_ok()
    with pytest.raises(ValueError): a.issue('s','x+y',(1.,1.,1.,1.))

def test_holdout_failure_is_explicit():
    c=Cascade(1)
    c.holdout=((.5,.5),)
    assert c.heldout('1/(x-y)') is None
