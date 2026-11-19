import asyncio
import copy
import pytest
from omega_x_evolution.modal import Model, check
from omega_x_evolution.safety_synthesis import prove, verify, RuleBook
from omega_x_evolution.engine import Cascade, Expression, ImmutableAuditKernel, Config, run


def test_general_ctl_and_countermodel():
    m=Model((('start',('ready',)),('ready',('done',)),('done',('done',))), {'done':('finished',)})
    assert check(m, ('AF',('atom','finished')), 'start')['holds']
    assert check(m, ('AG',('EF',('atom','finished'))), 'start')['holds']
    assert not check(m, ('EG',('not',('atom','finished'))), 'start')['holds']
    assert check(m, ('AU',('not',('atom','finished')),('atom','finished')), 'start')['holds']
    bad=Model((('start',('ready','start')),('ready',('ready',))), {'ready':('finished',)})
    assert not check(bad, ('AF',('atom','finished')), 'start')['holds']
    assert check(bad, ('EG',('not',('atom','finished'))), 'start')['holds']
    with pytest.raises(ValueError): check(m, ('mystery',), 'start')


def test_ast_specs_and_certificate():
    c='-(x+y+abs(x-y)/(.01+x*y))';p=prove(c)
    assert p['proved'] and p['specification']['nodes'] and p['modal']['holds']
    assert any(n['kind']=='nonzero' for n in p['specification']['obligations'])
    assert p['rules'] and verify(c,p)
    for key in ('specification','modal','rules'):
        bad=copy.deepcopy(p);bad[key]=None
        assert not verify(c,bad)


def test_hidden_pole_precedes_empirical(monkeypatch):
    monkeypatch.setattr(Expression,'evaluate',lambda *args:pytest.fail('empirical evaluation before formal proof'))
    assert Cascade(42).evaluate('1/(x-.123456)').stage==1


def test_audit_bound_to_proof_and_learning():
    a=ImmutableAuditKernel(b'k'*32,'test');m=(1.,1.,1.,1.)
    with pytest.raises(ValueError):a.issue('unsafe','1/(x-.123456)',m)
    code='-(x+y+abs(x-y)/(.01+x*y))';token=a.issue('ok',code,m)
    assert a.verify(token,'ok',code,m)
    assert a.rules.snapshot()['entries']
    assert not a.verify(token,'ok',code,m)
    assert a.rules.lookup(code)


def test_rulebook_readback_and_tamper():
    b=RuleBook();code='1/(.25+x)';b.learn(code,prove(code));state=b.snapshot()
    assert RuleBook(state).snapshot()==state
    assert RuleBook(state).lookup(code)
    assert any(r['kind']=='nonzero' for r in RuleBook(state).matches('2/(.25+x)'))
    bad=copy.deepcopy(state);bad['entries'][0]['certificate']['rules'][0]['upper']=0
    with pytest.raises(ValueError):RuleBook(bad)
    with pytest.raises(ValueError):b.learn('x',prove('y'))


def test_actual_core_checkpoint(tmp_path):
    from omega_x_evolution.checkpoint import CheckpointStore
    cfg=Config(seed=5,generations=2,islands=1,workers=2)
    s=CheckpointStore(tmp_path/'c.db',b'k'*32)
    r=asyncio.run(run(cfg,checkpoint=s))
    assert r['formal_rule_count']>0
    _,state=s.load();assert state['safety_rules']['entries']
    assert asyncio.run(run(cfg,checkpoint=s,resume=True))==r


def test_actual_cluster_default_rules_and_forgery():
    from omega_x_evolution.cluster import ClusterConfig, initial_state, IslandActor, verify_transition, ClusterError
    c=ClusterConfig(islands=1,rounds=1,batch=2,budget=2)
    s=initial_state(c,0);n=IslandActor(c,0).step(s,None,s['elite'])
    assert n['safety_rules']['entries']
    verify_transition(c,s,n,None,s['elite'],False)
    bad=copy.deepcopy(n);bad['safety_rules']['entries']=[]
    with pytest.raises(ClusterError):verify_transition(c,s,bad,None,s['elite'],False)


