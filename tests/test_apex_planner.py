from dataclasses import replace
import pytest
from omega_x_evolution.apex_shield import Limits, HTP, ReRAM, MTJ
from omega_x_evolution.apex_twin import Parameters
from omega_x_evolution.apex_planner import Scenario, Event, Release, Plan, evaluate, choose, train, recommend

L = Limits(100, 43000, 1024, 600000, 650000, 1000)
P = Parameters(42850, 10, 100, 3, 2, 64)
S = Scenario(L, P)
W = (MTJ('read', 100), MTJ('read', 100))
FAST = Plan('fast', (Event(0, W[0]), Event(1, W[1])))
SAFE = Plan('safe', (Event(0, W[0]), Event(20, W[1])))


def test_mpc_uses_real_twin_and_veto():
    result = choose(W, (FAST, SAFE), (S,), 30)
    assert result.plan == SAFE
    assert result.worst_finish_ms == 20
    assert evaluate(W, FAST, S, 30) is None
    assert choose(W, (FAST,), (S,), 30) is None


def test_robust_scenarios_not_mean():
    cool = Scenario(L, replace(P, ambient_mc=25000))
    assert choose(W, (FAST, SAFE), (cool,), 30).plan == FAST
    assert choose(W, (FAST, SAFE), (cool, S), 30).plan == SAFE


def test_workload_mismatch_and_deadline():
    assert evaluate(W, Plan('skip', (Event(0, W[0]),)), S, 30) is None
    assert evaluate(W, SAFE, S, 19) is None
    assert evaluate(W, Plan('swap', (Event(0, MTJ('read', 99)), Event(20, W[1]))), S, 30) is None


def test_reram_poll_and_htp_release():
    work = (ReRAM('poll', 0), ReRAM('write', 4), HTP(1024, 0), Release(1024))
    plan = Plan('io', tuple(Event(i*20, a) for i, a in enumerate(work)))
    result = evaluate(work, plan, Scenario(L, replace(P, ambient_mc=25000)), 100)
    assert result is not None and result.finish_ms == 60


def test_offline_table_is_conservative_and_live_revalidated():
    cool = Scenario(L, replace(P, ambient_mc=25000))
    table = train(W, (FAST, SAFE), (cool,), 30)
    assert recommend(W, (FAST, SAFE), (S,), 30, table).plan == SAFE
    assert recommend(W, (FAST,), (S,), 30, table) is None
    assert recommend((MTJ('read', 99),), (FAST,), (S,), 30, table) is None


def test_training_rejects_unknown_plan_and_failed_scenario():
    table = train(W, (FAST, SAFE), (S,), 30)
    assert len(table.entries) == 1
    renamed = Plan('new', SAFE.events)
    assert recommend(W, (renamed,), (S,), 30, table) is None


def test_replay_identical_and_deterministic_tie():
    a = Plan('a', SAFE.events)
    b = Plan('b', SAFE.events)
    assert choose(W, (b, a), (S,), 30) == choose(W, (a, b), (S,), 30)
    assert choose(W, (b, a), (S,), 30).plan == a


@pytest.mark.parametrize('plan', [Plan('x', (Event(True, W[0]), Event(20, W[1]))), Plan('x', (Event(20, W[0]), Event(0, W[1]))), Plan('x', (Event(0, object()), Event(20, W[1])))])
def test_invalid_events_fail_closed(plan):
    assert evaluate(W, plan, S, 30) is None
