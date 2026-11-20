"""Phase0 test-first requirements; no operational runtime or source execution."""
import hashlib
import json
import math
from dataclasses import FrozenInstanceError

import pytest

from omega_x_evolution.ontos_v52_temporal import (
    TemporalEvent, temporal_view, clock_windows, temporal_consistency,
)
from omega_x_evolution.ontos_v53_accounting import (
    WorkLedger, WorkEstimate, estimate_kernel,
)
from omega_x_evolution.ontos_v54_phase0 import (
    run_phase0, PHASE0_SEEDS,
)

D = hashlib.sha256(b'synthetic-source').hexdigest()


def ev(ident='a', v=1, tx=1, start=0, end=100, group=None, tenant='tenant'):
    return TemporalEvent(tenant,ident,group or ident,str(v),D,start,end,tx,6)


def test_v52_independent_bitemporal_axes_and_late_correction():
    original=ev(v=1,tx=1)
    correction=ev(v=2,tx=10,start=30,end=60)
    data=(correction,original)
    assert temporal_view(data,tenant='tenant',valid_at=40,known_at=9).visible[0].value=='1'
    assert temporal_view(data,tenant='tenant',valid_at=40,known_at=10).visible[0].value=='2'
    assert temporal_view(data,tenant='tenant',valid_at=20,known_at=10).visible==()
    assert temporal_view(data,tenant='other',valid_at=40,known_at=10).visible==()
    assert temporal_view(data[::-1],tenant='tenant',valid_at=40,known_at=10)==temporal_view(data,tenant='tenant',valid_at=40,known_at=10)


def test_v52_group_collision_blocks_independence_claim():
    rows=(ev('a'),ev('b',group='a'))
    with pytest.raises(ValueError,match='independence'):
        temporal_view(rows,tenant='tenant',valid_at=20,known_at=3)


def test_v52_clock_windows_and_retention_bounds():
    assert clock_windows(25,1)==(22,23,24,25)
    assert clock_windows(25,6)==(6,12,18,24)
    assert clock_windows(75,24)==(0,24,48,72)
    with pytest.raises(ValueError): clock_windows(25,7)
    with pytest.raises(ValueError): clock_windows(True,6)


def test_v52_timestamp_conflicts_and_caps():
    with pytest.raises(ValueError,match='ambiguous'):
        temporal_view((ev('a',v=1),ev('a',v=2)),tenant='tenant',valid_at=1,known_at=3)
    with pytest.raises(ValueError): ev(start=8,end=8)
    with pytest.raises(ValueError): ev(tenant='../evil')
    with pytest.raises(ValueError): TemporalEvent('tenant','a','a','v',D,0,100,1,7)
    with pytest.raises(ValueError): temporal_view(tuple(ev(str(i),group=str(i)) for i in range(257)),tenant='tenant',valid_at=1,known_at=1)


def test_v52_retention_and_source_do_not_imply_authentication():
    rows=(ev('a',tx=1),ev('b',tx=2))
    s=temporal_view(rows,tenant='tenant',valid_at=50,known_at=2)
    assert s.provenance_authenticated is False and s.independence_verified is False
    assert s.visible[0].source_sha256==D
    assert temporal_consistency(rows,tenant='tenant',valid_at=50,known_at=2)['selected']==2
    with pytest.raises(FrozenInstanceError): s.visible[0].value='hacked'


def test_v53_known_workload_kernel_units_separated():
    infer=estimate_kernel('inference',rows=2,cols=3)
    update=estimate_kernel('update',rows=2,cols=3)
    qr=estimate_kernel('qr',rows=4,cols=2)
    svd=estimate_kernel('svd',rows=4,cols=2)
    lp=estimate_kernel('lp',rows=4,cols=2)
    assert infer.compute_units==12
    assert update.compute_units==24
    assert qr.compute_units==32
    assert svd.compute_units==64
    assert lp.compute_units==24
    assert all(x.io_bytes>0 for x in (infer,update,qr,svd,lp))
    assert infer.kind=='inference' and qr.kind=='qr'


