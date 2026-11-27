from dataclasses import replace
from fractions import Fraction
from concurrent.futures import ThreadPoolExecutor
import shutil

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from omega_x_evolution.ontos_otce import (Scope, Event, Read, Query, OTCEJournal,
    event_bytes, read_bytes, Coordinates)
from omega_x_evolution.ontos_v72_jcs import canonical_json
from omega_x_evolution.ontos_epoch_journal_core import IntegrityError

W,R,U,V=[Ed25519PrivateKey.from_private_bytes(bytes([i])*32) for i in range(1,5)]
def pub(k): return k.public_key().public_bytes_raw()

def setup(tmp_path):
    p=Scope('alpha','a'*64,1,2,pub(W),pub(R),pub(U))
    a=tmp_path/'anchor'; s=tmp_path/'segments'; a.mkdir(mode=0o700); s.mkdir(mode=0o700)
    j=OTCEJournal(a/'floor.db',s,p,p.pin)
    return p,j,j.initialize(),a,s

def node(i, *, parents=(), value='value', cognitive=2, causal=0, observed=1,
         expires=100, branch='actual', forecast=None, evidence='observed', kind='R0', start=0):
    return dict(id=i,parents=list(parents),kind=kind,evidence=evidence,branch=branch,
        time=dict(start=start,end=90,cognitive=cognitive,causal=causal,observed=observed,
                  forecast=forecast,evolution=1,expires=expires),source='b'*64,
        payload=dict(key='k',value=value) if kind=='R0' else dict(x=[1,2],y=3))

def event(p,f,kind,body,key=None):
    e=Event(f.head,f.count+1,kind,canonical_json(body),b'\0'*64)
    return replace(e,signature=(key or (W if kind=='put' else R)).sign(event_bytes(p,e)))

def add(p,j,f,kind,body):
    g=j.append(f.fence,event(p,f,kind,body)); assert g.status=='COMMITTED'; return g

def query(**kw):
    return Query(**(dict(branch='actual',valid=10,known=40,cognitive=99,causal=99,observed=99,evolution=1,forecast=None)|kw))

def request(p,f,op='recall',q=None,key=U,epoch=1,issued=5,expires=20):
    r=Read(f.fence,epoch,op,'k',q or query(),issued,expires,b'\0'*64)
    return replace(r,signature=key.sign(read_bytes(p,r)))

def test_axes_and_correction(tmp_path):
    p,j,f,*_=setup(tmp_path)
    f=add(p,j,f,'put',node('a',value='old'))
    f=add(p,j,f,'put',node('b',value='new',parents=('a',),cognitive=4,causal=1,observed=3,start=5))
    for q in (query(known=1),query(cognitive=3),query(causal=0),query(observed=2),query(valid=1)):
        assert j.read(request(p,f,q=q),retained=f.fence,now=6)=='old'
    assert j.read(request(p,f),retained=f.fence,now=6)=='new'
    assert j.read(request(p,f,q=query(evolution=2)),retained=f.fence,now=6) is None
    assert j.read(request(p,f,q=query(valid=90)),retained=f.fence,now=6) is None

def test_forecast_isolated_and_lineage(tmp_path):
    p,j,f,*_=setup(tmp_path)
    f=add(p,j,f,'put',node('a'))
    f=add(p,j,f,'put',node('sim',branch='future',forecast=30,evidence='simulated',value='forecast'))
    assert j.read(request(p,f),retained=f.fence,now=6)=='value'
    assert j.read(request(p,f,q=query(branch='future',forecast=30)),retained=f.fence,now=6)=='forecast'
    assert j.read(request(p,f,q=query(branch='future',forecast=31)),retained=f.fence,now=6) is None
    for b in (node('x',parents=('sim',),causal=1),node('x',parents=('sim',),causal=1,kind='R1')):
        assert j.append(f.fence,event(p,f,'put',b)).status=='REJECTED'

