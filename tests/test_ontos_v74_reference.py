from dataclasses import replace
import pytest
from omega_x_evolution.ontos_v74_reference import reference_plan, execute_seed, run_reference


def test_reference_grid_and_frozen_digest():
    plan = reference_plan()
    assert len(plan.configurations) == 60 and len(plan.seeds) == 30
    assert len({c.artifact_sha256 for c in plan.configurations}) == 60
    with pytest.raises(ValueError): run_reference('0'*64)


def test_seed_runs_real_engines_and_broker():
    p = reference_plan()
    runs, details = execute_seed(p,p.seeds[0])
    assert len(runs) == len(details) == 60
    assert {r.configuration for r in runs} == {c.name for c in p.configurations}
    assert all(r.status == 'COMPLETED' for r in runs)
    assert all(0 <= r.correct <= 240 for r in runs)
    assert all(d['broker_report_sha256'] for d in details if d['suite']=='C')
    assert all(d['false_accepts']+d['correct']==240 for d in details if d['suite']=='D')
    assert (runs, details) == execute_seed(p,p.seeds[0])


def test_unregistered_seed_and_modified_plan_rejected():
    p = reference_plan()
    with pytest.raises(ValueError): execute_seed(p,0)
    with pytest.raises(ValueError): execute_seed(replace(p,analysis_seed=42),p.seeds[0])
