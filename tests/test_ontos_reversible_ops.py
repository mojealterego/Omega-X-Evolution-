from dataclasses import replace
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor
import shutil

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from omega_x_evolution.ontos_reversible_ops import OperatorJournal, ExportLedger, Permit, permit_bytes
from omega_x_evolution.ontos_epoch_journal_core import IntegrityError
from omega_x_evolution.ontos_v72_jcs import canonical_json
from omega_x_evolution.ontos_otce import Scope
from test_ontos_otce import node, request, query, pub, W, R, U
from test_ontos_sealed_otce import command, put, KEK, VID

A=Ed25519PrivateKey.from_private_bytes(b'\x19'*32)


def setup(tmp):
    p=Scope('alpha','a'*64,1,2,pub(W),pub(R),pub(U))
    a,s,v,l,t=[tmp/x for x in ('anchor','segments','vault','ledger','receipts')]
    for d in (a,s,v,l,t): d.mkdir(mode=0o700)
    j=OperatorJournal(a/'floor.db',s,v/'keys.db',p,p.pin,KEK,vault_id=VID)
    ledger=ExportLedger(l/'floor.db',t,j,pub(A))
    return p,j,j.initialize(),ledger,ledger.initialize(),l,t


def revoke(p,j,f,i):
    g=j.append(f.fence,command(p,f,'revoke',{'id':i})); assert g.status=='COMMITTED'; return g


def test_r2_reconstruct_shard_after_revocation(tmp_path):
    p,j,f,*_=setup(tmp_path)
    f=put(p,j,f,node('a',value='Żółć kot'))
    f=put(p,j,f,node('b',value='Kot pies',parents=('a',),causal=1))
    f=put(p,j,f,node('c',value='pies las'))
    def index(f): return j.index(request(p,f,'r2'),retained=f.fence,now=6)
    assert dict(index(f).postings)=={'kot':('a','b'),'las':('c',),'pies':('b','c'),'żółć':('a',)}
    old=f; f=revoke(p,j,f,'a'); assert j.purge(f.fence,now=6)==2
    assert dict(index(f).postings)=={'las':('c',),'pies':('c',)}
    with pytest.raises(IntegrityError): j.index(request(p,old,'r2'),retained=f.fence,now=6)
    with pytest.raises(ValueError): j.index(request(p,f),retained=f.fence,now=6)
    with pytest.raises(ValueError): j.read(request(p,f,'r2'),retained=f.fence,now=6)


def test_r3_checkpoint_replay_and_revocation(tmp_path):
    p,j,f,*_=setup(tmp_path)
    f=put(p,j,f,node('a')); f=put(p,j,f,node('b'))
    f=put(p,j,f,dict(node('x',parents=('a',),causal=1,kind='R1'),payload={'x':[1,2],'y':1}))
    f=put(p,j,f,dict(node('y',parents=('b',),causal=1,kind='R1'),payload={'x':[2,1],'y':-1}))
    def model(f,cp=None): return j.model(request(p,f,'r3'),retained=f.fence,now=6,checkpoint=cp)
    first=model(f); assert first.checkpoint.weights==(-1,1)
    assert model(f,first.checkpoint).reused==2
    with pytest.raises(ValueError): model(f,replace(first.checkpoint,weights=(0,0)))
    f=revoke(p,j,f,'a'); j.purge(f.fence,now=6)
    rebuilt=model(f,first.checkpoint)
    assert rebuilt.reused==0 and rebuilt.checkpoint.weights==(-2,-1)
    assert rebuilt.checkpoint==model(f).checkpoint
    with pytest.raises(ValueError): j.model(request(p,f,'weights'),retained=f.fence,now=6)


def grant(j,ledger,f,r,*,nonce='d'*64,recipient='archive',digest=None,key=A):
    g=Permit(nonce,recipient,sha256(canonical_json('value')).hexdigest() if digest is None else digest,5,10,b'\0'*64)
    return replace(g,signature=key.sign(permit_bytes(ledger.pin,j,r,g)))


def test_r4_commit_before_release_and_replay(tmp_path):
    p,j,f,l,h,*_=setup(tmp_path); f=put(p,j,f,node('a'))
    r=request(p,f,'r4'); g=grant(j,l,f,r)
    result=j.export(l,h,r,g,retained=f.fence,now=6)
    assert result.payload==canonical_json('value') and result.status=='COMMITTED'
    with pytest.raises(IntegrityError): j.export(l,h,r,g,retained=f.fence,now=6)
    assert j.export(l,result.fence,r,g,retained=f.fence,now=6).payload is None
    assert l.read(result.fence)==(g.nonce,)


@pytest.mark.parametrize('alter',['role','recipient','digest','expired','operation','scope'])
def test_r4_rejects_unauthorized_export(tmp_path,alter):
    p,j,f,l,h,*_=setup(tmp_path); f=put(p,j,f,node('a'))
    r=request(p,f,'r4'); g=grant(j,l,f,r); now=6
    if alter=='role': g=grant(j,l,f,r,key=W)
    if alter=='recipient': g=replace(g,recipient='other')
    if alter=='digest': g=grant(j,l,f,r,digest='f'*64)
    if alter=='expired': now=10
    if alter=='operation': r=request(p,f,'recall'); g=grant(j,l,f,r)
    if alter=='scope': r=request(replace(p,tenant='beta'),f,'r4'); g=grant(j,l,f,r)
    with pytest.raises((ValueError,IntegrityError)): j.export(l,h,r,g,retained=f.fence,now=now)
    assert l.read(h)==()


