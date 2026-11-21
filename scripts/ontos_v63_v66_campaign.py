"""Deterministic 30-seed L10 reference campaign; zero host or network actions."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json

from omega_x_evolution.ontos_v47_pure_ir import PureIR
from omega_x_evolution.ontos_v63_interface import Frame, Session, run_sequence
from omega_x_evolution.ontos_v64_certificate import certify, verify_certificate
from omega_x_evolution.ontos_v65_hypertraces import Event, check_pairwise, check_interleavings
from omega_x_evolution.ontos_v66_wire import Envelope, Receiver, encode, decode, model_precommit_delivery

SEEDS = tuple(9100 + 29*i for i in range(30))


def campaign() -> dict:
    full = []
    caps = ('compute', 'remember', 'sense')
    a = PureIR(('add', ('x',), ('lit', 15)))
    b = PureIR(('sub', ('x',), ('lit', 1)))
    proof = certify(a,b)
    assert verify_certificate(a,b,proof)
    for seed in SEEDS:
        selected = caps[seed%3]
        channel = 'D' if seed%2 else 'C'
        session = Session(frozenset(caps),frozenset(caps),deadline=30)
        msgs = (('A','observe',None),('B','assess',None),
                (channel,'propose',selected),('E','allow',selected))
        frames = tuple(Frame(ch,action,f's{seed}_{i}',i+1,cap)
                       for i,(ch,action,cap) in enumerate(msgs))
        result = run_sequence(session,frames)
        assert result.phase=='MODEL_APPROVED' and result.caps==frozenset((selected,))
        left = (Event('alpha',f'a{seed}','public','S1','ok',(),('global:counter',)),)
        right = (Event('beta',f'b{seed}','public','S2','ok',('global:counter',),()),)
        conflict = check_interleavings(left,right,max_schedules=2)
        low = check_pairwise(((Event('alpha','x','public','S1','ok',(),()),),
                              (Event('alpha','y','public','S2','ok',(),()),)),max_pairs=2)
        assert conflict['status']=='FAIL_CONFLICT' and low['status']=='PASS_FINITE'
        receiver = Receiver('tenant',0)
        packets=[]
        for sequence,(ch,action,cap) in enumerate(msgs):
            body = json.dumps({'kind':action,'cap':cap,'alarm':False},
                              sort_keys=True,separators=(',',':')).encode()
            wire = encode(Envelope('ontos-ipc-v1',ch,'tenant',f's{seed}_{sequence}',
                                   sequence,sequence+1,sequence+2,body))
            packets.append(wire)
        for wire in packets:
            receiver, receipt = __wire_only_deliver(receiver,wire)
            assert receipt == 'DELIVERED_MODEL'
        assert receiver.deliveries==4
        replay_state, replay_receipt = __wire_only_deliver(receiver,packets[0])
        assert replay_state==receiver and replay_receipt == 'REPLAY_REJECTED'
        full.append({'seed':seed,'selected_cap':selected,
                     'proposal_channel':channel,'session_phase':result.phase,
                     'operational_capabilities_granted':result.operational_capabilities_granted,
                     'session_log_sha256':hashlib.sha256(json.dumps(result.audit).encode()).hexdigest(),
                     'conflict_verdict':conflict['status'],
                     'noninterference_verdict':low['status'],
                     'wire_batch_sha256':hashlib.sha256(b''.join(packets)).hexdigest(),
                     'receiver_deliveries':receiver.deliveries,
                     'replay_verdict':replay_receipt})
    return {'schema':'ontos-l10-v63-v66-finite-v1',
            'base_seed_count':len(SEEDS),
            'certificate_256_i4_valid':True,
            'certificate_sha256':proof['certificate_sha256'],
            'model_only':True,
            'actual_runtime_permissions_granted':False,
            'native_lean_smt_egglog_verified':False,
            'native_rust_zenoh_wasi_verified':False,
            'measured_ipc_latency_ms':None,
            'events':full}


def __wire_only_deliver(receiver:Receiver,raw:bytes):
    from omega_x_evolution.ontos_v66_wire import receive
    env = decode(raw)
    next_receiver,receipt = receive(receiver,raw,at_tick=max(receiver.last_tick,env.issued_at))
    return next_receiver,receipt['status']


if __name__=='__main__':
    print(json.dumps(campaign(),sort_keys=True,indent=2,allow_nan=False))