def test_retention_applies_to_ancestors_and_weights(tmp_path):
    p,j,f,*_=setup(tmp_path)
    f=add(p,j,f,'put',node('a',expires=10))
    f=add(p,j,f,'put',node('b',parents=('a',),causal=1,kind='R1'))
    assert j.read(request(p,f,'weights'),retained=f.fence,now=9)==(Fraction(1,2),Fraction(1,1))
    assert j.read(request(p,f,'weights'),retained=f.fence,now=10)==(Fraction(0),Fraction(0))
    assert j.read(request(p,f),retained=f.fence,now=10) is None
    info=j.read(request(p,f,'explain'),retained=f.fence,now=9)
    assert len(info)==2 and info[1]['parents']==['a'] and len(info[1]['output'])==64
    assert j.read(request(p,f,'explain'),retained=f.fence,now=10)==[]

def test_policy_rotation_scope_and_expiry(tmp_path):
    p,j,f,*_=setup(tmp_path)
    f=add(p,j,f,'put',node('a'))
    old=request(p,f)
    for r in (replace(old,operation='explain'),replace(old,epoch=2),request(p,f,key=R),request(replace(p,tenant='beta'),f)):
        with pytest.raises(ValueError): j.read(r,retained=f.fence,now=6)
    with pytest.raises(ValueError): j.read(old,retained=f.fence,now=20)
    f=add(p,j,f,'rotate',{'epoch':2,'reader':pub(V).hex()})
    with pytest.raises(IntegrityError): j.read(old,retained=f.fence,now=6)
    with pytest.raises(ValueError): j.read(request(p,f),retained=f.fence,now=6)
    with pytest.raises(ValueError): j.read(request(p,f,key=U,epoch=2),retained=f.fence,now=6)
    assert j.read(request(p,f,key=V,epoch=2),retained=f.fence,now=6)=='value'
    assert j.append(f.fence,event(p,f,'rotate',{'epoch':3,'reader':pub(U).hex()})).status=='REJECTED'

def test_revoke_cascade_compaction_and_rollback(tmp_path):
    p,j,f,a,s=setup(tmp_path)
    f=add(p,j,f,'put',node('a'))
    f=add(p,j,f,'put',node('b',parents=('a',),causal=1,kind='R1'))
    old=request(p,f)
    shutil.copy2(a/'floor.db',tmp_path/'old-a');shutil.copy2(s/'segment-0000.db',tmp_path/'old-s')
    f=add(p,j,f,'revoke',{'id':'a'})
    f=j.compact(f.fence); assert f.status=='COMPACTED'
    j=OTCEJournal(a/'floor.db',s,p,p.pin)
    assert j.read(request(p,f,q=query(known=1)),retained=f.fence,now=6) is None
    assert j.read(request(p,f,'weights'),retained=f.fence,now=6)==(Fraction(0),Fraction(0))
    shutil.copy2(tmp_path/'old-a',a/'floor.db');shutil.copy2(tmp_path/'old-s',s/'segment-0000.db')
    with pytest.raises(IntegrityError): j.read(request(p,f),retained=f.fence,now=6)
    with pytest.raises(IntegrityError): j.read(old,retained=f.fence,now=6)

@pytest.mark.parametrize('changes',[{'causal':1},{'evolution':2},{'cognitive':True},{'expires':0},{'forecast':30},{'start':90}])
def test_invalid_axes(tmp_path,changes):
    p,j,f,*_=setup(tmp_path)
    b=node('a');b['time'].update(changes)
    assert j.append(f.fence,event(p,f,'put',b)).status=='REJECTED'

@pytest.mark.parametrize('kind',['R2','R3','R4'])
def test_unsupported_operator_rejected(tmp_path,kind):
    p,j,f,*_=setup(tmp_path)
    assert j.append(f.fence,event(p,f,'put',node('a',kind=kind))).status=='REJECTED'

def test_concurrent_CAS(tmp_path):
    p,j,f,*_=setup(tmp_path); e=event(p,f,'put',node('a'))
    with ThreadPoolExecutor(2) as pool: out=list(pool.map(lambda _:j.append(f.fence,e),range(2)))
    assert sorted(x.status for x in out)==['COMMITTED','STALE']


def test_independent_fence_required(tmp_path):
    p,j,f,*_=setup(tmp_path)
    r=request(p,f)
    with pytest.raises(ValueError): j.read(r,retained=None,now=6)
    with pytest.raises(TypeError): j.read(r,now=6)


