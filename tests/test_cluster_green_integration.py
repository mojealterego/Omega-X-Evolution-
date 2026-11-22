"""GCL-E2E: native MAP-Elites runner integration. Requires complete repository.

These tests must run against the real cluster, store, and thread/backend code;
no substitute runner is supplied. CI/test environment must provide dependencies.
"""
from __future__ import annotations

import asyncio

from omega_x_evolution.cluster import ClusterConfig, LocalBackend, Store, run_cluster
from omega_x_evolution.cluster_green import WorkerPowerScenario
from omega_x_evolution.performance import Policy


PROFILE = WorkerPowerScenario(2, 3, 4, 450, 'reference-active-thread-power',
                              'reference-grid-intensity')


def test_gcl_e2e_two_islands_commit_after_actual_actor_work(tmp_path):
    cfg = ClusterConfig(islands=2, rounds=2, batch=1, budget=8,
                        parallelism=2, seed=35, timeout=60)
    store = Store(tmp_path / 'cluster.sqlite', b'a'*32, cfg).initialize()
    with LocalBackend(cfg, processes=False) as backend:
        result = asyncio.run(run_cluster(store, backend, green=PROFILE))
    green = result['green_computing']
    assert result['complete'] is True
    assert green['new_commits'] == result['commits'] == 6
    assert green['unobserved_commits'] == 0
    assert green['measured_commits'] == 6
    assert green['whole_history_complete'] is True
    assert green['energy_cpu_wh']['central'] > 0
    assert green['energy_cpu_wh']['low'] <= green['energy_cpu_wh']['central']
    assert green['energy_cpu_wh']['high'] >= green['energy_cpu_wh']['central']
    assert green['attempts'] == result['attempts']
    assert green['rejections'] == result['rejections']
    assert green['release_authorized'] is False


def test_gcl_e2e_resume_does_not_claim_previous_cpu_energy(tmp_path):
    cfg = ClusterConfig(islands=2, rounds=2, batch=1, budget=8,
                        parallelism=2, seed=36, timeout=60)
    store = Store(tmp_path / 'cluster.sqlite', b'b'*32, cfg).initialize()
    with LocalBackend(cfg, processes=False) as backend:
        first = asyncio.run(run_cluster(store, backend, stop_after=2, green=PROFILE))
    assert first['green_computing']['new_commits'] == 2
    with LocalBackend(cfg, processes=False) as backend:
        second = asyncio.run(run_cluster(store, backend, green=PROFILE))
    assert second['complete'] is True
    assert second['green_computing']['previous_commits_unknown'] == 2
    assert second['green_computing']['whole_history_complete'] is False
    assert second['green_computing']['new_commits'] == second['commits'] - 2


def test_gcl_e2e_default_runner_contract_unchanged(tmp_path):
    cfg = ClusterConfig(islands=1, rounds=1, batch=1, budget=2,
                        parallelism=1, seed=37, timeout=60)
    store = Store(tmp_path / 'cluster.sqlite', b'c'*32, cfg).initialize()
    with LocalBackend(cfg, processes=False) as backend:
        plain = asyncio.run(run_cluster(store, backend))
    assert 'green_computing' not in plain
    assert plain['complete'] is True


def test_gcl_e2e_performance_gate_counts_are_not_promoted_by_telemetry(tmp_path):
    cfg = ClusterConfig(islands=1, rounds=1, batch=1, budget=2,
                        parallelism=1, seed=38, timeout=60,
                        policy=Policy())
    store = Store(tmp_path / 'cluster.sqlite', b'd'*32, cfg).initialize()
    with LocalBackend(cfg, processes=False) as backend:
        result = asyncio.run(run_cluster(store, backend, green=PROFILE))
    green = result['green_computing']
    assert green['performance_profiled'] == result['performance_profiled']
    assert green['performance_regression_rejections'] == result['performance_rejections']
    assert result['complete'] is True
    assert green['release_authorized'] is False
