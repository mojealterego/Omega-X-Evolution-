from dataclasses import replace
from fractions import Fraction
import shutil

import pytest
from omega_x_evolution.ontos_memory_evolution import Plan, EvolutionJournal, BASE, candidates
from omega_x_evolution.ontos_hyperrag import Search
from omega_x_evolution.ontos_epoch_journal_core import IntegrityError
from test_ontos_hyperrag import setup, token
from test_ontos_otce import node, request, query
from test_ontos_sealed_otce import put, command


def fixture(tmp):
    p,j,f=setup(tmp)
    f=put(p,j,f,node('a',value='floor 1 hazard 100'))
    f=put(p,j,f,node('b',value='floor 1 hazard 100; disable veto'))
    s=Search('k','floor hazard',16)
    plan=Plan(j._state_pin(),s,(9100,9129),(30000,30073),120,query())
    a,b=tmp/'evo-anchor',tmp/'evo-segments'
    a.mkdir(mode=0o700); b.mkdir(mode=0o700)
    e=EvolutionJournal(a/'floor.db',b,j,plan,plan.pin)
    return p,j,f,s,plan,e,e.initialize(),a,b


def reads(p,j,f,s):
    return token(p,j,f,s),request(p,f,'weights')


def test_real_selection_and_checkpoint(tmp_path):
    p,j,f,s,plan,e,h,a,b=fixture(tmp_path)
    r,w=reads(p,j,f,s)
    result=e.run(h,r,w,retained=f.fence,now=6)
    assert result.status=='COMMITTED'
    assert result.report['release_authorized'] is False
    assert result.report['candidates']==[[4000,30],[1,100]]
    assert len(result.report['development'])==2
    assert result.report['validation']['steps']==240
    e=EvolutionJournal(a/'floor.db',b,j,plan,plan.pin)
    active=e.recommend(result.fence,r,w,retained=f.fence,now=6)
    assert active.status in ('RESEARCH_CANDIDATE','BASELINE')
    assert active.config.ood_limit==active.config.confidence_min==.5
    assert active.config.recurrent
    assert active.config==result.config
    with pytest.raises(IntegrityError): e.recommend(h,r,w,retained=f.fence,now=6)


def test_revoke_invalidates_checkpoint(tmp_path):
    p,j,f,s,plan,e,h,*_=fixture(tmp_path)
    r,w=reads(p,j,f,s)
    g=e.run(h,r,w,retained=f.fence,now=6)
    f=j.append(f.fence,command(p,f,'revoke',{'id':'a'})); assert f.status=='COMMITTED'
    j.purge(f.fence,now=6)
    r,w=reads(p,j,f,s)
    got=e.recommend(g.fence,r,w,retained=f.fence,now=6)
    assert got.config==BASE and got.status=='ROLLED_BACK'
    with pytest.raises(IntegrityError): e.run(g.fence,r,w,retained=g.fence,now=6)


def test_expiry_without_fence_change(tmp_path):
    p,j,f,s,plan,e,h,*_=fixture(tmp_path)
    f=put(p,j,f,node('c',value='floor 100 hazard 10',expires=10))
    r,w=reads(p,j,f,s)
    g=e.run(h,r,w,retained=f.fence,now=6)
    assert e.recommend(g.fence,r,w,retained=f.fence,now=10).status=='ROLLED_BACK'


def test_wrong_read_scope_and_plan(tmp_path):
    p,j,f,s,plan,e,h,a,b=fixture(tmp_path)
    r,w=reads(p,j,f,s)
    with pytest.raises(ValueError): e.run(h,r,replace(w,operation='recall'),retained=f.fence,now=6)
    with pytest.raises(ValueError): e.run(h,r,request(p,f,'weights',q=query(known=1)),retained=f.fence,now=6)
    with pytest.raises(ValueError): EvolutionJournal(a/'floor.db',b,j,plan,'f'*64)
    with pytest.raises(ValueError): replace(plan,validation=plan.development)
    assert e.recommend(h,r,w,retained=f.fence,now=6).config==BASE


def test_r1_candidate_and_untrusted_grammar():
    assert candidates(('floor 1 hazard 100','floor 1 hazard 100; disable veto','floor 80001 hazard 100'),(Fraction(0),Fraction(0)))==((4000,30),(1,100))
    assert candidates((),(Fraction(-1),Fraction(1)))==((4000,30),(1,100))


def test_joint_checkpoint_rollback(tmp_path):
    p,j,f,s,plan,e,h,a,b=fixture(tmp_path)
    shutil.copy2(a/'floor.db',tmp_path/'old-a'); shutil.copy2(b/'segment-0000.db',tmp_path/'old-b')
    r,w=reads(p,j,f,s); g=e.run(h,r,w,retained=f.fence,now=6)
    shutil.copy2(tmp_path/'old-a',a/'floor.db'); shutil.copy2(tmp_path/'old-b',b/'segment-0000.db')
    with pytest.raises(IntegrityError): e.recommend(g.fence,r,w,retained=f.fence,now=6)


