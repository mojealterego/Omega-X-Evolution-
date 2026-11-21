"""Finite ONTOS v63-v66 contracts, TDD: no operational rights or external services."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import pytest

from omega_x_evolution.ontos_logic import Poly, Lens
from omega_x_evolution.ontos_v47_pure_ir import PureIR
from omega_x_evolution.ontos_v63_interface import Session, Frame, transition, run_sequence
from omega_x_evolution.ontos_v64_certificate import certify, verify_certificate
from omega_x_evolution.ontos_v65_hypertraces import Event, check_pairwise, check_interleavings
from omega_x_evolution.ontos_v66_wire import Envelope, Receiver, encode, decode, receive


def session():
    return Session(frozenset({'sense', 'remember', 'compute'}),
                   frozenset({'sense', 'remember', 'compute'}), deadline=12)


def frame(channel, kind, nonce, tick, cap=None, alarm=False):
    return Frame(channel, kind, nonce, tick, cap, alarm)


def test_v63_happy_precommit_model_never_executes():
    s = session()
    for f in [frame('A','observe','obs',1), frame('B','assess','risk',2),
              frame('C','propose','candidate',3,'remember'),
              frame('E','allow','decision',4,'remember')]:
        s = transition(s,f)
    assert s.phase == 'MODEL_APPROVED'
    assert s.caps == frozenset({'remember'})
    assert s.operational_capabilities_granted is False
    assert s.audit[-1].startswith('E:allow')
    assert s.audit[0].startswith('A:observe')


def test_v63_proposal_requires_external_assessment_and_lens_contract():
    s = session()
    with pytest.raises(ValueError): transition(s,frame('C','propose','jump',1,'sense'))
    p = Poly((2,))
    lens = Lens.identity(p)
    assert lens.compose(lens) == lens
    assert run_sequence(s,(frame('A','observe','a',1),frame('B','assess','b',2))).phase == 'ASSESSED'


def test_v63_lockdown_on_alarm_timeout_and_recovery_never_restores_rights():
    s = transition(session(),frame('A','observe','a',1))
    s = transition(s,frame('B','alarm','b',2,alarm=True))
    assert s.phase == 'LOCKDOWN' and not s.caps
    restarted = transition(s,frame('E','restart','r',3))
    assert restarted.phase == 'LOCKDOWN' and not restarted.caps
    with pytest.raises(ValueError): transition(restarted,frame('A','observe','post',4))
    t = transition(session(),frame('A','observe','late',13))
    assert t.phase == 'LOCKDOWN' and not t.caps


def test_v63_proposal_veto_and_monotonic_caps_under_sequences():
    s=session(); last=s.caps
    seq=(frame('A','observe','a',1),frame('B','assess','b',2),
         frame('D','propose','d',3,'compute'),frame('E','veto','v',4))
    for step in seq:
        s=transition(s,step)
        assert s.caps <= last
        last = s.caps
    assert s.phase == 'LOCKDOWN'
    assert not s.operational_capabilities_granted


def test_v63_invalid_replays_tenant_override_and_invalid_frames():
    s=transition(session(),frame('A','observe','a',1))
    with pytest.raises(ValueError): transition(s,frame('B','assess','a',2))
    with pytest.raises(ValueError): transition(s,frame('B','assess','wrong',0))
    with pytest.raises(ValueError): Frame('X','observe','a',1,None,False)
    with pytest.raises(ValueError): Frame('A','observe','../x',1,None,False)
    with pytest.raises(ValueError): Frame('A','observe','x',1,None,True)
    with pytest.raises(ValueError): frame('D','propose','d',1,'host_shell')


def test_v63_corrupted_frozen_state_rejected():
    s=session()
    object.__setattr__(s,'caps',frozenset({'forbidden'}))
    with pytest.raises(ValueError): transition(s,frame('A','observe','a',1))


def test_v64_exhaustive_certificate_and_independent_recheck():
    a=PureIR(('add',('x',),('lit',15)))
    b=PureIR(('sub',('x',),('lit',1)))
    cert=certify(a,b)
    assert cert['status']=='PASS_EXHAUSTIVE'
    assert cert['cases']==256
    assert verify_certificate(a,b,cert) is True
    assert cert['semantics']=='ontos-pure-i4-v1'
    assert cert['certificate_sha256'] == certify(a,b)['certificate_sha256']


def test_v64_forged_certificate_and_mutated_ir_rejected():
    a=PureIR(('add',('x',),('y',)))
    b=PureIR(('xor',('x',),('y',)))
    proof=certify(a,a)
    assert verify_certificate(a,b,proof) is False
    fake={**proof,'status':'PASS_EXHAUSTIVE','cases':4}
    assert verify_certificate(a,a,fake) is False
    object.__setattr__(a,'tree',('unknown',))
    assert verify_certificate(a,a,proof) is False


def test_v64_counterexample_and_incomplete_domain_cannot_pass():
    a=PureIR(('add',('x',),('y',)))
    b=PureIR(('xor',('x',),('y',)))
    cert=certify(a,b)
    assert cert['status']=='FAIL_COUNTEREXAMPLE' and cert['counterexample'] is not None
    assert not verify_certificate(a,b,cert)
    assert certify(a,a,max_cases=4)['status']=='UNKNOWN_BOUND'


def test_v64_float_semantics_not_mistaken_for_modular_ir():
    a=PureIR(('x',))
    assert certify(a,a,semantics='f32')['status']=='UNKNOWN_SEMANTICS'
    assert not verify_certificate(a,a,certify(a,a,semantics='f32'))


def test_v64_mdl_is_nonnegative_but_not_optimization_proof():
    a=PureIR(('add',('x',),('lit',0)))
    b=PureIR(('x',))
    c=certify(a,b)
    assert c['status']=='PASS_EXHAUSTIVE'
    assert c['mdl_nodes_before'] > c['mdl_nodes_after']
    assert verify_certificate(a,b,c)


def ev(tenant, name, low_in='same', secret='a', low_out='ok', reads=(), writes=()):
    return Event(tenant,name,low_in,secret,low_out,reads,writes)


def test_v65_same_public_input_different_secret_observation_must_match():
    t1=(ev('T','a',secret='one'),)
    t2=(ev('T','b',secret='two'),)
    check=check_pairwise((t1,t2),max_pairs=10)
    assert check['status']=='PASS_FINITE'
    assert check['compared_pairs']==1
    assert not check['proved_unbounded_hyperltl']
    bad=(ev('T','b',secret='two',low_out='leak'),)
    check=check_pairwise((t1,bad),max_pairs=10)
    assert check['status']=='FAIL_NONINTERFERENCE'
    assert check['counterexample']


def test_v65_noncomparable_or_budget_exhaustion_unknown():
    t1=(ev('T','a',low_in='x'),)
    t2=(ev('T','b',low_in='y'),)
    assert check_pairwise((t1,t2),max_pairs=10)['status']=='UNKNOWN_NO_COMPARABLE'
    assert check_pairwise((t1,(ev('T','c',low_in='x',secret='diff'),)),max_pairs=0)['status']=='UNKNOWN_BOUND'
    with pytest.raises(ValueError): check_pairwise((t1,),max_pairs=10)


def test_v65_independent_tenant_scopes_do_not_falsely_conflict():
    a=(ev('alpha','a',writes=('alpha:cache',)),)
    b=(ev('beta','b',reads=('beta:cache',)),)
    report=check_interleavings(a,b,max_schedules=6)
    assert report['status']=='PASS_FINITE'
    assert report['schedules']==2
    assert report['conflicts']==()


def test_v65_raw_war_waw_and_counterexample_interleavings():
    a=(ev('A','a',writes=('global:counter',)),)
    b=(ev('B','b',reads=('global:counter',),writes=('global:counter',)),)
    result=check_interleavings(a,b,max_schedules=6)
    assert result['status']=='FAIL_CONFLICT'
    assert {'RAW','WAR','WAW'} <= set(result['conflict_kinds'])
    assert result['counterexample']
    assert not result['verified_native_smt']


def test_v65_budget_unknown_never_passes():
    a=(ev('A','a',writes=('global:value',)),)
    b=(ev('B','b',reads=('global:value',)),)
    assert check_interleavings(a,b,max_schedules=1)['status']=='UNKNOWN_BOUND'


def test_v65_declared_sets_do_not_pretend_to_be_host_observations():
    a=(ev('A','a',writes=('global:value',)),)
    b=(ev('B','b',reads=('global:value',)),)
    r=check_interleavings(a,b,max_schedules=3)
    assert r['evidence_class']=='MODELLED_READ_WRITE_SETS'


def envelope(seq=0, nonce='nonce0', issued=10, expires=20, channel='A', payload=b'obs'):
    return Envelope('ontos-ipc-v1', channel, 'tenantA', nonce, seq, issued, expires, payload)


def test_v66_wire_canonical_roundtrip_with_binary_payload():
    message=envelope(payload=b'\x00\xffbinary')
    raw=encode(message)
    assert raw==encode(decode(raw))
    assert decode(raw)==message
    assert len(raw)<4096
    assert b'\n' not in raw


def test_v66_wire_rejects_unknown_version_crc_and_extra_fields():
    raw=encode(envelope())
    d=json.loads(raw)
    d['v']='future'
    with pytest.raises(ValueError): decode(json.dumps(d,sort_keys=True,separators=(',',':')).encode())
    d=json.loads(raw);d['extra']='evil'
    with pytest.raises(ValueError):decode(json.dumps(d,sort_keys=True,separators=(',',':')).encode())
    tampered=raw.replace(b'obs',b'xxx')
    if tampered!=raw:
        with pytest.raises(ValueError): decode(tampered)
    with pytest.raises(ValueError): decode(b'{"not":"canonical"}')


def test_v66_sequence_replay_ood_and_clock_expiry_fail_closed():
    state=Receiver('tenantA',0)
    state,rcpt=receive(state,encode(envelope()),at_tick=12)
    assert rcpt['status']=='DELIVERED_MODEL'
    assert state.next_sequence==1
    state2,receipt=receive(state,encode(envelope()),at_tick=13)
    assert state2==state
    assert receipt['status']=='REPLAY_REJECTED'
    state3,receipt=receive(state,encode(envelope(seq=1,nonce='nonce1')),at_tick=21)
    assert state3==state and receipt['status']=='EXPIRED'
    state4,receipt=receive(state,encode(envelope(seq=3,nonce='other')),at_tick=14)
    assert state4==state and receipt['status']=='OUT_OF_ORDER'


def test_v66_single_tenant_and_nonce_idempotency():
    state=Receiver('tenantA',0)
    state,receipt=receive(state,encode(envelope()),at_tick=10)
    wrong=envelope(seq=1,nonce='nonce1')
    wrong=dataclasses.replace(wrong,tenant='other')
    s,r=receive(state,encode(wrong),at_tick=11)
    assert s==state and r['status']=='TENANT_REJECTED'
    s,r=receive(state,encode(envelope(seq=1,nonce='nonce0')),at_tick=11)
    assert s==state and r['status']=='REPLAY_REJECTED'


def test_v66_bytes_and_size_bounds():
    with pytest.raises(ValueError): encode(envelope(payload=b'x'*4097))
    with pytest.raises(ValueError): decode('not bytes')
    with pytest.raises(ValueError): envelope(seq=True)
    with pytest.raises(ValueError): Envelope('ontos-ipc-v1','A','../tenant','n',0,1,2,b'')
    with pytest.raises(ValueError): Receiver('tenantA',-1)


def test_v66_no_physical_latency_claims():
    s=Receiver('tenantA',0)
    s,r=receive(s,encode(envelope()),at_tick=15)
    assert r['observed_ipc_latency_ms'] is None
    assert not r['native_rust_zenoh_wasi_verified']
    assert r['logical_age_ticks']==5


def test_v63_exhaustive_cap_subset_monotonicity_and_restarts():
    from itertools import combinations
    caps=('sense','remember','compute')
    for size in range(4):
        for combo in combinations(caps,size):
            root=frozenset(combo)
            state=Session(root,root,deadline=12)
            for i in range(2):
                state=transition(state,frame('E','restart',f'restart{i}',i+1))
                assert state.caps <= root and not state.operational_capabilities_granted
            if not root: continue
            chosen=sorted(root)[0]
            sequence=(frame('A','observe','a',4),frame('B','assess','b',5),
                      frame('C','propose','c',6,chosen),frame('E','allow','e',7,chosen))
            previous=state.caps
            for msg in sequence:
                state=transition(state,msg)
                assert state.caps <= previous
                previous=state.caps
            assert state.caps == frozenset((chosen,))
            restarted=transition(state,frame('E','restart','again',8))
            assert restarted.caps == state.caps


def test_v63_no_fake_approval_on_mismatched_pending_cap():
    s=run_sequence(session(),(frame('A','observe','a',1),
                              frame('B','assess','b',2),
                              frame('D','propose','d',3,'compute')))
    with pytest.raises(ValueError):transition(s,frame('E','allow','e',4,'sense'))
    assert s.phase == 'PROPOSED_D'
    with pytest.raises(ValueError):transition(s,frame('C','propose','other',4,'remember'))


def test_v64_proof_integrity_binds_all_fields_and_i4_domain():
    left=PureIR(('xor',('x',),('y',)))
    c=certify(left,left)
    assert verify_certificate(left,left,c)
    for key,replacement in [('truth_sha256','f'*64),('certificate_sha256','f'*64),
                            ('mdl_nodes_after',c['mdl_nodes_after']+1),
                            ('cases',255),('semantics','i16'),('schema','old')]:
        forged=dict(c);forged[key]=replacement
        assert not verify_certificate(left,left,forged)
    assert not verify_certificate(left,left,{**c,'extra':1})


def test_v64_all_256_cases_can_include_last_case_counterexample():
    left=PureIR(('and',('x',),('y',)))
    right=PureIR(('lit',0))
    c=certify(left,right)
    assert c['status']=='FAIL_COUNTEREXAMPLE'
    assert 1 <= c['cases'] <= 256
    assert verify_certificate(left,right,c) is False


def test_v65_seeded_model_has_no_unbounded_proof_claim():
    from itertools import product
    for sec_a,sec_b in product(('a','b'),repeat=2):
        t1=(ev('T','a',secret=sec_a,low_out='stable'),)
        t2=(ev('T','b',secret=sec_b,low_out='stable'),)
        r=check_pairwise((t1,t2),max_pairs=2)
        assert r['status'] in ('PASS_FINITE','UNKNOWN_NO_COMPARABLE')
        assert r['proved_unbounded_hyperltl'] is False


def test_v65_two_vs_two_schedules_and_repeated_execution_are_deterministic():
    a=(ev('A','a1',writes=('global:counter',)), ev('A','a2',reads=('global:counter',)))
    b=(ev('B','b1',reads=('global:counter',)), ev('B','b2',writes=('global:counter',)))
    r=check_interleavings(a,b,max_schedules=6)
    assert r['status']=='FAIL_CONFLICT'
    assert r['schedules']==6
    assert r==check_interleavings(a,b,max_schedules=6)
    assert check_interleavings(a,b,max_schedules=5)['status']=='UNKNOWN_BOUND'


def test_v65_rejects_foreign_tenant_read_scope():
    with pytest.raises(ValueError):ev('alice','a',reads=('bob:secret',))
    with pytest.raises(ValueError):ev('alice','a',writes=('../host',))


def test_v66_corrupted_checksum_and_noncanonical_whitespace_are_rejected():
    msg=encode(envelope())
    o=json.loads(msg)
    o['payload']='Y2hhbmdlZA=='
    with pytest.raises(ValueError):decode(json.dumps(o,sort_keys=True,separators=(',',':')).encode())
    with pytest.raises(ValueError):decode(msg+b' ')
    with pytest.raises(ValueError):decode(b'['+msg+b']')
    state=Receiver('tenantA',0)
    same,result=receive(state,msg+b' ',at_tick=15)
    assert same==state and result['status']=='INVALID_FRAME'


def test_v66_sequence_run_100_messages_no_implicit_host_actions():
    state=Receiver('tenantA',0)
    for i in range(100):
        src=envelope(seq=i,nonce=f'n{i}',issued=i,expires=i+1)
        state,r=receive(state,encode(src),at_tick=i)
        assert r['status']=='DELIVERED_MODEL'
        assert r['observed_ipc_latency_ms'] is None
        assert not r['native_rust_zenoh_wasi_verified']
    assert state.next_sequence==100 and state.deliveries==100
    before,replay_receipt=receive(state,encode(envelope(seq=0,nonce='n0')),at_tick=100)
    assert before==state and replay_receipt['status']=='REPLAY_REJECTED'


def test_v66_tenant_isolation_out_of_order_capacity_and_future_clock():
    state=Receiver('tenantA',0)
    for message,tick,code in [
        (envelope(seq=0,nonce='x',issued=5),4,'NOT_YET_VALID'),
        (envelope(seq=5,nonce='x'),12,'OUT_OF_ORDER'),
        (envelope(seq=0,nonce='x',issued=10,expires=11),12,'EXPIRED')]:
        s,r=receive(state,encode(message),at_tick=tick)
        assert s==state and r['status']==code
    # Caller-visible receiver state cannot be used as a native permission token.
    assert not hasattr(state,'grant_privilege')


def test_v66_wit_schema_is_present_without_native_claim():
    from pathlib import Path
    file=Path(__file__).resolve().parents[1] / 'interfaces/wit/ontos-ae-v1.wit'
    content=file.read_text(encoding='utf8')
    for name in ('package omega:ontos@0.1.0;', 'interface ae-protocol',
                 'world ontos-model','issued-tick: u64', 'payload: list<u8>',
                 'export ae-protocol;'):
        assert name in content


def test_v63_v66_integrated_model_precommit_and_atomic_rollback():
    from omega_x_evolution.ontos_v66_wire import model_precommit_delivery
    s=session();receiver=Receiver('tenantA',0)
    def packet(seq, channel,kind,cap=None,alarm=False):
        body=json.dumps({'alarm':alarm,'cap':cap,'kind':kind},sort_keys=True,
                        separators=(',',':')).encode()
        return encode(Envelope('ontos-ipc-v1',channel,'tenantA',f'packet{seq}',
                               seq,seq+1,seq+2,body))
    bad=packet(0,'E','allow','compute')
    ns,nr,r=model_precommit_delivery(s,receiver,bad,at_tick=1)
    assert ns==s and nr==receiver and r['status']=='POLICY_REJECTED'
    for seq,(channel,kind,cap) in enumerate((('A','observe',None),
                                             ('B','assess',None),
                                             ('D','propose','compute'),
                                             ('E','allow','compute'))):
        s,receiver,r=model_precommit_delivery(s,receiver,packet(seq,channel,kind,cap),at_tick=seq+1)
        assert r['status']=='COMMITTED_TO_MODEL'
        assert not r['operational_capabilities_granted']
    assert s.phase=='MODEL_APPROVED'
    assert s.caps==frozenset(('compute',))
    assert receiver.next_sequence==4
    after_s,after_r,result=model_precommit_delivery(s,receiver,packet(0,'A','observe'),at_tick=5)
    assert (after_s,after_r)==(s,receiver)
    assert result['status']=='REPLAY_REJECTED'


def test_v63_v66_model_rejects_malformed_payload_without_sequence_consumption():
    from omega_x_evolution.ontos_v66_wire import model_precommit_delivery
    session0=session(); receiver=Receiver('tenantA',0)
    msg=envelope(payload=b'{"kind":"observe","cap":null,"alarm":false} ')
    s,r,receipt=model_precommit_delivery(session0,receiver,encode(msg),at_tick=12)
    assert s==session0 and r==receiver and receipt['status']=='POLICY_REJECTED'
