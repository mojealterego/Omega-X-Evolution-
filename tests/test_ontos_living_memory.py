from dataclasses import replace
from fractions import Fraction
import hashlib
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from omega_x_evolution.ontos_living_memory import Batch, bind, diagnose, review_session, review_candidate
from omega_x_evolution.ontos_v51_skepticism import MemoryEvent
from omega_x_evolution.ontos_v51_sequential_memory import ReviewPlan, SignedTrial, signing_payload as trial_payload
from omega_x_evolution.ontos_authenticated_boundary import BoundaryPlan, SignedEnvelope, signing_payload as wire_payload
from omega_x_evolution.ontos_v63_interface import CAPABILITIES
from omega_x_evolution.ontos_v66_wire import Envelope, encode

A=(1,)*8; B=(-1,)*8; C=(-1,)+(1,)*7; D=(1,)+(-1,)*7
EVAL, OBJ, AUD=(Ed25519PrivateKey.from_private_bytes(bytes([i])*32) for i in (1,2,3))


def batch():
    return Batch(((A,A),(B,B))*12,((C,A),(D,B)))


def evidence(b, n=8):
    p=ReviewPlan('tenant',(b.sha256,),EVAL.public_key().public_bytes_raw(),24)
    head=p.sha256; rows=[]
    for i in range(1,n+1):
        e=MemoryEvent('tenant',b.sha256,f'e{i}',f'g{i}',hashlib.sha256(str(i).encode()).hexdigest(),True,0,1000,i)
        t=SignedTrial(head,i,e,EVAL.sign(trial_payload(p.sha256,head,i,e)))
        head=t.sha256(p.sha256); rows.append(t)
    return p,tuple(rows),head


def boundary(p,b,head,alarm=False,**changes):
    args=dict(tenant=p.tenant,session_id=review_session(p.sha256,head,b.sha256),root_caps=CAPABILITIES,deadline=20,object_key=OBJ.public_key().public_bytes_raw(),auditor_key=AUD.public_key().public_bytes_raw()); args.update(changes)
    bp=BoundaryPlan(**args); h=bp.sha256; rows=[]
    commands=[('A','observe',None),('B','assess',None),('C','propose','remember'),('E','allow','remember')]
    if alarm: commands.extend([('B','alarm',None),('E','restart',None)])
    for i,(c,k,cap) in enumerate(commands):
        raw=encode(Envelope('ontos-ipc-v1',c,bp.tenant,f'n{i}',i,0,100,json.dumps({'alarm':k=='alarm','cap':cap,'kind':k},sort_keys=True,separators=(',',':')).encode()))
        key=AUD if c in 'BE' else OBJ
        s=SignedEnvelope(h,i+1,raw,key.sign(wire_payload(bp.sha256,h,i+1,raw)))
        h=s.sha256(bp.sha256); rows.append(s)
    return bp,tuple(rows),h


def run(b,e,bound):
    p,t,h=e; bp,m,bh=bound
    return review_candidate(b,p,p.sha256,t,h,bp,bp.sha256,m,bh)


def test_vsa_exact_inverse_and_candidate_identity():
    assert bind(bind(A,C),C)==A
    assert batch().sha256==batch().sha256
    assert replace(batch(),probes=((C,B),(D,A))).sha256!=batch().sha256


def test_adaptive_recall_and_prediction_on_unseen_keys():
    b=batch(); r=diagnose(b)
    assert r==diagnose(b)
    assert r['hopfield_bit_accuracy']==1
    assert r['predictive_mse']<r['zero_predictor_mse']
    assert r['predictive_bit_accuracy']==1
    assert len(r['scale_weight_norms'])==3
    assert r['promotion_authorized'] is False


def test_probe_targets_do_not_train_or_change_predictions():
    b=batch(); a=diagnose(b); z=diagnose(replace(b,probes=((C,B),(D,A))))
    assert a['model_sha256']==z['model_sha256']
    assert a['predictions']==z['predictions']
    assert a['hopfield_bit_accuracy']==1 and z['hopfield_bit_accuracy']==0


def test_three_signed_roles_and_exact_heads_enable_diagnostic_only():
    b=batch(); e=evidence(b); result=run(b,e,boundary(e[0],b,e[2]))
    assert result['decision']=='QUARANTINED_DIAGNOSTIC'
    assert result['diagnostic']['hopfield_bit_accuracy']==1
    assert not result['promotion_authorized'] and not result['null_verified']


@pytest.mark.parametrize('n,alarm',[(4,False),(8,True)])
def test_insufficient_evidence_or_sticky_alarm_blocks_computation(n,alarm):
    b=batch(); e=evidence(b,n); result=run(b,e,boundary(e[0],b,e[2],alarm))
    assert result['decision']=='QUARANTINED_BLOCKED' and result['diagnostic'] is None


def test_scope_candidate_and_exact_history_binding():
    b=batch(); e=evidence(b); p,t,h=e; bp,m,bh=boundary(p,b,h)
    for args in [(replace(b,probes=((C,B),(D,A))),p,p.sha256,t,h,bp,bp.sha256,m,bh),(b,p,p.sha256,t[:-1],h,bp,bp.sha256,m,bh),(b,p,p.sha256,t,h,bp,bp.sha256,m[:-1],bh),(b,p,p.sha256,t,h,bp,bp.sha256,m,None)]:
        with pytest.raises(ValueError): review_candidate(*args)
    for change in ({'tenant':'foreign'},{'session_id':'b'*64},{'object_key':p.evaluator_key}):
        other=replace(bp,**change)
        with pytest.raises(ValueError): review_candidate(b,p,p.sha256,t,h,other,other.sha256,m,bh)


@pytest.mark.parametrize('train,probes',[((),((C,A),)),(((A,A),),((A,B),)),(((A,A),),(((True,)*8,A),)),(((A,A),),((C,(1,)*9),)),(((A,A),)*65,((C,A),)),(((A,A),),())])
def test_batch_bounds_and_disjoint_probes(train,probes):
    with pytest.raises(ValueError): Batch(train,probes)


def test_seeded_noisy_key_campaign():
    import numpy as np
    metrics=[]
    for seed in range(32):
        rng=np.random.default_rng(seed); d=16
        keys=[tuple(1 if (i&j).bit_count()%2==0 else -1 for j in range(d)) for i in range(8)]
        values=[tuple(map(int,rng.choice([-1,1],d))) for _ in keys]
        train=list(zip(keys,values))*8; rng.shuffle(train)
        probes=[]
        for k,v in zip(keys,values):
            q=list(k); q[int(rng.integers(d))]*=-1; probes.append((tuple(q),v))
        r=diagnose(Batch(tuple(train),tuple(probes)))
        metrics.append((r['predictive_mse'],r['predictive_bit_accuracy'],r['hopfield_bit_accuracy']))
        assert all(0<=x<=2.+1e-12 for x in r['scale_weight_norms'])
    mse,predictive,hopfield=np.mean(metrics,axis=0)
    assert mse<.5 and predictive>.95 and hopfield==1.