def test_r4_concurrent_and_rollback(tmp_path):
    p,j,f,l,h,a,s=setup(tmp_path); f=put(p,j,f,node('a'))
    r=request(p,f,'r4'); g=grant(j,l,f,r)
    shutil.copy2(a/'floor.db',tmp_path/'old-a'); shutil.copy2(s/'segment-0000.db',tmp_path/'old-s')
    def export():
        try: return j.export(l,h,r,g,retained=f.fence,now=6)
        except IntegrityError: return None
    with ThreadPoolExecutor(2) as pool: results=list(pool.map(lambda _:export(),range(2)))
    winner=next(x for x in results if x is not None and x.payload is not None)
    assert sum(x is not None and x.payload is not None for x in results)==1
    shutil.copy2(tmp_path/'old-a',a/'floor.db'); shutil.copy2(tmp_path/'old-s',s/'segment-0000.db')
    with pytest.raises(IntegrityError): j.export(l,winner.fence,r,g,retained=f.fence,now=6)


def test_r4_uncertain_commit_is_spent_not_delivered(tmp_path,monkeypatch):
    from omega_x_evolution.ontos_managed_journal import ManagedJournal
    p,j,f,l,h,*_=setup(tmp_path); f=put(p,j,f,node('a'))
    r=request(p,f,'r4'); g=grant(j,l,f,r)
    def crash(*args): raise RuntimeError('injected interruption')
    with monkeypatch.context() as m:
        m.setattr(ManagedJournal,'_finish',crash)
        with pytest.raises(RuntimeError): j.export(l,h,r,g,retained=f.fence,now=6)
    with pytest.raises(IntegrityError): l.read(h)
    recovered=l.recover_from_anchor()
    assert l.read(recovered)==(g.nonce,)
    assert j.export(l,recovered,r,g,retained=f.fence,now=6).payload is None


def test_r4_reader_rotation_cannot_collapse_roles(tmp_path):
    p,j,f,l,h,*_=setup(tmp_path); f=put(p,j,f,node('a'))
    f=j.append(f.fence,command(p,f,'rotate',{'epoch':2,'reader':pub(A).hex()}))
    assert f.status=='COMMITTED'
    r=request(p,f,'r4',key=A,epoch=2); g=grant(j,l,f,r)
    with pytest.raises(ValueError,match='roles'): j.export(l,h,r,g,retained=f.fence,now=6)
    assert l.read(h)==()


def test_r4_revocation_precedes_release(tmp_path):
    p,j,f,l,h,*_=setup(tmp_path); f=put(p,j,f,node('a'))
    r=request(p,f,'r4'); g=grant(j,l,f,r)
    f=revoke(p,j,f,'a'); j.purge(f.fence,now=6)
    with pytest.raises(IntegrityError): j.export(l,h,r,g,retained=f.fence,now=6)
    r=request(p,f,'r4'); g=grant(j,l,f,r)
    with pytest.raises(ValueError,match='no active'): j.export(l,h,r,g,retained=f.fence,now=6)
    assert l.read(h)==()


def test_r3_checkpoint_scope_and_expiry(tmp_path):
    p,j,f,*_=setup(tmp_path)
    f=put(p,j,f,node('a',expires=10))
    f=put(p,j,f,node('b',kind='R1',parents=('a',),causal=1))
    r=request(p,f,'r3')
    cp=j.model(r,retained=f.fence,now=9).checkpoint
    with pytest.raises(ValueError): j.model(r,retained=f.fence,now=9,checkpoint=replace(cp,scope='f'*64))
    assert j.purge(f.fence,now=10)==2
    rebuilt=j.model(r,retained=f.fence,now=10,checkpoint=cp)
    assert rebuilt.reused==0 and rebuilt.checkpoint.weights==(0,0)


def test_r2_key_and_forecast_isolation(tmp_path):
    p,j,f,*_=setup(tmp_path)
    f=put(p,j,f,node('a',value='keep'))
    f=put(p,j,f,dict(node('b'),payload={'key':'other','value':'hidden'}))
    f=put(p,j,f,node('sim',branch='future',forecast=30,evidence='simulated',value='future'))
    assert dict(j.index(request(p,f,'r2'),retained=f.fence,now=6).postings)=={'keep':('a',)}
    with pytest.raises(ValueError): j.index(request(p,f,'r2',q=query(branch='future',forecast=30)),retained=f.fence,now=6)


def test_r3_verified_prefix_after_append(tmp_path):
    p,j,f,*_=setup(tmp_path)
    f=put(p,j,f,node('a')); f=put(p,j,f,node('x',parents=('a',),causal=1,kind='R1'))
    cp=j.model(request(p,f,'r3'),retained=f.fence,now=6).checkpoint
    f=put(p,j,f,dict(node('y',parents=('a',),causal=1,kind='R1'),payload={'x':[2,1],'y':-1}))
    r=request(p,f,'r3'); got=j.model(r,retained=f.fence,now=6,checkpoint=cp)
    assert got.reused==1 and got.checkpoint==j.model(r,retained=f.fence,now=6).checkpoint