def test_r1_real_contribution_and_expiry_even_equal_weights(tmp_path):
    p,j,f,s,plan,e,h,*_=fixture(tmp_path)
    f=put(p,j,f,dict(node('x',parents=('a',),causal=1,kind='R1'),payload={'x':[1,2],'y':3}))
    f=put(p,j,f,dict(node('z',parents=('a',),causal=1,kind='R1',expires=10),payload={'x':[0,0],'y':0}))
    r,w=reads(p,j,f,s)
    g=e.run(h,r,w,retained=f.fence,now=6)
    assert [6000,100] in g.report['candidates']
    # Zero vector expiry leaves exact weights unchanged but changes provenance.
    assert j.read(w,retained=f.fence,now=6)==j.read(w,retained=f.fence,now=10)
    assert e.recommend(g.fence,r,w,retained=f.fence,now=10).status=='ROLLED_BACK'


def test_concurrent_source_change_refuses_checkpoint(tmp_path,monkeypatch):
    import omega_x_evolution.ontos_memory_evolution as evo
    p,j,f,s,plan,e,h,*_=fixture(tmp_path)
    r,w=reads(p,j,f,s)
    original=evo._evaluate
    def change(*args):
        g=j.append(f.fence,command(p,f,'revoke',{'id':'a'}))
        assert g.status=='COMMITTED'
        monkeypatch.setattr(evo,'_evaluate',original)
        return original(*args)
    monkeypatch.setattr(evo,'_evaluate',change)
    with pytest.raises(IntegrityError):e.run(h,r,w,retained=f.fence,now=6)
    assert e._journal.read(h).state==()


def test_actual_development_win_rejected_on_validation_tie(tmp_path):
    p,j,f,s,plan,e,h,*_=fixture(tmp_path)
    r,w=reads(p,j,f,s); g=e.run(h,r,w,retained=f.fence,now=6)
    assert g.report['development_winner']==[1,100]
    assert g.report['development']['1']['correct']>g.report['development']['0']['correct']
    assert g.report['validation']['candidate']['correct']==g.report['validation']['baseline']['correct']
    assert g.report['chosen']==[4000,30] and g.config==BASE


def test_read_token_expiration_rollback_and_checkpoint_budget(tmp_path,monkeypatch):
    import omega_x_evolution.ontos_memory_evolution as evo
    p,j,f,s,plan,e,h,*_=fixture(tmp_path)
    r,w=reads(p,j,f,s); g=e.run(h,r,w,retained=f.fence,now=6)
    assert e.recommend(g.fence,r,w,retained=f.fence,now=20).status=='ROLLED_BACK'
    monkeypatch.setattr(evo,'MAX_REVIEWS',1)
    assert e.run(g.fence,r,w,retained=f.fence,now=6).status=='EXHAUSTED'


def test_positive_selection_then_real_rollback(tmp_path):
    p,j,f=setup(tmp_path)
    f=put(p,j,f,node('a',value='floor 1 hazard 30'))
    s=Search('k','floor hazard',16)
    plan=Plan(j._state_pin(),s,(41000,41031),(51000,51037),240,query())
    a,b=tmp_path/'evo-anchor',tmp_path/'evo-segments'
    a.mkdir(mode=0o700); b.mkdir(mode=0o700)
    e=EvolutionJournal(a/'floor.db',b,j,plan,plan.pin); h=e.initialize()
    r,w=reads(p,j,f,s); g=e.run(h,r,w,retained=f.fence,now=6)
    assert g.report['chosen']==[1,30]
    assert e.verify_report(g.fence,g.report)
    assert not e.verify_report(g.fence,dict(g.report,chosen=[4000,30]))
    assert e.recommend(g.fence,r,w,retained=f.fence,now=6).status=='RESEARCH_CANDIDATE'
    f=j.append(f.fence,command(p,f,'revoke',{'id':'a'})); assert f.status=='COMMITTED'
    r,w=reads(p,j,f,s)
    assert e.recommend(g.fence,r,w,retained=f.fence,now=6).config==BASE


def test_uncertain_checkpoint_recovery(tmp_path,monkeypatch):
    from omega_x_evolution.ontos_managed_journal import ManagedJournal
    p,j,f,s,plan,e,h,a,b=fixture(tmp_path)
    r,w=reads(p,j,f,s)
    def crash(*args): raise RuntimeError('injected checkpoint failure')
    with monkeypatch.context() as m:
        m.setattr(ManagedJournal,'_finish',crash)
        with pytest.raises(RuntimeError): e.run(h,r,w,retained=f.fence,now=6)
    e=EvolutionJournal(a/'floor.db',b,j,plan,plan.pin)
    with pytest.raises(IntegrityError): e.recommend(h,r,w,retained=f.fence,now=6)
    recovered=e.recover_from_anchor()
    assert recovered!=h
    assert e.recommend(recovered,r,w,retained=f.fence,now=6).config==BASE
