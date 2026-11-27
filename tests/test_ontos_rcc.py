from dataclasses import replace
from fractions import Fraction as F
import shutil
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from omega_x_evolution.ontos_rcc import Plan, Command, RCCJournal, Statistics, signing_bytes
from omega_x_evolution.ontos_v72_jcs import canonical_json
from omega_x_evolution.ontos_epoch_journal_core import IntegrityError

W=Ed25519PrivateKey.from_private_bytes(b'\x01'*32)
R=Ed25519PrivateKey.from_private_bytes(b'\x02'*32)


def setup(tmp_path):
    p=Plan('alpha','a'*64,1,2,W.public_key().public_bytes_raw(),R.public_key().public_bytes_raw())
    a=tmp_path/'anchor'; s=tmp_path/'segments'; a.mkdir(mode=0o700); s.mkdir(mode=0o700)
    j=RCCJournal(a/'floor.db',s,p,p.pin)
    return p,j,j.initialize(),a,s


def command(p,head,seq,kind,body,key=None):
    c=Command(head,seq,kind,canonical_json(body),b'\0'*64)
    return replace(c,signature=(key or (R if kind=='revoke' else W)).sign(signing_bytes(p,c)))


def atom(i,value='old',parents=(),start=0,evidence='observed'):
    return dict(id=i,key='k',value=value,start=start,end=100,source='b'*64,parents=list(parents),evidence=evidence)


def learn(i,parents,x,y):
    return dict(id=i,parents=list(parents),x=x,y=y)


def add(p,j,f,kind,body):
    c=command(p,f.head,f.count+1,kind,body)
    u=j.append(f.fence,c); assert u.status=='COMMITTED'
    return u


def test_signed_temporal_revocation_and_exact_ridge(tmp_path):
    p,j,f,a,s=setup(tmp_path)
    f=add(p,j,f,'atom',atom('a'))
    f=add(p,j,f,'atom',atom('b','new',start=20))
    f=add(p,j,f,'learn',learn('x',['a'],[1,2],3))
    f=add(p,j,f,'learn',learn('y',['b'],[2,1],4))
    assert j.recall(f.fence,'k',30,1)=='old'
    assert j.recall(f.fence,'k',30,4)=='new'
    old=f.fence
    f=add(p,j,f,'revoke',{'id':'b'})
    assert j.recall(f.fence,'k',30,4)=='old'
    expected=Statistics.zero(2).delta((1,2),3,1)
    assert j.statistics(f.fence)==expected
    assert j.weights(f.fence)==expected.ridge(1)
    with pytest.raises(IntegrityError): j.recall(old,'k',30,4)
    compact=j.compact(f.fence); assert compact.status=='COMPACTED'
    j=RCCJournal(a/'floor.db',s,p,p.pin)
    assert j.statistics(compact.fence)==expected
    assert j.recall(compact.fence,'k',30,4)=='old'


def test_diamond_and_reject_revoked_parent(tmp_path):
    p,j,f,_,_=setup(tmp_path)
    for i,parents in [('a',()),('b',('a',)),('c',('a',))]: f=add(p,j,f,'atom',atom(i,parents=parents))
    f=add(p,j,f,'learn',learn('d',['b','c'],[1,1],2))
    f=add(p,j,f,'revoke',{'id':'a'})
    assert j.statistics(f.fence)==Statistics.zero(2)
    assert j.recall(f.fence,'k',1,3) is None
    c=command(p,f.head,f.count+1,'learn',learn('e',['b'],[1,1],2))
    assert j.append(f.fence,c).status=='REJECTED'
    assert j.append(f.fence,command(p,f.head,f.count+1,'atom',atom('a'))).status=='REJECTED'


def test_scope_signature_role_and_replay(tmp_path):
    p,j,f,_,_=setup(tmp_path)
    for q in (replace(p,tenant='beta'),replace(p,encoder='c'*64),replace(p,epoch=2)):
        assert j.append(f.fence,command(q,f.head,1,'atom',atom('a'))).status=='REJECTED'
    assert j.append(f.fence,command(p,f.head,1,'atom',atom('a'),R)).status=='REJECTED'
    c=command(p,f.head,1,'atom',atom('a'))
    assert j.append(f.fence,replace(c,body=canonical_json(atom('b')))).status=='REJECTED'
    g=j.append(f.fence,c); assert g.status=='COMMITTED'
    assert j.append(f.fence,c).status=='STALE'
    assert j.append(g.fence,c).status=='REJECTED'
    assert j.append(g.fence,command(p,g.head,2,'revoke',{'id':'a'},W)).status=='REJECTED'


