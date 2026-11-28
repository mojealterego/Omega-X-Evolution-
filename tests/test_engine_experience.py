import asyncio
from dataclasses import replace
from fractions import Fraction
import shutil

import pytest
from omega_x_evolution.engine import Config
from omega_x_evolution.engine_dgm import DGMJournal, Plan, BASE, Selector
from omega_x_evolution.engine_experience import ExperienceJournal, revoke_bytes
from omega_x_evolution.ontos_epoch_journal_core import IntegrityError
from test_engine_dgm import setup as dgm_setup
from test_ontos_otce import R, W
from test_ontos_sealed_otce import command


def setup(tmp, seed=41):
    p,j,f,s,clock,m,_,_,_,_,_=dgm_setup(tmp)
    plan=Plan(Config(generations=1,islands=1,workers=1,budget=20),2,5,seed)
    a,b,c,e=[tmp/x for x in ('learn-dgm-a','learn-dgm-b','learn-a','learn-b')]
    for path in (a,b,c,e): path.mkdir(mode=0o700)
    d=DGMJournal(a/'floor.db',b,m,plan,plan.pin(m)); h=d.initialize(source_fence=f.fence)
    pin=ExperienceJournal.pin_for(d)
    x=ExperienceJournal(c/'floor.db',e,d,pin)
    z=x.initialize(h,source_fence=f.fence)
    return p,j,f,clock,d,h,x,z,c,e


def advance(d,h,x,z,f):
    g=asyncio.run(d.step(h,source_fence=f.fence)); assert g.status=='COMMITTED'
    q=x.sync(z,g.fence,source_fence=f.fence); assert q.status=='COMMITTED'
    return g,q.fence


def test_real_positive_experience_and_restart(tmp_path):
    p,j,f,clock,d,h,x,z,c,e=setup(tmp_path)
    g,z=advance(d,h,x,z,f)
    v=x.view(z,g.fence,source_fence=f.fence)
    assert g.record['promoted'] and v.statistics.n==1
    assert v.entries[0].label==1 and v.entries[0].selector==Selector(0,0,0)
    assert v.statistics.b==(1,0,0,0)
    assert v.perceptron==(1,0,0,0)
    assert v.rank((BASE,Selector(0,0,0)))[0]==Selector(0,0,0)
    x=ExperienceJournal(c/'floor.db',e,d,ExperienceJournal.pin_for(d))
    assert x.view(z,g.fence,source_fence=f.fence)==v
    assert x.sync(z,g.fence,source_fence=f.fence).status=='UP_TO_DATE'


def test_real_negative_experience(tmp_path):
    p,j,f,clock,d,h,x,z,*_=setup(tmp_path,5)
    g,z=advance(d,h,x,z,f)
    v=x.view(z,g.fence,source_fence=f.fence)
    assert not g.record['promoted'] and v.entries[0].label==-1
    assert v.statistics.b==(-1,0,0,0)
    assert v.rank((Selector(0,0,0),BASE))[0]==BASE


def test_cascade_revocation_and_exact_downdate(tmp_path):
    p,j,f,clock,d,h,x,z,*_=setup(tmp_path)
    g,z=advance(d,h,x,z,f)
    second,z=advance(d,g.fence,x,z,f)
    v=x.view(z,second.fence,source_fence=f.fence)
    assert len(v.entries)==2
    reason='a'*64; sig=R.sign(revoke_bytes(x.pin,1,v.entries[0].digest,reason))
    out=x.revoke(z,second.fence,1,reason,sig,source_fence=f.fence)
    assert out.status=='COMMITTED'
    new=x.view(out.fence,second.fence,source_fence=f.fence)
    assert new.entries==() and new.statistics.n==0 and new.ridge==(0,)*4 and new.perceptron==(0,)*4
    assert new.invalidated_from==1 and new.trusted_active==BASE
    with pytest.raises(IntegrityError): x.view(z,second.fence,source_fence=f.fence)
    assert x.revoke(out.fence,second.fence,1,reason,sig,source_fence=f.fence).status=='REJECTED'


def test_revoked_prefix_cannot_be_reactivated_by_future_import(tmp_path):
    p,j,f,clock,d,h,x,z,*_=setup(tmp_path)
    g,z=advance(d,h,x,z,f)
    v=x.view(z,g.fence,source_fence=f.fence)
    reason='b'*64; sig=R.sign(revoke_bytes(x.pin,1,v.entries[0].digest,reason))
    out=x.revoke(z,g.fence,1,reason,sig,source_fence=f.fence)
    second,z=advance(d,g.fence,x,out.fence,f)
    v=x.view(z,second.fence,source_fence=f.fence)
    assert v.entries==() and v.imported==2 and v.invalidated_from==1


def test_wrong_authority_and_tampered_revocation(tmp_path):
    p,j,f,clock,d,h,x,z,*_=setup(tmp_path)
    g,z=advance(d,h,x,z,f); v=x.view(z,g.fence,source_fence=f.fence)
    reason='c'*64; raw=revoke_bytes(x.pin,1,v.entries[0].digest,reason)
    for sig,r in ((W.sign(raw),reason),(R.sign(raw),'d'*64)):
        assert x.revoke(z,g.fence,1,r,sig,source_fence=f.fence).status=='REJECTED'
    assert x.view(z,g.fence,source_fence=f.fence)==v


