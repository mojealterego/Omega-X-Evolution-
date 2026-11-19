import math
import pytest
from dataclasses import replace
from omega_x_evolution.discovery import Dataset, Observation, discover, fixture, verify_report

@pytest.mark.parametrize('task',['sum','product','squares','distance'])
def test_symbolic_hypothesis_reproducible_and_verified(task):
    data=fixture(task,seed=45)
    report=discover(data,seed=4,budget=100,strategy='evolution')
    assert report==discover(data,seed=4,budget=100,strategy='evolution')
    assert report['attempts']==100 and report['holdout_evaluations']==1
    assert report['holdout_rmse']<=1e-12
    assert verify_report(data,report)
    assert not verify_report(data,{**report,'holdout_rmse':99})

def test_holdout_never_selects_hypothesis():
    data=fixture('product',seed=5)
    altered=replace(data,holdout=tuple(replace(p,z=p.z+2) for p in data.holdout))
    a=discover(data,seed=7,budget=25); b=discover(altered,seed=7,budget=25)
    assert a['expression']==b['expression'] and a['training_rmse']==b['training_rmse'] and a['holdout_rmse']!=b['holdout_rmse']

def test_dataset_validation():
    p=Observation(.1,.2,.3)
    with pytest.raises(ValueError): Dataset((p,),(p,))
    with pytest.raises(ValueError): Observation(float('nan'),0,0)
    with pytest.raises(ValueError): discover(fixture('sum',seed=5),budget=100000)
    with pytest.raises(ValueError): discover(fixture('sum',seed=5),strategy='arbitrary')

def test_custom_json_data_not_a_named_fixture():
    import json
    raw=json.dumps({'train':[{'x':i/10,'y':.3,'z':i/10-.3} for i in range(1,6)],
                    'holdout':[{'x':i/10,'y':.2,'z':i/10-.2} for i in range(6,9)]})
    data=Dataset.from_json(raw)
    result=discover(data,budget=60)
    assert result['empirical_match'] and verify_report(data,result)
    with pytest.raises(ValueError): Dataset.from_json('{"train":[],"holdout":[],"target":"x-y"}')
