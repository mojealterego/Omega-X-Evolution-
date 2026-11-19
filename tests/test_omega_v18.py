from dataclasses import replace
import json
import pytest
from omega_x_evolution.experiments import design, execute, Plan
from omega_x_evolution.compute import CPUBackend, Router
from omega_x_evolution.graph_memory import GraphMemory
from omega_x_evolution.neuro_symbolic import fixture


def test_plan_and_selection_no_test_leakage(tmp_path):
    d=fixture('smooth',seed=17); altered=replace(d,test=tuple(replace(o,z=o.z+5) for o in d.test))
    p=design(d,seed=9,budget=64,epochs=20)
    assert p==design(altered,seed=9,budget=64,epochs=20)
    assert Plan.from_json(p.to_json())==p
    r=execute(p,d,router=Router([CPUBackend()]))
    s=execute(p,altered,router=Router([CPUBackend()]))
    assert r['selected']==s['selected'] and r['validation']==s['validation']
    assert r['test_rmse']!=s['test_rmse']
    assert r['test_evaluations']==1 and r['attempts']<=p.budget
    assert r['validation_evaluations']==len(p.candidates)


def test_memory_integration_and_contract(tmp_path):
    d=fixture('xor',seed=7); p=design(d,seed=1,budget=64,epochs=10)
    memory=GraphMemory(tmp_path/'graph.db',b'q'*32,'lab')
    r=execute(p,d,memory=memory)
    hit=memory.retrieve('experiment plan',limit=4)
    assert {r['plan_id'],r['result_id']}<={x['id'] for x in hit}
    assert execute(p,d,memory=memory)==r
    with pytest.raises(ValueError): execute(p,fixture('xor',seed=8))
    with pytest.raises(ValueError): design(d,budget=100000)
    obj=json.loads(p.to_json());obj['candidates']=['shell']
    with pytest.raises(ValueError): Plan.from_json(json.dumps(obj))


def test_work_budget_controls_plan_and_fails_closed():
    from omega_x_evolution.experiments import NEURAL, RESIDUAL
    d=fixture('smooth'); work=len(d.train)*10
    a=design(d,epochs=10,work_cap=1)
    b=design(d,epochs=10,work_cap=work*NEURAL.parameters)
    c=design(d,epochs=10,work_cap=work*(NEURAL.parameters+RESIDUAL.parameters))
    assert [len(p.candidates) for p in (a,b,c)]==[1,2,3]
    assert execute(a,d)['training_work']==0
    assert execute(b,d)['training_work']==work*NEURAL.parameters
    with pytest.raises(ValueError): execute(replace(a,candidates=('symbolic','neural')),d)
