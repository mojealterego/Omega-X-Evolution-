import numpy as np
import pytest
from dataclasses import replace
from omega_x_evolution.neuro_symbolic import hybrid, fixture, Split
from omega_x_evolution.neural import Architecture, fit, predict, evolve_architectures


def test_real_training_and_replay():
    data=fixture('smooth',seed=25)
    a=Architecture((8,), 'tanh', 'momentum', .08)
    model=fit(a,data.train,seed=2,epochs=120)
    assert model.losses[-1]<model.losses[0]
    assert np.array_equal(predict(model,data.test),predict(fit(a,data.train,seed=2,epochs=120),data.test))
    with pytest.raises(ValueError): Architecture((1000,), 'tanh','sgd',.1)


def test_hybrid_holdout_is_not_selection():
    data=fixture('smooth',seed=12)
    report=hybrid(data,seed=5,budget=80,epochs=120)
    other=hybrid(replace(data,test=tuple(replace(o,z=o.z+0.2) for o in data.test)),seed=5,budget=80,epochs=120)
    assert report['expression']==other['expression'] and report['selected']==other['selected']
    assert report['validation']==other['validation'] and report['test']!=other['test']
    assert report['validation']['selected']<=report['validation']['symbolic']
    assert report['training_loss_after'] < report['training_loss_before']
    with pytest.raises(ValueError): Split(data.train,data.train,data.test)


def test_architecture_evolution_and_budget():
    d=fixture('xor',seed=6)
    a=evolve_architectures(d,rounds=2,population=3,epochs=120,seed=9)
    b=evolve_architectures(d,rounds=2,population=3,epochs=120,seed=9)
    assert a==b and len(a['history'])<=6 and a['training_runs']<=6
    assert a['selected_validation_rmse']<=a['baseline_validation_rmse']
    other=evolve_architectures(replace(d,test=tuple(replace(o,z=1-o.z) for o in d.test)),rounds=2,population=3,epochs=120,seed=9)
    assert a['selected']==other['selected'] and a['history']==other['history']
    with pytest.raises(ValueError): evolve_architectures(d,rounds=100)


def test_safe_reusable_weight_artifact():
    import json
    from omega_x_evolution.neural import Model, digest
    d=fixture('smooth',seed=42)
    m=fit(Architecture((4,), 'relu','sgd',.05),d.train,epochs=5)
    restored=Model.from_json(m.to_json())
    assert digest(m)==digest(restored)
    assert np.array_equal(predict(m,d.test),predict(restored,d.test))
    corrupt=json.loads(m.to_json());corrupt['weights'][0][0][0]=float('nan')
    with pytest.raises(ValueError): Model.from_json(json.dumps(corrupt))
    corrupt=json.loads(m.to_json());corrupt['weights'][0].append([1,2,3,4])
    with pytest.raises(ValueError): Model.from_json(json.dumps(corrupt))


def test_exported_hybrid_and_nas_models_reproduce_predictions():
    import json
    from omega_x_evolution.neural import Model, rmse
    from omega_x_evolution.neuro_symbolic import symbolic_predictions
    d=fixture('smooth',seed=7)
    h=hybrid(d,epochs=25,budget=64)
    m=Model.from_json(json.dumps(h['model']))
    assert rmse(symbolic_predictions(h['expression'],d.test)+predict(m,d.test),d.test)==h['test']['hybrid']
    n=evolve_architectures(d,rounds=1,population=2,epochs=25)
    assert rmse(predict(Model.from_json(json.dumps(n['model'])),d.test),d.test)==n['selected_test_rmse']
