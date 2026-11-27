from dataclasses import replace
import shutil

import pytest
from omega_x_evolution.ontos_sealed_otce import SealedOTCEJournal, sealed_event_bytes
from omega_x_evolution.ontos_otce import Scope, OTCEJournal, Event
from omega_x_evolution.ontos_epoch_journal_core import IntegrityError
from test_ontos_otce import node, event, request, query, pub, W, R, U, V
from omega_x_evolution.ontos_managed_journal import ManagedJournal
from omega_x_evolution.ontos_v72_jcs import canonical_json
import sqlite3

KEK=b'K'*32
NEW=b'N'*32
VID='c'*64


def setup(tmp_path):
    p=Scope('alpha','a'*64,1,2,pub(W),pub(R),pub(U))
    a,s,v=(tmp_path/x for x in ('anchor','segments','vault'))
    for d in (a,s,v): d.mkdir(mode=0o700)
    j=SealedOTCEJournal(a/'floor.db',s,v/'keys.db',p,p.pin,KEK,vault_id=VID)
    return p,j,j.initialize(),a,s,v


def command(p,f,kind,body,*,vault_id=VID):
    e=Event(f.head,f.count+1,kind,canonical_json(body),b'\0'*64)
    return replace(e,signature=R.sign(sealed_event_bytes(p,vault_id,e)))


def put(p,j,f,b):
    u=j.put(f.fence,b,W.sign)
    assert u.status=='COMMITTED'
    return u


def read(p,j,f,op='recall',**kw):
    now=kw.pop('now',6)
    return j.read(request(p,f,op,**kw),retained=f.fence,now=now)


def test_ciphertext_only_and_reopen(tmp_path):
    p,j,f,a,s,v=setup(tmp_path)
    secret='unique-private-payload-21f6a7'
    f=put(p,j,f,node('a',value=secret))
    f=put(p,j,f,node('b',parents=('a',),causal=1,kind='R1'))
    for d in (a,s,v):
        for file in d.iterdir():
            if file.is_file():
                raw=file.read_bytes()
                assert secret.encode() not in raw and secret.encode().hex().encode() not in raw
                assert KEK not in raw
    j=SealedOTCEJournal(a/'floor.db',s,v/'keys.db',p,p.pin,KEK,vault_id=VID)
    assert read(p,j,f)==secret
    assert read(p,j,f,'weights')==(0.5,1)
    assert len(read(p,j,f,'explain'))==2
    with pytest.raises((IntegrityError,ValueError)):
        OTCEJournal(a/'floor.db',s,p,p.pin).recover_from_anchor()


def test_revoke_cascade_purge_and_restart(tmp_path):
    p,j,f,a,s,v=setup(tmp_path)
    f=put(p,j,f,node('a',value='secret'))
    f=put(p,j,f,node('b',parents=('a',),causal=1,kind='R1'))
    f=put(p,j,f,node('c',value='kept'))
    old=f
    f=j.append(f.fence,command(p,f,'revoke',{'id':'a'}))
    assert f.status=='COMMITTED'
    assert read(p,j,f)=='kept' and read(p,j,f,'weights')==(0,0)
    assert j.purge(f.fence,now=6)==2
    assert j.purge(f.fence,now=6)==0
    f=j.compact(f.fence)
    j=SealedOTCEJournal(a/'floor.db',s,v/'keys.db',p,p.pin,KEK,vault_id=VID)
    assert read(p,j,f)=='kept'
    assert read(p,j,f,'weights')==(0,0)
    with pytest.raises(IntegrityError): read(p,j,old)


def test_wrong_kek_and_atomic_rewrap(tmp_path):
    p,j,f,a,s,v=setup(tmp_path)
    f=put(p,j,f,node('a'))
    with pytest.raises(IntegrityError): read(p,SealedOTCEJournal(a/'floor.db',s,v/'keys.db',p,p.pin,NEW,vault_id=VID),f)
    assert j.rewrap(f.fence,NEW)==1
    with pytest.raises(IntegrityError): read(p,SealedOTCEJournal(a/'floor.db',s,v/'keys.db',p,p.pin,KEK,vault_id=VID),f)
    assert read(p,SealedOTCEJournal(a/'floor.db',s,v/'keys.db',p,p.pin,NEW,vault_id=VID),f)=='value'


def test_expiry_purge_ancestry(tmp_path):
    p,j,f,*_=setup(tmp_path)
    f=put(p,j,f,node('a',expires=10))
    f=put(p,j,f,node('b',parents=('a',),causal=1,kind='R1'))
    assert read(p,j,f,'weights',now=9)==(0.5,1)
    assert j.purge(f.fence,now=10)==2
    assert read(p,j,f,'weights',now=10)==(0,0)
    with pytest.raises(IntegrityError): read(p,j,f,now=9)


def test_bad_signature_and_plaintext_bypass(tmp_path):
    p,j,f,*_=setup(tmp_path)
    with pytest.raises(ValueError): j.append(f.fence,event(p,f,'put',node('a')))
    assert j.put(f.fence,node('a'),R.sign).status=='REJECTED'
    assert j.purge(f.fence,now=6)==0
    f=put(p,j,f,node('a'))
    with pytest.raises(ValueError): j.read(request(p,f,key=R),retained=f.fence,now=6)
    assert read(p,j,f)=='value'


def test_vault_backup_cannot_reactivate_revoked_read(tmp_path):
    p,j,f,a,s,v=setup(tmp_path)
    f=put(p,j,f,node('a'))
    shutil.copy2(v/'keys.db',tmp_path/'vault-backup')
    old=f
    f=j.append(f.fence,command(p,f,'revoke',{'id':'a'}))
    assert j.purge(f.fence,now=6)==1
    shutil.copy2(tmp_path/'vault-backup',v/'keys.db')
    assert read(p,j,f) is None
    with pytest.raises(IntegrityError): read(p,j,old)
    assert j.purge(f.fence,now=6)==1