def test_v53_reserve_before_settle_without_mutation():
    ledger=WorkLedger(max_compute_units=1000,max_io_bytes=10000)
    plan=WorkEstimate('inference',12,128)
    reserved=ledger.reserve('step1',plan)
    assert ledger.reserved_compute_units==0 and reserved.reserved_compute_units==12
    finished=reserved.settle('step1',actual_compute_units=10,actual_io_bytes=120)
    assert finished.used_compute_units==10 and finished.used_io_bytes==120
    assert finished.open_tickets==() and finished.complete
    with pytest.raises(ValueError): finished.reserve('step1',plan)


def test_v53_fail_closed_on_overbudget_and_overspend():
    ledger=WorkLedger(max_compute_units=15,max_io_bytes=128)
    with pytest.raises(ValueError): ledger.reserve('bad',WorkEstimate('inference',16,50))
    with pytest.raises(ValueError): ledger.reserve('bad',WorkEstimate('inference',10,129))
    reserved=ledger.reserve('step',WorkEstimate('inference',10,100))
    with pytest.raises(ValueError): reserved.settle('step',actual_compute_units=11,actual_io_bytes=90)
    with pytest.raises(ValueError): reserved.settle('step',actual_compute_units=10,actual_io_bytes=101)
    assert reserved.used_compute_units==0 and reserved.reserved_compute_units==10


def test_v53_unknown_real_work_is_not_claimed_metered():
    ledger=WorkLedger(100,1000).reserve('step',WorkEstimate('svd',20,400))
    done=ledger.settle('step',actual_compute_units=None,actual_io_bytes=None)
    assert not done.complete and done.unknown_tickets==('step',)
    assert done.used_compute_units==20 and done.used_io_bytes==400
    assert done.report()['verification']=='UNKNOWN_ACTUAL_WORK'


def test_v53_invalid_spec_and_resource_validation():
    with pytest.raises(ValueError): WorkLedger(True,100)
    with pytest.raises(ValueError): WorkEstimate('inference',-1,100)
    with pytest.raises(ValueError): estimate_kernel('svd',rows=0,cols=2)
    with pytest.raises(ValueError): estimate_kernel('qr',rows=2,cols=4)
    with pytest.raises(ValueError): estimate_kernel('unknown',rows=2,cols=2)
    with pytest.raises(ValueError): WorkLedger(100,100).reserve('../x',WorkEstimate('inference',10,10))


def test_v53_immutable_tickets_limit_and_memory_io():
    ledger=WorkLedger(2000,2000)
    for i in range(8):
        ledger=ledger.reserve('id'+str(i),WorkEstimate('io',0,50))
    assert ledger.reserved_io_bytes==400 and ledger.used_io_bytes==0
    with pytest.raises(ValueError): ledger.reserve('new',WorkEstimate('io',0,1800))
    for i in range(8):
        ledger=ledger.settle('id'+str(i),actual_compute_units=0,actual_io_bytes=50)
    assert ledger.complete and ledger.used_io_bytes==400


def test_v54_frozen_a_b_replay_and_no_oracle_policy():
    report=run_phase0((9100,9129))
    assert report==run_phase0((9100,9129))
    assert report['total_steps']==2*2*240
    assert report['policies']==('A_cycle','B_offset')
    assert report['operator_actions_enabled'] is False
    assert report['frozen_tapes'] is True
    assert set(report['suites'])==set(report['policies'])
    assert all(x['scorer_truth_not_in_policy'] for x in report['per_seed'])


def test_v54_full_30_seed_campaign_reproduces_prior_v48():
    report=run_phase0(PHASE0_SEEDS)
    assert report['total_steps']==14400
    assert report['suites']['A_cycle']['correct']==1788
    assert report['suites']['B_offset']['correct']==1817
    assert report['suites']['A_cycle']['ood']==678
    assert report['suites']['A_cycle']['unconditional_accuracy']<.91
    assert report['meets_source_target'] is False
    assert report['independent_holdout']['seed_count']==10
    assert report['dev']['seed_count']==20
    assert report['unmetered_operation_count']>0
    assert not report['eligible_for_release']