def test_revocation_reserve_with_rotation(tmp_path):
    p,j,f,*_=setup(tmp_path)
    # Reduced test bounds exercise the production admission and capacity logic.
    import omega_x_evolution.ontos_otce as otce
    from unittest.mock import patch
    with patch.object(otce,'MAX_NODES',2),patch.object(otce,'MAX_ROTATIONS',1),patch.object(otce,'MAX_EVENTS',5):
        f=add(p,j,f,'put',node('a'))
        f=add(p,j,f,'put',node('b'))
        assert j.append(f.fence,event(p,f,'put',node('c'))).status=='REJECTED'
        f=add(p,j,f,'rotate',{'epoch':2,'reader':pub(V).hex()})
        assert j.append(f.fence,event(p,f,'rotate',{'epoch':3,'reader':'f'*64})).status=='REJECTED'
        f=add(p,j,f,'revoke',{'id':'a'})
        f=add(p,j,f,'revoke',{'id':'b'})
        assert f.count==5
        assert j.read(request(p,f,q=query(known=5),key=V,epoch=2),retained=f.fence,now=6) is None


def test_full_admission_and_revoke_budget(tmp_path):
    p,j,f,a,s=setup(tmp_path)
    for i in range(16): f=add(p,j,f,'put',node(f'n{i}'))
    assert j.append(f.fence,event(p,f,'put',node('overflow'))).status=='REJECTED'
    for epoch in range(2,10):
        reader=Ed25519PrivateKey.from_private_bytes(bytes([epoch+10])*32)
        f=add(p,j,f,'rotate',{'epoch':epoch,'reader':pub(reader).hex()})
    for i in range(16): f=add(p,j,f,'revoke',{'id':f'n{i}'})
    assert f.count==40
    f=j.compact(f.fence)
    j=OTCEJournal(a/'floor.db',s,p,p.pin)
    assert j.read(request(p,f,key=reader,epoch=9),retained=f.fence,now=6) is None
    assert j.read(request(p,f,'explain',key=reader,epoch=9),retained=f.fence,now=6)==[]


def test_read_query_and_time_tamper(tmp_path):
    p,j,f,*_=setup(tmp_path)
    f=add(p,j,f,'put',node('a',observed=8))
    r=request(p,f)
    assert j.read(r,retained=f.fence,now=6) is None
    assert j.read(r,retained=f.fence,now=8)=='value'
    for invalid in (replace(r,key='other'),replace(r,query=query(valid=1)),replace(r,expires=21)):
        with pytest.raises(ValueError): j.read(invalid,retained=f.fence,now=8)
    with pytest.raises(ValueError): j.read(r,retained=f.fence,now=4)
    assert j.append(f.fence,event(replace(p,tenant='beta'),f,'put',node('b'))).status=='REJECTED'
    assert j.append(f.fence,event(p,f,'rotate',{'epoch':2,'reader':pub(V).hex()},W)).status=='REJECTED'


def test_replay_verification_cache_exact_and_cold_restart(tmp_path,monkeypatch):
    import omega_x_evolution.ontos_otce as otce
    calls=[]
    verify=otce.strict_verify
    def counted(key,message,signature):
        calls.append((key,message,signature))
        return verify(key,message,signature)
    monkeypatch.setattr(otce,'strict_verify',counted)
    p,j,f,a,s=setup(tmp_path)
    first=event(p,f,'put',node('a'))
    f=j.append(f.fence,first);assert f.status=='COMMITTED'
    second=event(p,f,'put',node('b'))
    f=j.append(f.fence,second);assert f.status=='COMMITTED'
    assert len(calls)==2
    bad=event(p,f,'put',node('c'))
    bad=replace(bad,signature=second.signature)
    assert j.append(f.fence,bad).status=='REJECTED'
    assert len(calls)==3
    j=OTCEJournal(a/'floor.db',s,p,p.pin)
    calls.clear()
    r=request(p,f)
    assert j.read(r,retained=f.fence,now=6)=='value'
    assert len(calls)==3  # both events and the read token
    assert j.read(r,retained=f.fence,now=6)=='value'
    assert len(calls)==4  # read authorization is never memoized
