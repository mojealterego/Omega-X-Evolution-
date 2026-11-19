import asyncio
import pytest
from omega_x_evolution.knowledge import collect, fit, Student, experiment
from omega_x_evolution.engine import Expression, apply_patch
import json

def test_training_determinism_and_serialization():
    data=asyncio.run(collect((21,22), per_seed=3))
    student=fit(data)
    assert student==fit(tuple(reversed(data)))
    assert Student.from_json(student.to_json())==student
    p=student.probabilities('fast','x+y')
    assert abs(sum(p)-1)<1e-12 and all(x>0 for x in p)
    patch=asyncio.run(student.proposal()('fast',json.dumps({'parent':'x+y'}),3))
    Expression(apply_patch('x+y',patch))

def test_seed_leakage_and_invalid_model():
    with pytest.raises(ValueError): asyncio.run(experiment((21,22),(22,23)))
    with pytest.raises(ValueError): Student.from_json('{"evil":true}')
    with pytest.raises(ValueError): fit(())

def test_report_measures_heldout_teacher_and_student():
    r=asyncio.run(experiment((21,22),(31,32),per_seed=3))
    assert r['training_records']==6 and r['validation_records']==6
    assert r['train_seeds']==[21,22] and r['validation_seeds']==[31,32]
    assert 0<=r['mean_regret']<=1 and 0<=r['top1_accuracy']<=1
    assert r['student_calls']==6 and r['teacher_calls']==30
