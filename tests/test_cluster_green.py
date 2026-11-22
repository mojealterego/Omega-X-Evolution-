"""GCL-001..: deterministic contract tests for optional cluster CPU energy ledger."""
from __future__ import annotations
import json
import math
import pytest

from omega_x_evolution.cluster_green import (
    WorkerPowerScenario, GreenLedger, Reading, make_reading, render_jsonl,
    render_prometheus, sample_worker_step,
)

PROFILE = WorkerPowerScenario(2.0, 3.0, 4.0, 450.0, 'operator-CPU-power', 'operator-grid-intensity')


def new_ledger(*, islands=2, revisions=(0,0)):
    return GreenLedger(PROFILE, islands=islands, initial_revisions=revisions)


def test_gcl_real_duration_and_cpu_scenario_units():
    r = Reading(wall_ns=2_000_000_000, cpu_ns=1_000_000_000)
    ledger = new_ledger()
    ledger.commit(0, 1, r, attempts=3, rejections=1, profiled=2, perf_rejected=1)
    rep = ledger.report()
    assert rep['energy_cpu_wh']['low'] == pytest.approx(2/3600)
    assert rep['energy_cpu_wh']['central'] == pytest.approx(3/3600)
    assert rep['energy_cpu_wh']['high'] == pytest.approx(4/3600)
    assert rep['carbon_cpu_g']['central'] == pytest.approx((3/3600)*450/1000)
    assert rep['worker_cpu_s'] == 1.0
    assert rep['worker_wall_s'] == 2.0
    assert rep['islands'][0]['attempts'] == 3
    assert rep['islands'][0]['performance_regression_rejections'] == 1
    assert rep['physical_measurement_verified'] is False
    assert rep['release_authorized'] is False


def test_gcl_unmeasured_worker_never_becomes_zero():
    ledger = new_ledger(islands=1, revisions=(0,))
    ledger.commit(0, 1, Reading(1_000_000_000, None), attempts=0, rejections=0, profiled=0, perf_rejected=0)
    rep=ledger.report()
    assert rep['energy_cpu_wh'] is None
    assert rep['carbon_cpu_g'] is None
    assert rep['measured_commits']==0
    assert rep['unknown_commits']==1
    assert rep['worker_cpu_s'] is None
    assert 'omega_cluster_cpu_energy_wh_known 0' in render_prometheus(rep)


def test_gcl_one_unknown_prevents_false_complete_total():
    ledger = new_ledger(islands=2)
    ledger.commit(0,1,Reading(10,10),attempts=1,rejections=0,profiled=0,perf_rejected=0)
    ledger.commit(1,1,Reading(100,None),attempts=1,rejections=1,profiled=0,perf_rejected=0)
    rep=ledger.report()
    assert rep['new_commits']==2
    assert rep['measured_commits']==1
    assert rep['energy_cpu_wh'] is None
    assert rep['measured_cpu_energy_partial_wh']['central'] > 0
    assert rep['islands'][1]['energy_cpu_wh'] is None


def test_gcl_dedup_and_revision_contiguity():
    ledger=new_ledger(islands=1,revisions=(0,))
    ledger.commit(0,1,Reading(200,150),attempts=1,rejections=0,profiled=0,perf_rejected=0)
    with pytest.raises(ValueError,match='revision'):
        ledger.commit(0,1,Reading(200,150),attempts=1,rejections=0,profiled=0,perf_rejected=0)
    with pytest.raises(ValueError,match='revision'):
        ledger.commit(0,3,Reading(200,150),attempts=1,rejections=0,profiled=0,perf_rejected=0)
    assert ledger.report()['new_commits']==1


def test_gcl_restart_does_not_claim_historical_energy():
    l=new_ledger(islands=1,revisions=(12,))
    l.commit(0,13,Reading(100000,50000),attempts=1,rejections=0,profiled=0,perf_rejected=0)
    r=l.report()
    assert r['previous_commits_unknown']==12
    assert r['whole_history_complete'] is False
    assert r['new_commits']==1
    assert r['energy_cpu_wh'] is not None


def test_gcl_report_jsonlines_canonical_no_secrets():
    l=new_ledger(islands=1,revisions=(0,))
    l.commit(0,1,Reading(10,8),attempts=0,rejections=0,profiled=0,perf_rejected=0)
    line=render_jsonl(l.report())
    assert line.count('\n')==1 and line.endswith('\n')
    o=json.loads(line)
    assert o['schema']=='omega-cluster-green-v1'
    assert o['source']=='OPERATOR_SCENARIO_THREAD_CPU'
    assert 'code' not in o and 'prompts' not in o
    assert o['energy_cpu_wh']['central'] is not None


def test_gcl_prometheus_no_dynamic_labels_cardinality():
    l=new_ledger(islands=1,revisions=(0,))
    s=render_prometheus(l.report())
    assert 'omega_cluster_cpu_energy_wh_known 1' in s  # no commits, sum well-defined zero
    assert 'omega_cluster_worker_cpu_seconds 0.0' in s
    assert '{' not in s and '\n# HELP ' in s


def test_gcl_oversized_and_invalid_numbers_rejected():
    for bad in (True, -1, float('nan'), float('inf'), 10**400):
        with pytest.raises(ValueError): WorkerPowerScenario(bad,3,4,100,'p','i')
        with pytest.raises(ValueError): WorkerPowerScenario(1,2,3,bad,'p','i')
    with pytest.raises(ValueError): WorkerPowerScenario(4,3,2,100,'p','i')
    with pytest.raises(ValueError): WorkerPowerScenario(1,2,3,100,'has\nnewline','i')
    with pytest.raises(ValueError): WorkerPowerScenario(1,2,3,100,'p','secret=abc')


