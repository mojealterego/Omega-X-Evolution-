"""Finite authenticated A-E boundary; no native sandbox assertions."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from omega_x_evolution.ontos_v66_wire import Envelope, encode
from omega_x_evolution.ontos_v73_isolation import IsolationGateway, signing_bytes

OBJ = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
EXT = Ed25519PrivateKey.from_private_bytes(bytes(reversed(range(32))))
SID = b's' * 32
CAPS = frozenset({'sense', 'remember', 'compute'})


def pub(key):
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def gateway(*, session_id=SID, tenant='alpha', external=EXT):
    return IsolationGateway(tenant=tenant, session_id=session_id, root_caps=CAPS,
                            deadline=100, object_key=pub(OBJ), external_key=pub(external))


def wire(channel, kind, seq, *, cap=None, alarm=False, tenant='alpha', expires=100):
    body = json.dumps({'kind':kind,'cap':cap,'alarm':alarm},sort_keys=True,separators=(',',':')).encode()
    return encode(Envelope('ontos-ipc-v1',channel,tenant,f'n{seq}',seq,0,expires,body))


def signed(g, raw, key):
    return key.sign(signing_bytes(g.session_id,g.snapshot().history,raw))


def submit(g, raw, key, tick=1):
    return g.submit(raw,signed(g,raw,key),at_tick=tick)


def prepare(g, channel='C'):
    for seq,(ch,kind,cap) in enumerate((('A','observe',None),('B','assess',None),(channel,'propose','remember'))):
        assert submit(g,wire(ch,kind,seq,cap=cap),OBJ) == 'COMMITTED_TO_MODEL'


@pytest.mark.parametrize('channel',['C','D'])
def test_distinct_authorities_and_monotone_caps(channel):
    g = gateway(); prepare(g,channel)
    raw = wire('E','allow',3,cap='remember')
    before = g.snapshot()
    assert submit(g,raw,OBJ) == 'UNAUTHENTICATED'
    assert g.snapshot() == before
    assert submit(g,raw,EXT) == 'COMMITTED_TO_MODEL'
    after = g.snapshot()
    assert after.phase == 'MODEL_APPROVED' and after.caps == {'remember'}
    assert after.operational_capabilities_granted is False
    assert submit(g,wire('E','restart',4),EXT) == 'COMMITTED_TO_MODEL'
    assert g.snapshot().caps == {'remember'}


def test_external_key_cannot_impersonate_object_and_keys_must_differ():
    g = gateway(); before = g.snapshot()
    assert submit(g,wire('A','observe',0),EXT) == 'UNAUTHENTICATED'
    assert g.snapshot() == before
    with pytest.raises(ValueError): gateway(external=OBJ)


def test_binding_tenant_session_and_transcript():
    g = gateway(); other = gateway(session_id=b't'*32)
    raw = wire('A','observe',0)
    sig = signed(g,raw,OBJ)
    assert other.submit(raw,sig,at_tick=1) == 'UNAUTHENTICATED'
    assert submit(g,wire('A','observe',0,tenant='beta'),OBJ) == 'TENANT_REJECTED'
    assert g.submit(raw,sig,at_tick=1) == 'COMMITTED_TO_MODEL'
    assert g.submit(raw,sig,at_tick=1) == 'UNAUTHENTICATED'
    assert g.snapshot().next_sequence == 1


def test_approval_cannot_be_reused_for_different_proposal():
    a,b = gateway(),gateway(); prepare(a,'C'); prepare(b,'D')
    raw = wire('E','allow',3,cap='remember')
    sig = signed(a,raw,EXT)
    assert b.submit(raw,sig,at_tick=1) == 'UNAUTHENTICATED'
    assert a.submit(raw,sig,at_tick=1) == 'COMMITTED_TO_MODEL'
    assert b.snapshot().phase == 'PROPOSED_D'


@pytest.mark.parametrize('kind',['host_read','network_connect','key_export','evaluator_write','audit_write'])
def test_no_protected_resource_operation_in_model(kind):
    g = gateway(); before = g.snapshot()
    assert submit(g,wire('A',kind,0),OBJ) == 'POLICY_REJECTED'
    assert g.snapshot() == before


def test_veto_and_restart_cannot_reacquire_caps():
    g = gateway(); prepare(g)
    assert submit(g,wire('E','veto',3),EXT) == 'COMMITTED_TO_MODEL'
    assert g.snapshot().phase == 'LOCKDOWN' and not g.snapshot().caps
    assert submit(g,wire('E','restart',4),EXT) == 'COMMITTED_TO_MODEL'
    assert g.snapshot().phase == 'LOCKDOWN' and not g.snapshot().caps
    assert submit(g,wire('A','observe',5),OBJ) == 'POLICY_REJECTED'


def test_deep_malformed_frames_and_bad_inputs_fail_closed():
    g = gateway(); before = g.snapshot()
    assert g.submit(b'['*2000+b']'*2000,bytes(64),at_tick=1) == 'INVALID_FRAME'
    assert g.submit(b'x'*8193,bytes(64),at_tick=1) == 'INVALID_FRAME'
    raw = wire('A','observe',0)
    assert g.submit(raw,bytes(64),at_tick=1) == 'UNAUTHENTICATED'
    assert g.submit(raw,signed(g,raw,OBJ),at_tick=True) == 'INVALID_TICK'
    assert submit(g,wire('A','observe',0,expires=0),OBJ) == 'EXPIRED'
    assert g.snapshot() == before


def test_competing_delivery_is_atomic():
    g = gateway(); raw = wire('A','observe',0); sig = signed(g,raw,OBJ)
    with ThreadPoolExecutor(max_workers=2) as ex:
        results = list(ex.map(lambda _:g.submit(raw,sig,at_tick=1),range(2)))
    assert sorted(results) == ['COMMITTED_TO_MODEL','UNAUTHENTICATED']
    assert g.snapshot().next_sequence == 1


def test_trusted_delivery_tick_is_bound_to_history():
    a,b = gateway(),gateway()
    raw = wire('A','observe',0)
    sig = signed(a,raw,OBJ)
    assert a.submit(raw,sig,at_tick=1) == 'COMMITTED_TO_MODEL'
    assert b.submit(raw,sig,at_tick=2) == 'COMMITTED_TO_MODEL'
    assert a.snapshot().history != b.snapshot().history
    follow = wire('B','assess',1)
    assert b.submit(follow,signed(a,follow,OBJ),at_tick=3) == 'UNAUTHENTICATED'