def test_source_and_dgm_fences_required(tmp_path):
    p,j,f,clock,d,h,x,z,*_=setup(tmp_path)
    g,z=advance(d,h,x,z,f)
    with pytest.raises(IntegrityError): x.view(z,h,source_fence=f.fence)
    new=j.append(f.fence,command(p,f,'revoke',{'id':'a'})); assert new.status=='COMMITTED'
    with pytest.raises(IntegrityError): x.view(z,g.fence,source_fence=new.fence)
    with pytest.raises(IntegrityError): x.view(z,g.fence,source_fence=f.fence)


def test_full_experience_rollback(tmp_path):
    p,j,f,clock,d,h,x,z,a,b=setup(tmp_path)
    shutil.copy2(a/'floor.db',tmp_path/'old-a'); shutil.copy2(b/'segment-0000.db',tmp_path/'old-b')
    g,z=advance(d,h,x,z,f)
    shutil.copy2(tmp_path/'old-a',a/'floor.db'); shutil.copy2(tmp_path/'old-b',b/'segment-0000.db')
    with pytest.raises(IntegrityError): x.view(z,g.fence,source_fence=f.fence)


def test_prefix_lag_and_no_external_record_ingestion(tmp_path):
    p,j,f,clock,d,h,x,z,*_=setup(tmp_path)
    g=asyncio.run(d.step(h,source_fence=f.fence))
    v=x.view(z,g.fence,source_fence=f.fence)
    assert v.imported==0 and v.pending==1
    forged={'kind':'learn','round':1,'digest':'a'*64,'selector':[0,0,0],'label':1,'active':[0,0,0]}
    from omega_x_evolution.ontos_v72_jcs import canonical_json
    q=x._journal.append(z,canonical_json(forged)); assert q.status=='COMMITTED'
    with pytest.raises(IntegrityError): x.view(q.snapshot.fence,g.fence,source_fence=f.fence)


def test_recovery_uncertain_import(tmp_path,monkeypatch):
    from omega_x_evolution.ontos_managed_journal import ManagedJournal
    p,j,f,clock,d,h,x,z,a,b=setup(tmp_path)
    g=asyncio.run(d.step(h,source_fence=f.fence))
    original=ManagedJournal._finish
    def crash(self,*args):
        if self is x._journal: raise RuntimeError('injected')
        return original(self,*args)
    with monkeypatch.context() as m:
        m.setattr(ManagedJournal,'_finish',crash)
        with pytest.raises(RuntimeError): x.sync(z,g.fence,source_fence=f.fence)
    x=ExperienceJournal(a/'floor.db',b,d,ExperienceJournal.pin_for(d))
    with pytest.raises(IntegrityError): x.view(z,g.fence,source_fence=f.fence)
    z=x.recover_from_anchor(g.fence,source_fence=f.fence)
    assert x.view(z,g.fence,source_fence=f.fence).statistics.n==1


def test_guarded_transfer_to_fresh_engine_assessment(tmp_path):
    p,j,f,clock,d,h,x,z,*_=setup(tmp_path)
    g,z=advance(d,h,x,z,f)
    pool=(BASE,Selector(0,0,0))
    assert x.rank(z,g.fence,pool,source_fence=f.fence)[0]==Selector(0,0,0)
    with pytest.raises(ValueError):
        asyncio.run(x.assess(z,g.fence,pool,tuple(d.plan.schedule(0)[:2]),source_fence=f.fence))
    report=asyncio.run(x.assess(z,g.fence,pool,(100,200),source_fence=f.fence))
    assert report['candidate']==[0,0,0] and report['release_authorized'] is False
    assert report['seeds']==[100,200] and len(report['candidate_metrics'])==2
    assert report['incumbent']==[0,0,0]
    assert not report['eligible_for_review']


def test_lag_blocks_ranking_and_partial_revoke_preserves_prefix(tmp_path):
    p,j,f,clock,d,h,x,z,*_=setup(tmp_path)
    g,z=advance(d,h,x,z,f)
    before=x.view(z,g.fence,source_fence=f.fence)
    second=asyncio.run(d.step(g.fence,source_fence=f.fence))
    with pytest.raises(ValueError): x.rank(z,second.fence,(BASE,Selector(0,0,0)),source_fence=f.fence)
    z=x.sync(z,second.fence,source_fence=f.fence).fence
    both=x.view(z,second.fence,source_fence=f.fence)
    sig=R.sign(revoke_bytes(x.pin,2,both.entries[1].digest,'e'*64))
    q=x.revoke(z,second.fence,2,'e'*64,sig,source_fence=f.fence)
    after=x.view(q.fence,second.fence,source_fence=f.fence)
    assert after.entries==before.entries and after.statistics==before.statistics
    assert after.ridge==before.ridge and after.perceptron==before.perceptron
    assert after.trusted_active==before.trusted_active


def test_concurrent_sync_single_import(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    p,j,f,clock,d,h,x,z,*_=setup(tmp_path)
    g=asyncio.run(d.step(h,source_fence=f.fence))
    def sync():
        try: return x.sync(z,g.fence,source_fence=f.fence)
        except IntegrityError: return None
    with ThreadPoolExecutor(2) as pool: out=list(pool.map(lambda _:sync(),range(2)))
    winner=next(q for q in out if q is not None and q.status=='COMMITTED')
    assert sum(q is not None and q.status=='COMMITTED' for q in out)==1
    assert x.view(winner.fence,g.fence,source_fence=f.fence).imported==1
