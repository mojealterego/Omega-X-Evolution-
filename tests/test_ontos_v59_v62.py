"""RED/GREEN — L9 finite oscillators, sheaf, data recovery, noise."""
from dataclasses import FrozenInstanceError
from itertools import product
import math
import pytest
import numpy as np

from omega_x_evolution.ontos_v59_oscillator import (
    KuramotoState, coupling_force, advance, potential_energy, order_parameter,
)
from omega_x_evolution.ontos_v60_sheaf import (
    SheafEdge, energy, gradient, diffuse,
)
from omega_x_evolution.ontos_v61_faults import (
    GridCheckpoint, apply_event, fault_campaign,
)
from omega_x_evolution.ontos_v62_noise import (
    theoretical_error, simulate_error, drift_campaign,
)
from omega_x_evolution.ontos_repair import RepairState


def sample_state():
    return KuramotoState(phase=(0., 1., 2.), frequency=(0., 0., 0.),
                         factors=((1., .5), (.8, .1), (.4, 1.)))


def test_v59_dense_reference():
    s=sample_state()
    K=np.asarray(s.factors) @ np.asarray(s.factors).T
    phase=np.asarray(s.phase)
    dense=tuple(float(np.sum(K[i]*np.sin(phase-phase[i]))/3) for i in range(3))
    assert coupling_force(s)==pytest.approx(dense,abs=1e-13)


def test_v59_energy_decreases_for_unforced_flow():
    s=sample_state()
    start=potential_energy(s)
    for i in range(100):
        s=advance(s, .025)
        assert potential_energy(s) <= start+1e-10
        start=potential_energy(s)
    assert start < potential_energy(sample_state())
    assert order_parameter(s)>order_parameter(sample_state())


def test_v59_global_phase_shift_invariance():
    s=sample_state()
    t=KuramotoState(tuple(x+.5 for x in s.phase),s.frequency,s.factors)
    assert coupling_force(t)==pytest.approx(coupling_force(s))
    assert potential_energy(t)==pytest.approx(potential_energy(s))


def test_v59_unforced_singleton_and_external_forcing():
    s=KuramotoState((.5,),(3.,),((.8,),))
    t=advance(s,.01,steps=10)
    assert t.phase[0]==pytest.approx(.8)
    assert coupling_force(s)==(0.,)
    assert potential_energy(s)==0
    assert 0<=order_parameter(t)<=1


@pytest.mark.parametrize('phase,frequency,factors', [
    ((),(),()), ((0.,),(0.,),((-.1,),)),
    ((float('nan'),),(0.,),((1.,),)),
    ((0.,),(float('inf'),),((1.,),)),
    ((0.,1.),(0.,),((1.,),(1.,))),
    ((0.,1.),(0.,0.),((1.,),)),
    ((0.,),(0.,),((True,),)),
])
def test_v59_rejects_bad_states(phase,frequency,factors):
    with pytest.raises(ValueError): KuramotoState(phase,frequency,factors)


@pytest.mark.parametrize('step,n', [(-.01,1),(.1,1),(.01,0),(.01,257), (True,1)])
def test_v59_step_contract(step,n):
    with pytest.raises(ValueError): advance(sample_state(),step,steps=n)


def test_v60_dense_gradient_reference():
    x=((1.,2.),(2.,0.),(0.,0.))
    edge=SheafEdge(0,1,((1.,0.),(0.,2.)),((2.,0.),(0.,1.)),1.)
    g=gradient(x,(edge,))
    # δ=(1-4, 4-0)=(-3,4); gradient left=A^T δ=(-3,8), right=-B^T δ=(6,-4)
    assert g[0]==pytest.approx((-3.,8.))
    assert g[1]==pytest.approx((6.,-4.))
    assert g[2]==(0.,0.)
    assert energy(x,(edge,))==pytest.approx(.5*(9+16))


def test_v60_energy_nonincreasing_with_stable_dt():
    x=((2.,-1.),(0.,2.),(-2.,.5))
    edges=(SheafEdge(0,1,((1.,0.),(0.,1.)),((1.,0.),(0.,1.)),1.),
           SheafEdge(1,2,((1.,0.),(0.,1.)),((1.,0.),(0.,1.)),.5))
    e=energy(x,edges)
    for _ in range(80):
        x=diffuse(x,edges,.02)
        assert energy(x,edges)<=e+1e-12
        e=energy(x,edges)
    assert e < 1


def test_v60_identity_restrictions_constant_stable():
    x=((2.,3.),(2.,3.),(2.,3.))
    e=(SheafEdge(0,1,((1.,0.),(0.,1.)),((1.,0.),(0.,1.)),1.),)
    assert diffuse(x,e,.01)==x
    assert energy(x,e)==0


def test_v60_nontrivial_restriction_and_disconnected():
    x=((1.,0.),(0.,0.),(9.,9.))
    edge=SheafEdge(0,1,((2.,0.),),((1.,0.),),1.)
    y=diffuse(x,(edge,),.02)
    assert y[0][0]<x[0][0] and y[1][0]>0
    assert y[2]==x[2]


def test_v60_step_is_fail_closed_for_oversized_dt():
    e=SheafEdge(0,1,((2.,0.),),((2.,0.),),1.)
    with pytest.raises(ValueError,match='stability'):
        diffuse(((1.,0.),(0.,0.)),(e,),.5)


@pytest.mark.parametrize('case', [
    (0,0,((1.,),),((1.,),),1.),
    (0,1,((1.,0.),),((1.,),),1.),
    (0,1,((float('nan'),0.),),((1.,0.),),1.),
    (0,1,((1.,0.),),((1.,0.),),-1.),
    (0,1,((1.,0.),(1.,)),((1.,0.),(1.,0.)),1.),
])
def test_v60_invalid_edge(case):
    with pytest.raises(ValueError): SheafEdge(*case)


