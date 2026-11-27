from dataclasses import replace
from fractions import Fraction
from concurrent.futures import ThreadPoolExecutor
import shutil

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_ontos_otce import setup, node, event, add, query, request, pub, W, U, V
from omega_x_evolution.ontos_otce import OTCEJournal
from omega_x_evolution.ontos_epoch_journal_core import IntegrityError


def transition(p, f, *, evolution=2, epoch=2, reader=V, key=None, **changes):
    body = dict(evolution=evolution, epoch=epoch, reader=pub(reader).hex(), encoder=p.encoder) | changes
    return event(p, f, 'migrate', body, key)


def migrate(p, j, f, **kw):
    result = j.append(f.fence, transition(p, f, **kw))
    assert result.status == 'COMMITTED'
    return result


def test_migration_preserves_commitments_and_revocation(tmp_path):
    p,j,f,a,s=setup(tmp_path)
    f=add(p,j,f,'put',node('old',value='surviving'))
    f=add(p,j,f,'put',node('sample',parents=('old',),causal=1,kind='R1'))
    f=add(p,j,f,'put',node('removed',value='secret'))
    f=add(p,j,f,'put',node('dependent',parents=('removed',),causal=1,kind='R1'))
    f=add(p,j,f,'revoke',{'id':'removed'})
    before=j.read(request(p,f,'explain'),retained=f.fence,now=6)
    old=request(p,f)
    f=migrate(p,j,f)
    q=query(evolution=2)
    assert j.read(request(p,f,q=q,key=V,epoch=2),retained=f.fence,now=6)=='surviving'
    assert j.read(request(p,f,'weights',q=q,key=V,epoch=2),retained=f.fence,now=6)==(Fraction(1,2),Fraction(1))
    after=j.read(request(p,f,'explain',q=q,key=V,epoch=2),retained=f.fence,now=6)
    assert [n['id'] for n in after]==['old','sample']
    assert [n['output'] for n in before]==[n['output'] for n in after]
    assert all(n['time']['evolution']==1 and n['view_evolution']==2 for n in after)
    assert j.read(request(p,f,q=query(evolution=2,known=5),key=V,epoch=2),retained=f.fence,now=6) is None
    assert j.read(request(p,f,key=V,epoch=2),retained=f.fence,now=6) is None
    with pytest.raises(IntegrityError): j.read(old,retained=f.fence,now=6)
    with pytest.raises(ValueError): j.read(request(p,f,q=q,key=U,epoch=2),retained=f.fence,now=6)
    new=node('new',parents=('old',),causal=1,value='new epoch');new['time']['evolution']=2
    f=add(p,j,f,'put',new)
    assert j.read(request(p,f,q=q,key=V,epoch=2),retained=f.fence,now=6)=='new epoch'
    f=add(p,j,f,'revoke',{'id':'old'})
    f=j.compact(f.fence); assert f.status=='COMPACTED'
    j=OTCEJournal(a/'floor.db',s,p,p.pin)
    assert j.read(request(p,f,q=q,key=V,epoch=2),retained=f.fence,now=6) is None
    assert j.read(request(p,f,'weights',q=q,key=V,epoch=2),retained=f.fence,now=6)==(0,0)


@pytest.mark.parametrize('changes',[{'evolution':1},{'evolution':3},{'epoch':3},{'encoder':'f'*64},{'reader':U},{'key':W}])
def test_bad_transition_rejected(tmp_path,changes):
    p,j,f,*_=setup(tmp_path)
    assert j.append(f.fence,transition(p,f,**changes)).status=='REJECTED'


def test_migration_preserves_expiry_and_forecast(tmp_path):
    p,j,f,*_=setup(tmp_path)
    f=add(p,j,f,'put',node('a',expires=10))
    f=add(p,j,f,'put',node('b',parents=('a',),causal=1,branch='future',forecast=30,evidence='simulated'))
    f=migrate(p,j,f)
    q=query(evolution=2,branch='future',forecast=30)
    assert j.read(request(p,f,q=q,key=V,epoch=2),retained=f.fence,now=9)=='value'
    assert j.read(request(p,f,q=q,key=V,epoch=2),retained=f.fence,now=10) is None
    assert j.read(request(p,f,q=query(evolution=2,branch='future',forecast=31),key=V,epoch=2),retained=f.fence,now=9) is None
    assert j.append(f.fence,event(p,f,'put',node('stale'))).status=='REJECTED'


