import sqlite3
import pytest
from omega_x_evolution.graph_memory import GraphMemory, IntegrityError

KEY=b'k'*32

def test_durable_cited_graph_and_tenant_isolation(tmp_path):
    p=tmp_path/'memory.db'; a=GraphMemory(p,KEY,'alice')
    experiment=a.add('experiment','symbolic regression experiment',{'seed':42})
    result=a.add('result','heldout RMSE and metrics',{'rmse':0.1})
    a.link(experiment,'produced',result)
    assert a.add('experiment','symbolic regression experiment',{'seed':42})==experiment
    b=GraphMemory(p,KEY,'bob'); b.add('result','symbolic regression secret',{})
    matches=GraphMemory(p,KEY,'alice').retrieve('symbolic regression',limit=3)
    assert [r['id'] for r in matches]==[experiment,result]
    assert matches[1]['path']==[experiment,result]
    assert matches[1]['payload']=={'rmse':0.1}
    with pytest.raises(ValueError): b.link(experiment,'produced',result)


def test_tampered_record_or_edge_fails_closed(tmp_path):
    p=tmp_path/'m.db'; m=GraphMemory(p,KEY,'alpha')
    a=m.add('experiment','experiment',{}); b=m.add('result','result',{})
    m.link(a,'produced',b)
    with sqlite3.connect(p) as db: db.execute("UPDATE edges SET relation='derived' WHERE tenant='alpha'")
    with pytest.raises(IntegrityError): m.retrieve('experiment')
    with sqlite3.connect(p) as db:
        db.execute("DELETE FROM edges"); db.execute("UPDATE nodes SET body='{}' WHERE tenant='alpha'")
    with pytest.raises(IntegrityError): m.retrieve('experiment')


def test_validation_and_bound(tmp_path):
    m=GraphMemory(tmp_path/'m.db',KEY,'alpha')
    with pytest.raises(ValueError): m.add('result','a',{'score':float('nan')})
    with pytest.raises(ValueError): m.retrieve('x',limit=1000)
    with pytest.raises(ValueError): GraphMemory(tmp_path/'m.db',b'x','alpha')


def test_namespace_key_binding_and_atomic_experiment(tmp_path):
    p=tmp_path/'m.db'; m=GraphMemory(p,KEY,'alpha')
    with pytest.raises(IntegrityError): GraphMemory(p,b'x'*32,'alpha')
    other=GraphMemory(p,b'x'*32,'beta'); other.add('result','independent namespace',{})
    with pytest.raises(ValueError): m.record_experiment({'plan':1},{'invalid':float('nan')})
    assert m.retrieve('experiment')==[]
    a,b=m.record_experiment({'plan':1},{'score':1})
    assert (a,b)==m.record_experiment({'plan':1},{'score':1})
    assert len(m.retrieve('experiment'))==2


def test_graph_storage_cap_and_strict_json(tmp_path,monkeypatch):
    from omega_x_evolution import graph_memory
    m=GraphMemory(tmp_path/'m.db',KEY,'alpha')
    monkeypatch.setattr(graph_memory,'MAX_STORAGE',250)
    m.add('result','small',{'a':'x'*40})
    with pytest.raises(ValueError): m.add('result','large',{'a':'x'*200})
    with pytest.raises(ValueError): m.add('result','bad',{1:'not string'})
