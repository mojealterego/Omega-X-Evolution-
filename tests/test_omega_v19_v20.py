import json
import sqlite3
from dataclasses import replace
import pytest
from omega_x_evolution.science import fixture, discover, verify, Data
from omega_x_evolution.runtime import Campaign, Task, run_campaign
from omega_x_evolution.checkpoint import CheckpointStore, CheckpointError
from omega_x_evolution.graph_memory import GraphMemory

@pytest.mark.parametrize('domain',['kinematics','mechanics','kinetics','dynamics'])
def test_dimensionally_valid_discovery(domain):
    d=fixture(domain,seed=104)
    r=discover(d)
    assert r['test_rmse']<1e-10 and r['test_evaluations']==1
    assert verify(d,r) and not verify(d,{**r,'test_rmse':42})
    assert Data.from_json(d.to_json())==d


def test_test_label_isolation_and_limits():
    d=fixture('kinematics',seed=5)
    other=replace(d,test=tuple((x,z+1) for x,z in d.test))
    a,b=discover(d),discover(other)
    assert a['terms']==b['terms'] and a['selection']==b['selection']
    assert a['test_rmse']!=b['test_rmse']
    with pytest.raises(ValueError): replace(d,test=d.train)
    with pytest.raises(ValueError): discover(d,degree=100)
    with pytest.raises(ValueError): replace(d,output_unit=(11,0,0,0))


def test_runtime_resume_and_graph_recovery(tmp_path):
    c=Campaign((Task('kinematics',123),Task('bits',124),Task('numeric',125)),budget=128,epochs=10)
    expected=run_campaign(c)
    ck=CheckpointStore(tmp_path/'run.db',b'k'*32)
    m=GraphMemory(tmp_path/'mem.db',b'm'*32,'lab')
    r=run_campaign(c,checkpoint=ck,memory=m,stop_after=1)
    assert r['completed']==1
    actual=run_campaign(c,checkpoint=CheckpointStore(ck.path,b'k'*32),memory=m,resume=True)
    assert actual==expected and actual['completed']==3
    assert len(m.retrieve('experiment plan',limit=32))>=3
    assert run_campaign(c,checkpoint=CheckpointStore(ck.path,b'k'*32),memory=m,resume=True)==expected
    with pytest.raises(CheckpointError): run_campaign(replace(c,epochs=12),checkpoint=ck,resume=True)


def test_runtime_crash_between_checkpoint_and_graph(tmp_path,monkeypatch):
    c=Campaign((Task('mechanics',8),),budget=64,epochs=10)
    ck=CheckpointStore(tmp_path/'run.db',b'k'*32); m=GraphMemory(tmp_path/'mem.db',b'm'*32,'lab')
    original=m.record_experiment
    def fail(*a,**kw): raise OSError('injected interruption')
    monkeypatch.setattr(m,'record_experiment',fail)
    with pytest.raises(OSError): run_campaign(c,checkpoint=ck,memory=m)
    assert ck.load()[0]==1
    monkeypatch.setattr(m,'record_experiment',original)
    assert run_campaign(c,checkpoint=ck,memory=m,resume=True)==run_campaign(c)
    assert m.retrieve('experiment plan')


def test_campaign_limits():
    with pytest.raises(ValueError): Task('shell',1)
    with pytest.raises(ValueError): Campaign((Task('numeric',1),)*2)
    with pytest.raises(ValueError): Campaign((Task('numeric',1),),budget=999999)
    with pytest.raises(ValueError): run_campaign(Campaign((Task('numeric',1),)),resume=True)


def test_custom_campaign_and_report_replay(tmp_path):
    from omega_x_evolution.runtime import verify_campaign
    d=fixture('kinematics',seed=17)
    c=Campaign((Task('kinematics',17,data_json=d.to_json()),),budget=32,epochs=3)
    assert Campaign.from_json(json.dumps(c.wire()))==c
    r=run_campaign(c)
    assert r['records'][0]['result']['data_sha256']==d.digest()
    assert r['records'][0]['task']['data_sha256']==d.digest() and 'data_json' not in r['records'][0]['task']
    assert verify_campaign(c,r) and not verify_campaign(c,{**r,'completed':3})
    with pytest.raises(ValueError): Task('bits',1,data_json=d.to_json())


def test_campaign_uses_original_evolution_and_semantic_memory(tmp_path):
    from omega_x_evolution.semantic_memory import retrieve
    c=Campaign((Task('scheduler',42),),budget=16,epochs=2)
    m=GraphMemory(tmp_path/'m.db',b'k'*32,'research')
    r=run_campaign(c,memory=m)
    assert 0<r['records'][0]['result']['attempts']<=16
    assert r['records'][0]['result']['mode']=='offline-simulation'
    assert retrieve(m,'scheduler')