def test_migration_cas_and_joint_rollback(tmp_path):
    p,j,f,a,s=setup(tmp_path)
    f=add(p,j,f,'put',node('a'))
    old=request(p,f)
    shutil.copy2(a/'floor.db',tmp_path/'old-a');shutil.copy2(s/'segment-0000.db',tmp_path/'old-s')
    e=transition(p,f)
    with ThreadPoolExecutor(2) as pool: out=list(pool.map(lambda _:j.append(f.fence,e),range(2)))
    assert sorted(x.status for x in out)==['COMMITTED','STALE']
    g=next(x for x in out if x.status=='COMMITTED')
    shutil.copy2(tmp_path/'old-a',a/'floor.db');shutil.copy2(tmp_path/'old-s',s/'segment-0000.db')
    with pytest.raises(IntegrityError):j.read(old,retained=g.fence,now=6)
    with pytest.raises(IntegrityError):j.read(request(p,g,q=query(evolution=2),key=V,epoch=2),retained=g.fence,now=6)


def test_migration_shares_rotation_budget(tmp_path,monkeypatch):
    import omega_x_evolution.ontos_otce as otce
    monkeypatch.setattr(otce,'MAX_NODES',2);monkeypatch.setattr(otce,'MAX_ROTATIONS',1);monkeypatch.setattr(otce,'MAX_EVENTS',5)
    p,j,f,*_=setup(tmp_path)
    f=add(p,j,f,'put',node('a'));f=add(p,j,f,'put',node('b'))
    f=migrate(p,j,f)
    assert j.append(f.fence,transition(p,f,evolution=3,epoch=3)).status=='REJECTED'
    f=add(p,j,f,'revoke',{'id':'a'});f=add(p,j,f,'revoke',{'id':'b'})
    assert f.count==5


def test_second_migration_retired_key_and_origin(tmp_path):
    p,j,f,*_=setup(tmp_path)
    f=add(p,j,f,'put',node('a'))
    f=migrate(p,j,f)
    new=node('b',parents=('a',),causal=1);new['time']['evolution']=2
    f=add(p,j,f,'put',new)
    assert j.append(f.fence,transition(p,f,evolution=3,epoch=3,reader=U)).status=='REJECTED'
    next_reader=Ed25519PrivateKey.from_private_bytes(b'\x17'*32)
    f=migrate(p,j,f,evolution=3,epoch=3,reader=next_reader)
    result=j.read(request(p,f,'explain',q=query(evolution=3),key=next_reader,epoch=3),retained=f.fence,now=6)
    assert [(n['time']['evolution'],n['view_evolution']) for n in result]==[(1,3),(2,3)]
    assert j.read(request(p,f,q=query(evolution=3,known=3),key=next_reader,epoch=3),retained=f.fence,now=6) is None


def test_interrupted_migration_recovery(tmp_path,monkeypatch):
    from omega_x_evolution.ontos_managed_journal import ManagedJournal
    p,j,f,a,s=setup(tmp_path)
    f=add(p,j,f,'put',node('a'))
    old=request(p,f)
    def crash(*args): raise RuntimeError('injected crash')
    with monkeypatch.context() as m:
        m.setattr(ManagedJournal,'_finish',crash)
        with pytest.raises(RuntimeError):j.append(f.fence,transition(p,f))
    j=OTCEJournal(a/'floor.db',s,p,p.pin)
    with pytest.raises(IntegrityError):j.read(old,retained=f.fence,now=6)
    recovered=j.recover_from_anchor()
    assert recovered.count==2
    assert j.read(request(p,recovered,q=query(evolution=2),key=V,epoch=2),retained=recovered.fence,now=6)=='value'
