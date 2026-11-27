from dataclasses import replace
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from omega_x_evolution.ontos_v63_interface import CAPABILITIES
from omega_x_evolution.ontos_v66_wire import Envelope, encode
from omega_x_evolution.ontos_authenticated_boundary import (
    BoundaryPlan, SignedEnvelope, signing_payload, replay_boundary,
)

OBJECT=Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
AUDITOR=Ed25519PrivateKey.from_private_bytes(bytes(range(32,64)))


def plan(**changes):
    data=dict(tenant='tenant',session_id='a'*64,root_caps=CAPABILITIES,deadline=20,
              object_key=OBJECT.public_key().public_bytes_raw(),
              auditor_key=AUDITOR.public_key().public_bytes_raw())
    data.update(changes)
    return BoundaryPlan(**data)


def packet(p,previous,sequence,channel,kind,cap=None,*,key=None,tick=None,tenant=None,nonce=None):
    at=sequence+1 if tick is None else tick
    body=json.dumps({'alarm':kind=='alarm','cap':cap,'kind':kind},sort_keys=True,separators=(',',':')).encode()
    raw=encode(Envelope('ontos-ipc-v1',channel,tenant or p.tenant,nonce or f'n{sequence}',sequence,0,100,body))
    signer=key if key is not None else (AUDITOR if channel in 'BE' else OBJECT)
    return SignedEnvelope(previous,at,raw,signer.sign(signing_payload(p.sha256,previous,at,raw)))


def chain(p,commands):
    out=[];head=p.sha256
    for n,command in enumerate(commands):
        f=packet(p,head,n,*command);out.append(f);head=f.sha256(p.sha256)
    return tuple(out)


def replay(p,frames,**kw):
    return replay_boundary(p,p.sha256,frames,**kw)


def test_signed_model_approval_narrows_capabilities_only():
    p=plan(); frames=chain(p,[('A','observe'),('B','assess'),('C','propose','remember'),('E','allow','remember')])
    r=replay(p,frames)
    assert r.session.caps==frozenset({'remember'}) and r.session.phase=='MODEL_APPROVED'
    assert r.receiver.next_sequence==4
    assert not r.session.operational_capabilities_granted
    assert not r.retained_head_verified
    assert replay(p,frames,expected_head=r.head).retained_head_verified


@pytest.mark.parametrize('commands',[[],[('A','observe')],[('A','observe'),('B','assess')],[('A','observe'),('B','assess'),('C','propose','remember')],[('A','observe'),('B','assess'),('D','propose','compute')],[('A','observe'),('B','assess'),('C','propose','remember'),('E','allow','remember')]])
def test_signed_alarm_and_restart_are_fail_closed_at_every_phase(commands):
    p=plan(); frames=chain(p,commands+[('B','alarm'),('E','restart')]);r=replay(p,frames)
    assert r.session.phase=='LOCKDOWN' and not r.session.caps and r.session.pending_cap is None
    next_frame=packet(p,r.head,len(frames),'A','observe')
    with pytest.raises(ValueError): replay(p,frames+(next_frame,))


@pytest.mark.parametrize('channel,kind,cap,key',[('A','observe',None,AUDITOR),('B','alarm',None,OBJECT),('E','veto',None,OBJECT),('C','propose','remember',AUDITOR)])
def test_wrong_role_signature_rejected(channel,kind,cap,key):
    p=plan();f=packet(p,p.sha256,0,channel,kind,cap,key=key)
    with pytest.raises(ValueError,match='signature'): replay(p,(f,))


def test_signed_replay_tenant_clock_and_chain_fail_closed():
    p=plan();f=packet(p,p.sha256,0,'A','observe',tick=2);head=f.sha256(p.sha256)
    bads=(f,packet(p,head,1,'B','assess',nonce='n0'),packet(p,head,1,'B','assess',tenant='other'),packet(p,head,1,'B','assess',tick=1),packet(p,p.sha256,1,'B','assess'))
    for bad in bads:
        with pytest.raises(ValueError): replay(p,(f,bad))


def test_signature_binds_payload_and_tick_and_session():
    p=plan();f=packet(p,p.sha256,0,'A','observe');other=plan(session_id='b'*64)
    bads=(replace(f,at_tick=2),replace(f,raw=packet(p,p.sha256,0,'A','observe',nonce='changed').raw),replace(f,signature=b'\x00'*64))
    for bad in bads:
        with pytest.raises(ValueError): replay(p,(bad,))
    with pytest.raises(ValueError): replay_boundary(other,p.sha256,(f,))
    with pytest.raises(ValueError): replay(other,(replace(f,previous=other.sha256),))


def test_truncated_history_detected_relative_to_retained_head():
    p=plan(); frames=chain(p,[('A','observe'),('B','alarm')]); r=replay(p,frames)
    with pytest.raises(ValueError): replay(p,frames[:1],expected_head=r.head)
    assert replay(p,frames[:1]).session.phase=='OBSERVED'


@pytest.mark.parametrize('changes',[{'object_key':AUDITOR.public_key().public_bytes_raw()},{'auditor_key':b'\x01'+b'\x00'*31},{'tenant':'../x'},{'session_id':'x'},{'deadline':True},{'root_caps':frozenset({'shell'})}])
def test_invalid_pinned_plan(changes):
    with pytest.raises(ValueError): plan(**changes)


def test_explicit_timeout_removes_all_caps_and_is_sticky():
    p=plan(deadline=2); frames=chain(p,[('A','observe'),('B','assess'),('D','propose','compute'),('E','restart')]);r=replay(p,frames)
    assert r.session.phase=='LOCKDOWN' and not r.session.caps