def base_grid():
    return GridCheckpoint(3, RepairState((0.,)*9,1.,1000,1000))


def test_v61_simultaneous_faults_are_local():
    a=base_grid()
    b=apply_event(a,'inject1','inject',(0,4),.8,0)
    assert b.state.error==(0.8,0.,0.,0.,.8,0.,0.,0.,0.)
    assert a.state.error==(0.,)*9
    assert b.applied_ids==('inject1',)
    with pytest.raises(FrozenInstanceError): b.state.error=(0.,)*9


def test_v61_repair_measures_error_contraction_and_budget():
    s=apply_event(base_grid(),'f','inject',(1,7),.7,0)
    before=math.hypot(*s.state.error)
    t=apply_event(s,'repair-1','repair',(),0.,200)
    assert math.hypot(*t.state.error)<before
    assert t.state.remaining==800
    assert t.audit[-1].spent==200
    assert t.audit[-1].error_after < t.audit[-1].error_before
    assert t.state.integrity>=s.state.integrity


def test_v61_resource_exhaustion_preserves_state():
    s=apply_event(base_grid(),'f','inject',(1,),.6,0)
    a=apply_event(s,'r1','repair',(),0.,850)
    assert a.state.remaining==150
    b=apply_event(a,'r2','repair',(),0.,1)
    assert b.state==a.state and b.audit[-1].spent==0


def test_v61_idempotent_duplicate_event():
    s=apply_event(base_grid(),'f','inject',(0,),.4,0)
    assert apply_event(s,'f','inject',(0,),.4,0)==s


def test_v61_reused_event_id_with_changed_payload_fails():
    s=apply_event(base_grid(),'f','inject',(0,),.4,0)
    with pytest.raises(ValueError,match='idempotency'):
        apply_event(s,'f','inject',(1,),.4,0)


def test_v61_rejected_event_is_atomic():
    s=base_grid()
    with pytest.raises(ValueError): apply_event(s,'bad','inject',(99,),.4,0)
    with pytest.raises(ValueError): apply_event(s,'bad','repair',(),0.,-5)
    assert s==base_grid()


def test_v61_campaign_is_replayable_and_report_honest():
    a=fault_campaign((9216,9274,9651))
    assert a==fault_campaign((9216,9274,9651))
    assert len(a['runs'])==3
    assert a['simulation_only']
    assert a['measured_physical_recovery'] is False
    for r in a['runs']:
        assert r['after_error'] < r['before_error']
        assert r['spent']>0 and r['remaining']>=150


def test_v62_theory_independent_vs_correlated():
    assert theoretical_error(.1,3,correlation=0.)==pytest.approx(.0001)
    assert theoretical_error(.1,3,correlation=1.)==pytest.approx(.1)
    assert theoretical_error(.1,3,correlation=.5)==pytest.approx(.05005)


def test_v62_monte_carlo_matches_independent_theory():
    r=simulate_error(9011,p=.1,rechecks=3,correlation=0.,trials=40000)
    assert abs(r['error_rate']-r['expected_rate'])<.001
    assert r['checks_per_trial']==4
    assert r['modeled_checks']==160000
    assert r==simulate_error(9011,p=.1,rechecks=3,correlation=0.,trials=40000)


def test_v62_correlated_noise_disproves_false_p_power_law():
    r=simulate_error(9011,p=.1,rechecks=3,correlation=1.,trials=10000)
    assert r['error_rate']>.05
    assert r['expected_rate']==pytest.approx(.1)
    assert not r['independent_checks']


def test_v62_drift_campaign_evidence_separated_from_source_targets():
    r=drift_campaign((9216,9274,9651))
    assert r==drift_campaign((9216,9274,9651))
    assert r['trials']==3*240
    assert r['source_suite_d_accuracy_reproduced'] is False
    assert r['source_suite_d_health_reproduced'] is False
    assert r['mean_recheck_cost']>0
    assert r['correlated_false_acceptance']>=r['independent_false_acceptance']


@pytest.mark.parametrize('p,rechecks,corr', [(-.1,3,0.),(float('nan'),3,0.),(.1,-1,0.),(.1,9,0.),(.1,3,1.1),(.1,True,0.)])
def test_v62_invalid_config(p,rechecks,corr):
    with pytest.raises(ValueError): theoretical_error(p,rechecks,correlation=corr)


def test_v62_rejects_invalid_replay_specs():
    with pytest.raises(ValueError): simulate_error(True,p=.1,rechecks=3,correlation=0.,trials=10)
    with pytest.raises(ValueError): simulate_error(2,p=.1,rechecks=3,correlation=0.,trials=0)
    with pytest.raises(ValueError): drift_campaign((1,1))


def test_integration_v59_v62_four_models_no_privilege_path():
    oscillator=advance(sample_state(),.01)
    edge=SheafEdge(0,1,((1.,0.),),((1.,0.),),1.)
    sx=diffuse(((1.,0.),(0.,0.)),(edge,),.01)
    repaired=apply_event(apply_event(base_grid(),'i','inject',(0,),.5,0),'r','repair',(),0.,100)
    noise=theoretical_error(.1,3,correlation=.25)
    assert math.isfinite(oscillator.phase[0])
    assert energy(sx,(edge,))<energy(((1.,0.),(0.,0.)),(edge,))
    assert repaired.state.error[0]<.5 and noise>.001
    assert not hasattr(repaired,'deploy')