def test_independent_exact_rational_checker_and_unknown():
    from omega_x_evolution.interval_checker import check as numeric
    code='1/(.25+x)';p=prove(code)
    assert p['independent']['proved'] and numeric(code,p['rules'])[0]
    assert not numeric('1/(x-.123456)',[])[0]
    r=copy.deepcopy(p['rules']);r[0]['upper']=0
    assert not numeric(code,r)[0]


def test_ctl_validation_of_total_model_and_formula():
    with pytest.raises(ValueError):Model((('a',()),),{})
    with pytest.raises(ValueError):Model((('a',('b',)),),{})
    m=Model((('a',('a',)),),{'a':('x',)})
    with pytest.raises(ValueError):check(m,('AX',('atom','x'),('atom','x')),'a')
    assert check(m,('EX',('atom','x')),'a')['holds']
    assert check(m,('AX',('atom','x')),'a')['holds']
    assert check(m,('EU',('atom','x'),('atom','x')),'a')['holds']


def test_untrusted_worker_cannot_reach_profiler(monkeypatch):
    import json
    from omega_x_evolution import engine, performance
    from omega_x_evolution.workers import EvaluationOutput
    async def propose(model,prompt,seed):
        p=json.loads(prompt)['parent']
        return f'<<<<<<< SEARCH\n{p}\n=======\n1/(x-.123456)\n>>>>>>> REPLACE'
    async def forged(inputs,executor):
        return [EvaluationOutput(engine.Result(3,(1.,1.,1.,1.)),(),1) for _ in inputs]
    monkeypatch.setattr(engine,'evaluate_batch',forged)
    monkeypatch.setattr(performance,'check_candidate',lambda *a:pytest.fail('unsafe candidate reached profiler'))
    r=asyncio.run(run(Config(generations=1,islands=1,workers=1),propose,performance_policy=performance.Policy()))
    assert r['rejections']==1 and r['champion']==engine.BASELINE


def test_rulebook_capped_and_rejects_unproved():
    b=RuleBook()
    for i in range(b.LIMIT+1):
        code=f'x+{i}';assert b.learn(code,prove(code))==(i<b.LIMIT)
    assert len(b.snapshot()['entries'])==b.LIMIT
    with pytest.raises(ValueError):b.learn('x/0',prove('x/0'))


def test_cluster_process_resume_retains_certified_rules(tmp_path):
    from omega_x_evolution.cluster import ClusterConfig, Store, LocalBackend, run_cluster
    cfg=ClusterConfig(islands=2,rounds=2,batch=2,budget=8,parallelism=2,migration_interval=1)
    store=Store(tmp_path/'islands.db',b'z'*32,cfg).initialize()
    with LocalBackend(cfg,processes=True) as b:
        assert not asyncio.run(run_cluster(store,b,stop_after=2))['complete']
    with LocalBackend(cfg,processes=True) as b:
        r=asyncio.run(run_cluster(store,b));assert r['complete']
        assert r==asyncio.run(run_cluster(store,b))
    for i in range(cfg.islands):
        _,state=store.read(i)
        assert RuleBook(state['safety_rules']).count>0


def test_general_modal_k_validity_and_countermodel():
    from omega_x_evolution.modal import prove_k
    p=('atom','p');q=('atom','q')
    axiom=('implies',('box',('implies',p,q)),('implies',('box',p),('box',q)))
    r=prove_k(axiom);assert r['proved'] and r['status']=='valid'
    assert prove_k(axiom)==r
    invalid=prove_k(('implies',('box',p),p))
    assert invalid['status']=='countermodel' and not invalid['proved']
    assert invalid['countermodel']['worlds'][0]['successors']==[]
    assert prove_k(('implies',('not',('box',p)),('diamond',('not',p))))['proved']
    assert prove_k(axiom,budget=1)['status']=='unknown'
    assert prove('1/(.25+x)')['modal']['k_proof']['proved']


def test_proof_replaces_redundant_numeric_smoke(monkeypatch):
    c=Cascade(42);seen=[];original=Expression.evaluate
    def record(self,x,y):
        seen.append((x,y));return original(self,x,y)
    monkeypatch.setattr(Expression,'evaluate',record)
    assert c.evaluate('-(x+y)').stage==3
    assert (.2,.4) not in seen
    assert len(seen)==3*len(c.challenge)+len(c.grid)