def test_gcl_invalid_reading_rejected():
    for bad in (True, -1, 10**400, 1.0, float('nan')):
        with pytest.raises(ValueError): Reading(100,bad)
        with pytest.raises(ValueError): Reading(bad,100)
    with pytest.raises(ValueError): Reading(10,100000)


def test_gcl_invalid_commit_is_atomic():
    l=new_ledger(islands=1,revisions=(0,))
    with pytest.raises(ValueError): l.commit(0,1,Reading(100,50),attempts=1,rejections=2,profiled=0,perf_rejected=0)
    assert l.report()['new_commits']==0
    with pytest.raises(ValueError): l.commit(0,1,Reading(100,50),attempts=1,rejections=0,profiled=0,perf_rejected=1)
    assert l.report()['new_commits']==0
    l.commit(0,1,Reading(100,50),attempts=1,rejections=0,profiled=0,perf_rejected=0)
    assert l.report()['new_commits']==1


def test_gcl_many_islands_aggregation_and_isolation():
    l = new_ledger(islands=4,revisions=(2,1,0,0))
    for i,rev in enumerate((3,2,1,1)):
        l.commit(i,rev,Reading(1000*(i+1),500*(i+1)),attempts=i,rejections=0,profiled=0,perf_rejected=0)
    rep=l.report()
    assert rep['new_commits']==4
    assert rep['islands'][2]['worker_cpu_s']==1500/1e9
    assert rep['worker_cpu_s']==500*(1+2+3+4)/1e9
    assert rep['previous_commits_unknown']==3


def test_gcl_bounded_islands_and_refuse_bad_revisions():
    with pytest.raises(ValueError): GreenLedger(PROFILE,islands=0,initial_revisions=())
    with pytest.raises(ValueError): GreenLedger(PROFILE,islands=2,initial_revisions=(0,))
    with pytest.raises(ValueError): GreenLedger(PROFILE,islands=1,initial_revisions=(True,))
    with pytest.raises(ValueError): GreenLedger(PROFILE,islands=513,initial_revisions=(0,)*513)
    l=new_ledger(islands=1,revisions=(0,))
    with pytest.raises(ValueError): l.commit(True,1,Reading(10,5),attempts=0,rejections=0,profiled=0,perf_rejected=0)


def test_gcl_cpu_zero_is_real_zero():
    l=new_ledger(islands=1,revisions=(0,))
    l.commit(0,1,Reading(1000,0),attempts=0,rejections=0,profiled=0,perf_rejected=0)
    r=l.report()
    assert r['worker_cpu_s']==0.0
    assert r['energy_cpu_wh']['central']==0.0
    assert r['measured_commits']==1


def test_gcl_worker_step_call_records_real_time_and_exception_propagates():
    def work(v):
        n=0
        for i in range(300): n+=i
        return {'state':{'n':n,'arg':v},'pid':1}
    result=sample_worker_step(work,4)
    assert result['state']['arg']==4
    assert result['green_reading']['wall_ns']>0
    assert result['green_reading']['cpu_ns'] is None or result['green_reading']['cpu_ns']>=0
    with pytest.raises(RuntimeError,match='boom'):
        sample_worker_step(lambda: (_ for _ in ()).throw(RuntimeError('boom')))


def test_gcl_failures_during_optional_observation_do_not_promote():
    l=new_ledger(islands=1,revisions=(0,))
    l.commit(0,1,Reading(100,None),attempts=1,rejections=1,profiled=0,perf_rejected=0)
    assert l.report()['release_authorized'] is False
    assert l.report()['unknown_commits']==1


def test_gcl_invariant_performance_rejections_are_counted():
    l=new_ledger(islands=1,revisions=(0,))
    l.commit(0,1,Reading(100,70),attempts=8,rejections=3,profiled=5,perf_rejected=2)
    r=l.report()
    assert r['islands'][0]['attempts']==8
    assert r['islands'][0]['rejections']==3
    assert r['islands'][0]['performance_profiled']==5
    assert r['islands'][0]['performance_regression_rejections']==2


def test_gcl_empty_run_is_zero_not_fake_measurement():
    r=new_ledger(islands=1,revisions=(0,)).report()
    assert r['energy_cpu_wh']['central']==0.0
    assert r['measured_commits']==0
    assert r['whole_history_complete'] is True
    assert r['physical_measurement_verified'] is False


def test_gcl_corrupted_or_unavailable_worker_clock_remains_unknown():
    l=new_ledger(islands=1,revisions=(0,))
    l.commit(0,1,None,attempts=2,rejections=1,profiled=0,perf_rejected=0)
    r=l.report()
    assert r['worker_wall_s'] is None
    assert r['worker_cpu_s'] is None
    assert r['energy_cpu_wh'] is None
    assert r['unknown_commits']==1
    assert r['attempts']==2


def test_gcl_missing_committed_telemetry_never_claims_complete_energy():
    l=new_ledger(islands=1,revisions=(0,))
    l.commit(0,1,Reading(100,75),attempts=1,rejections=0,profiled=0,perf_rejected=0)
    r=l.report(expected_commits=2)
    assert r['unobserved_commits']==1
    assert r['worker_wall_s'] is None
    assert r['energy_cpu_wh'] is None
    assert r['whole_history_complete'] is False
    with pytest.raises(ValueError): l.report(expected_commits=0)
