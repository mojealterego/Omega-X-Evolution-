from dataclasses import replace
import pytest
from omega_x_evolution.apex_shield import HTP, Limits, MTJ, ReRAM
from omega_x_evolution.apex_twin import Parameters
from omega_x_evolution.apex_planner import Scenario, Release, evaluate, Plan
from omega_x_evolution.apex_mpc import run_mpc

HOT = Scenario(Limits(100, 43000, 1024, 600000, 650000, 1000), Parameters(42850, 10, 100, 3, 2, 64))
COOL = Scenario(HOT.limits, replace(HOT.parameters, ambient_mc=25000))


def test_replanning_includes_committed_thermal_state():
    work = (MTJ('read', 100),)*3
    out = run_mpc(work, (HOT, COOL), HOT, (0, 1, 20), 60, horizon=2)
    assert out.status == 'COMPLETE'
    assert tuple(e.at_ms for e in out.events) == (0, 20, 40)
    assert out.final == evaluate(work, Plan('replay', out.events), HOT, 60).final
    assert out.replans == 3


def test_robust_admission_even_when_actual_scenario_cool():
    work = (MTJ('read', 100),)*2
    out = run_mpc(work, (HOT, COOL), COOL, (0, 1, 20), 30, horizon=2)
    assert out.status == 'COMPLETE' and out.events[-1].at_ms == 20


def test_stop_without_mutating_unsafe_action():
    work = (MTJ('read', 100),)*2
    out = run_mpc(work, (HOT,), HOT, (0, 1), 30, horizon=1)
    assert out.status == 'STOP' and len(out.events) == 1
    assert out.final.revision == 1


def test_horizon_two_rejects_infeasible_sequence_at_genesis():
    out = run_mpc((MTJ('read', 100),)*2, (HOT,), HOT, (0, 1), 30, horizon=2)
    assert out.status == 'STOP' and out.events == () and out.final.revision == 0


def test_reram_busy_and_resource_release():
    work = (HTP(1024, 0), Release(1024), ReRAM('poll', 0), ReRAM('write', 4), ReRAM('poll', 0), ReRAM('write', 4))
    out = run_mpc(work, (COOL,), COOL, (0, 1, 3), 30, horizon=3)
    assert out.status == 'COMPLETE'
    assert out.events[-2].at_ms >= out.events[-3].at_ms + 3
    assert out.final.vtcm_used_bytes == 0


def test_advisory_delays_do_not_bypass_shield():
    out = run_mpc((MTJ('read', 100),)*2, (HOT,), HOT, (0, 20), 30, horizon=2, advisory=(0, 0))
    assert out.status == 'COMPLETE' and out.events[-1].at_ms == 20
    assert out.advice_rejections >= 1


@pytest.mark.parametrize('kw', [{'horizon': 0}, {'horizon': True}, {'advisory': (99,)}, {'advisory': (True,)}])
def test_invalid_options(kw):
    with pytest.raises(ValueError):
        run_mpc((MTJ('read', 100),), (HOT,), HOT, (0, 20), 30, **kw)


def test_actual_scenario_must_be_in_model_set():
    with pytest.raises(ValueError):
        run_mpc((MTJ('read', 100),), (HOT,), COOL, (0, 20), 30)