def test_wrong_vault_identity_and_scope(tmp_path):
    p,j,f,a,s,v=setup(tmp_path)
    f=put(p,j,f,node('a'))
    other=SealedOTCEJournal(a/'floor.db',s,v/'keys.db',p,p.pin,KEK,vault_id='d'*64)
    with pytest.raises(IntegrityError): read(p,other,f)
    other_scope=Scope('beta',p.encoder,1,2,p.writer,p.revoker,p.reader)
    other=SealedOTCEJournal(a/'floor.db',s,v/'keys.db',other_scope,other_scope.pin,KEK,vault_id=VID)
    with pytest.raises(IntegrityError): other.recover_from_anchor()


def test_swapped_wrapped_keys_and_rewrap_rollback(tmp_path):
    p,j,f,a,s,v=setup(tmp_path)
    f=put(p,j,f,node('a'))
    f=put(p,j,f,node('b',value='second'))
    with sqlite3.connect(v/'keys.db') as db:
        rows=db.execute('SELECT kid,wrapped FROM keys ORDER BY kid').fetchall()
        db.execute('UPDATE keys SET wrapped=? WHERE kid=?',(rows[0][1],rows[1][0]))
    with pytest.raises(IntegrityError): j.rewrap(f.fence,NEW)
    with sqlite3.connect(v/'keys.db') as db:
        assert db.execute('SELECT kid,wrapped FROM keys ORDER BY kid').fetchall()==[rows[0],(rows[1][0],rows[0][1])]
        db.execute('UPDATE keys SET wrapped=? WHERE kid=?',(rows[1][1],rows[1][0]))
    assert read(p,j,f)=='second'


def test_aad_and_ciphertext_authentication(tmp_path):
    p,j,f,*_=setup(tmp_path)
    f=put(p,j,f,node('a',value='secret'))
    snap=j._journal.read(f.fence)
    n=j._reduce(snap.state)[0]['a']
    with j._vault() as db:
        assert j._decrypt(db,n)['value']=='secret'
        for modified in (dict(n,id='b'),dict(n,source='f'*64),dict(n,payload=dict(n['payload'],key='other')),
                         dict(n,payload=dict(n['payload'],ciphertext=('1' if n['payload']['ciphertext'][0]=='0' else '0')+n['payload']['ciphertext'][1:]))):
            with pytest.raises(IntegrityError): j._decrypt(db,modified)


def test_interrupted_put_recovery_keeps_key(tmp_path,monkeypatch):
    p,j,f,a,s,v=setup(tmp_path)
    def crash(*args): raise RuntimeError('injected crash')
    with monkeypatch.context() as m:
        m.setattr(ManagedJournal,'_finish',crash)
        with pytest.raises(RuntimeError): j.put(f.fence,node('a'),W.sign)
    j=SealedOTCEJournal(a/'floor.db',s,v/'keys.db',p,p.pin,KEK,vault_id=VID)
    with pytest.raises(IntegrityError): j.purge(f.fence,now=6)
    g=j.recover_from_anchor()
    assert g.count==1 and read(p,j,g)=='value'
    assert j.purge(g.fence,now=6)==0


def test_orphan_key_reconciled_after_failed_append(tmp_path,monkeypatch):
    p,j,f,*_=setup(tmp_path)
    def crash(*args): raise RuntimeError('pre-append crash')
    with monkeypatch.context() as m:
        m.setattr(ManagedJournal,'append',crash)
        with pytest.raises(RuntimeError): j.put(f.fence,node('a'),W.sign)
    assert j.purge(f.fence,now=6)==1
    assert read(p,j,f) is None


def test_migrate_keeps_encryption_and_purge(tmp_path):
    p,j,f,*_=setup(tmp_path)
    f=put(p,j,f,node('a'))
    f=j.append(f.fence,command(p,f,'migrate',dict(epoch=2,reader=pub(V).hex(),encoder=p.encoder,evolution=2)))
    assert f.status=='COMMITTED'
    assert read(p,j,f,q=query(evolution=2),key=V,epoch=2)=='value'
    assert j.purge(f.fence,now=6)==0
    with pytest.raises(ValueError): read(p,j,f)


@pytest.mark.parametrize('payload',[{'key':'k','value':'x'*513},{'key':'k','value':True},{'key':'k','value':'ż'*300}])
def test_plaintext_budget_and_type(tmp_path,payload):
    p,j,f,*_=setup(tmp_path)
    with pytest.raises(ValueError): j.put(f.fence,dict(node('a'),payload=payload),W.sign)
    assert j.purge(f.fence,now=6)==0


def test_plain_scope_rotation_cannot_cross_into_sealed_genesis(tmp_path):
    p,j,f,*_=setup(tmp_path)
    e=event(p,f,'rotate',dict(epoch=2,reader=pub(V).hex()))
    assert j.append(f.fence,e).status=='REJECTED'
    assert j.append(f.fence,command(p,f,'rotate',dict(epoch=2,reader=pub(V).hex()),vault_id='d'*64)).status=='REJECTED'
    assert j.append(f.fence,command(p,f,'rotate',dict(epoch=2,reader=pub(V).hex()))).status=='COMMITTED'


def test_concurrent_purge_never_destroys_committed_key(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    p,j,f,*_=setup(tmp_path)
    def purge():
        try: return j.purge(f.fence,now=6)
        except IntegrityError: return 'STALE'
    with ThreadPoolExecutor(2) as pool:
        a=pool.submit(put,p,j,f,node('a'))
        b=pool.submit(purge)
        g=a.result(); assert b.result() in (0,'STALE')
    assert read(p,j,g)=='value'