def test_concurrent_and_joint_rollback(tmp_path):
    p,j,f,a,s=setup(tmp_path)
    c=command(p,f.head,1,'atom',atom('a'))
    with ThreadPoolExecutor(2) as pool: out=list(pool.map(lambda _:j.append(f.fence,c),range(2)))
    assert sorted(x.status for x in out)==['COMMITTED','STALE']
    f=next(x for x in out if x.status=='COMMITTED')
    shutil.copy2(a/'floor.db',tmp_path/'a'); shutil.copy2(s/'segment-0000.db',tmp_path/'s')
    g=add(p,j,f,'revoke',{'id':'a'})
    shutil.copy2(tmp_path/'a',a/'floor.db'); shutil.copy2(tmp_path/'s',s/'segment-0000.db')
    with pytest.raises(IntegrityError): j.recall(g.fence,'k',1,1)


@pytest.mark.parametrize('body',[atom('a',parents=('missing',)),atom('a',start=100),atom('a',parents=('a','a')),dict(atom('a'),extra=True)])
def test_invalid_atom(tmp_path,body):
    p,j,f,_,_=setup(tmp_path)
    assert j.append(f.fence,command(p,f.head,1,'atom',body)).status=='REJECTED'


def test_exact_downdate_matches_rebuild():
    from random import Random
    rng=Random(44)
    for _ in range(30):
        rows=[(tuple(rng.randint(-4,4) for _ in range(3)),rng.randint(-4,4)) for _ in range(12)]
        all_=Statistics.zero(3); kept=Statistics.zero(3)
        for i,(x,y) in enumerate(rows):
            all_=all_.delta(x,y,1)
            if i%3: kept=kept.delta(x,y,1)
        for x,y in rows[::3]: all_=all_.delta(x,y,-1)
        assert all_==kept and all_.ridge(2)==kept.ridge(2)


def test_reserve_revocation_capacity(tmp_path,monkeypatch):
    import omega_x_evolution.ontos_rcc as rcc
    monkeypatch.setattr(rcc,'MAX_EVENTS',4)
    monkeypatch.setattr(rcc,'MAX_NODES',2)
    p,j,f,_,_=setup(tmp_path)
    f=add(p,j,f,'atom',atom('a'))
    f=add(p,j,f,'atom',atom('b'))
    assert j.append(f.fence,command(p,f.head,3,'atom',atom('c'))).status=='REJECTED'
    f=add(p,j,f,'revoke',{'id':'a'})
    f=add(p,j,f,'revoke',{'id':'b'})
    assert f.count==4 and j.recall(f.fence,'k',1,4) is None


def test_pin_and_unknown_class(tmp_path):
    p,j,f,a,s=setup(tmp_path)
    with pytest.raises(ValueError): RCCJournal(a/'floor.db',s,replace(p,epoch=2),p.pin)
    with pytest.raises(ValueError): j.statistics(None)
    with pytest.raises(ValueError): command(p,f.head,1,'R3',{})
    c=command(p,f.head,1,'atom',atom('a'))
    result=j.append(f.fence,c)
    assert not hasattr(result,'state')
    assert j.append(f.fence,c).fence is None


def test_prepared_intent_recovery(tmp_path,monkeypatch):
    from omega_x_evolution.ontos_managed_journal import ManagedJournal
    p,j,f,a,s=setup(tmp_path)
    f=add(p,j,f,'atom',atom('a'))
    c=command(p,f.head,2,'revoke',{'id':'a'})
    def crash(*args): raise RuntimeError('injected crash')
    with monkeypatch.context() as m:
        m.setattr(ManagedJournal,'_finish',crash)
        with pytest.raises(RuntimeError): j.append(f.fence,c)
    j=RCCJournal(a/'floor.db',s,p,p.pin)
    with pytest.raises(IntegrityError): j.recall(f.fence,'k',1,1)
    # Recovery of an interrupted update requires explicit operator trust in the anchor.
    recovered=j.recover_from_anchor()
    assert recovered.count==2 and j.recall(recovered.fence,'k',1,1) is None


def test_nonobserved_lineage_never_enters_active_r1_or_fact_view(tmp_path):
    p,j,f,_,_=setup(tmp_path)
    f=add(p,j,f,'atom',atom('a','observed'))
    f=add(p,j,f,'atom',atom('b','forecast',evidence='simulated'))
    f=add(p,j,f,'atom',atom('c','hypothesis',parents=('b',),evidence='inferred'))
    assert j.recall(f.fence,'k',1,3)=='observed'
    for kind,body in [('atom',atom('d',parents=('c',))),('atom',atom('e',evidence='verified')),
                      ('learn',learn('f',['c'],[1,2],3)),('learn',learn('g',['b'],[1,2],3))]:
        assert j.append(f.fence,command(p,f.head,f.count+1,kind,body)).status=='REJECTED'
    assert j.statistics(f.fence)==Statistics.zero(2)