def test_v54_abstention_and_lure_metrics_are_honest():
    report=run_phase0((9100,))
    for value in report['suites'].values():
        assert value['abstentions']==0
        assert value['harm']==0
        assert value['lure_hits']==0
        assert 0<=value['unconditional_accuracy']<=1
        assert value['failures']==value['steps']-value['correct']
    assert report['target_lure_hits']==0
    assert report['suites']['A_cycle']['target_reached'] is False


def test_v54_no_invalid_seeds_or_action_policy_override():
    for bad in ((),(1,1),(True,2),(2**32,),tuple(range(31)),[1,2]):
        with pytest.raises(ValueError): run_phase0(bad)


def test_v52_to_v54_aggregate_clocks_and_belief_integrity():
    report=run_phase0((9274,))
    first=report['per_seed'][0]
    assert first['observer']['belief_updates']==480
    assert first['observer']['temporal_snapshots']==8
    assert len(first['observer']['trace_sha256'])==64
    assert first['observer']['min_belief']>=1e-4-1e-12
    assert report['unmetered_operation_count']>0


def test_v54_result_serialization_repeatability():
    r=run_phase0((9274,))
    raw=json.dumps(r,sort_keys=True,separators=(',',':'),allow_nan=False)
    assert json.loads(raw)['total_steps']==480
    assert raw==json.dumps(run_phase0((9274,)),sort_keys=True,separators=(',',':'),allow_nan=False)


def test_v52_snapshot_is_independent_from_mutation_of_source_event():
    original=ev('immutable',v=1)
    snapshot=temporal_view((original,),tenant='tenant',valid_at=30,known_at=3)
    object.__setattr__(original,'value','hijacked')
    assert snapshot.visible[0].value=='1'
    assert snapshot.trace_sha256==temporal_view((ev('immutable',v=1),),tenant='tenant',valid_at=30,known_at=3).trace_sha256


def test_v54_frozen_policy_tapes_are_not_mutable():
    from omega_x_evolution.ontos_v54_phase0 import TAPES
    with pytest.raises(TypeError):
        TAPES['A_cycle']=(4,)*240
    assert len(TAPES['A_cycle'])==240 and 4 not in TAPES['A_cycle']


def test_v53_tampered_reservation_fails_closed():
    plan=WorkEstimate('svd',64,500)
    ledger=WorkLedger(100,1000).reserve('ticket',plan)
    object.__setattr__(plan,'compute_units',-42)
    with pytest.raises(ValueError): ledger.report()
    with pytest.raises(ValueError): ledger.settle('ticket',actual_compute_units=None,actual_io_bytes=None)


@pytest.mark.parametrize('clock', (1,6,24))
def test_v52_four_clock_window_invariants(clock):
    for t in range(0,150):
        windows=clock_windows(t,clock)
        assert 1<=len(windows)<=4
        assert windows[-1]<=t
        assert all(x%clock==0 for x in windows)
        assert windows==tuple(sorted(set(windows)))


def test_v54_campaign_matches_previous_v37_trace_hash():
    report=run_phase0((9100,9129,9158))
    assert tuple(x['per_suite']['A_cycle']['trace_sha256'] for x in report['per_seed']) == (
        'cff2e2a3574c70ff20bee5ae65bbf918e21c7cf728d0fae1baf338f718ae1ac6',
        'b39f21eed885c15c51373547e299d2eda4140502015618bb20bcd7084fb48234',
        '5bf0e83458cd61edbc8f682fcaee18323b5afeae844629cdc47e2f1c58749aec',
    )


def test_v54_failure_propagates_without_rewriting_scorer_or_fallback(monkeypatch):
    import omega_x_evolution.ontos_v54_phase0 as module
    def fail(seed, tape):
        raise RuntimeError('injected source replay failure')
    monkeypatch.setattr(module,'replay',fail)
    with pytest.raises(RuntimeError,match='injected'):
        module.run_phase0((9100,))
