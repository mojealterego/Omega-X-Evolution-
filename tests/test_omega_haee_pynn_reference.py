"""TDD tests for optional HAEE admission and PyNN-inspired LIF reference."""
import copy
import json
from pathlib import Path

import pytest

from omega_x_evolution.haee_admission import AdmissionPolicy, admit_haee
from omega_x_evolution.pynn_lif_reference import DCPulse, LIFPlan, simulate_lif, compare_spikes

FIXTURES = Path(__file__).resolve().parent / 'fixtures'


def synthetic_examples():
    return (
        json.loads((FIXTURES / 'haee_genome_v1.json').read_text(encoding='utf-8')),
        json.loads((FIXTURES / 'haee_experiment_v1.json').read_text(encoding='utf-8')),
    )


def test_haee_synthetic_examples_admitted_as_research_only():
    g, e = synthetic_examples()
    result = admit_haee(g, e)
    assert len(result.sha256) == 64
    assert result.ordered_nodes[0] == 'input'
    assert result.ordered_nodes[-1] == 'output'
    assert result.can_execute is False
    assert result.can_promote is False
    assert result.shape_compatibility_verified is False


def test_haee_graph_node_and_edge_reordering_has_stable_digest():
    g, e = synthetic_examples()
    original = admit_haee(g, e)
    g['nodes'] = list(reversed(g['nodes']))
    g['edges'] = list(reversed(g['edges']))
    assert original.sha256 == admit_haee(g, e).sha256


@pytest.mark.parametrize('mutation', [
    lambda g, e: g.update(unsafe_code='print(1)'),
    lambda g, e: g['nodes'][0].update(activation='__import__'),
    lambda g, e: g['nodes'][1].update(id='input'),
    lambda g, e: g['nodes'][1].update(shape=[1, 0]),
    lambda g, e: g['nodes'][1].update(shape=[1, 10**400]),
    lambda g, e: g['nodes'][1].update(shape=[1, True]),
    lambda g, e: g['nodes'][1].update(shape=[1, 2, 3, 4, 5, 6, 7]),
    lambda g, e: g['edges'].append({'source': 'output', 'target': 'input', 'delay_steps': 0}),
    lambda g, e: g['edges'].append({'source': 'lost', 'target': 'input', 'delay_steps': 0}),
    lambda g, e: g['edges'].append({'source': 'input', 'target': 'proj', 'delay_steps': 0}),
    lambda g, e: g['edges'][0].update(delay_steps=-1),
    lambda g, e: g['nodes'][0].update(kind='OUTPUT'),
    lambda g, e: g['training'].update(optimizer='SHELL'),
    lambda g, e: g['training'].update(learning_rate=float('nan')),
    lambda g, e: g['limits'].update(max_nodes=1),
    lambda g, e: g['lineage'].update(parent_ids=[''] ),
    lambda g, e: g.update(task_id='different-task'),
    lambda g, e: g.update(genome_id='not-a-uuid'),
    lambda g, e: g['lineage'].update(operator='REMOVE_EDGE'),
])
def test_haee_adversarial_genomes_are_rejected(mutation):
    g, e = synthetic_examples()
    mutation(g, e)
    with pytest.raises(ValueError):
        admit_haee(g, e)


def test_haee_explicit_delayed_edge_is_allowed_but_not_a_zero_delay_cycle():
    g, e = synthetic_examples()
    g['nodes'][1]['kind'] = 'RECURRENT'
    g['edges'].append({'source': 'output', 'target': 'proj', 'delay_steps': 2})
    result = admit_haee(g, e)
    assert result.delayed_edges == 1


@pytest.mark.parametrize('mutation', [
    lambda g, e: e.update(approval_policy='AUTO_PROMOTE'),
    lambda g, e: e.update(allow_external_dataset_egress=True),
    lambda g, e: e.update(secret='value'),
    lambda g, e: e['dataset'].update(train_sha256='invalid'),
    lambda g, e: e.update(max_evaluations=10**400),
    lambda g, e: e.update(max_parallel_evaluations=10000),
    lambda g, e: e.update(objective_ids=['TASK_ERROR','TASK_ERROR']),
    lambda g, e: e.update(allowed_operators=['ARBITRARY_CODE']),
    lambda g, e: e.update(max_wall_clock_minutes=True),
    lambda g, e: e.update(task_id='other'),
])
def test_haee_adversarial_experiments_are_rejected(mutation):
    g, e = synthetic_examples()
    mutation(g, e)
    with pytest.raises(ValueError):
        admit_haee(g, e)


def test_haee_non_baseline_operator_can_be_allowed_by_policy():
    g, e = synthetic_examples()
    g['lineage']['operator'] = 'ADD_NODE'
    g['lineage']['parent_ids'] = ['parent-a']
    assert admit_haee(g, e).can_promote is False


def test_haee_resource_bound_is_fail_closed():
    g, e = synthetic_examples()
    with pytest.raises(ValueError):
        admit_haee(g, e, AdmissionPolicy(max_nodes=2))


def test_pynn_zero_current_no_spikes():
    out = simulate_lif(LIFPlan(dt_ms=1, duration_ms=100, current_na=0))
    assert out.spikes_ms == ()
    assert out.final_v_mv == pytest.approx(-65)
    assert out.backend == 'OFFLINE_LIF_ANALYTIC'
    assert out.pynn_native_verified is False


def test_pynn_suprathreshold_current_spikes_and_refractory():
    plan = LIFPlan(dt_ms=1, duration_ms=100, current_na=1.0, tau_m_ms=20, resistance_mohm=20)
    out = simulate_lif(plan)
    assert len(out.spikes_ms) >= 2
    assert all(b-a >= plan.refractory_ms for a,b in zip(out.spikes_ms,out.spikes_ms[1:]))
    assert all(0 <= t <= 100 for t in out.spikes_ms)


def test_pynn_split_run_equals_single_run_and_reset_replay():
    plan = LIFPlan(dt_ms=1, duration_ms=100, current_na=1.0, tau_m_ms=10)
    whole = simulate_lif(plan)
    one = simulate_lif(plan, segments_ms=(20,35,45))
    assert one == whole
    assert simulate_lif(plan) == whole


def test_pynn_step_source_delays_onset():
    plan = LIFPlan(dt_ms=1, duration_ms=100, current_na=0,
                   pulses=(DCPulse(start_ms=30, stop_ms=90, amplitude_na=1.0),))
    out = simulate_lif(plan)
    assert out.spikes_ms
    assert min(out.spikes_ms) >= 30
    assert max(out.spikes_ms) <= 100


@pytest.mark.parametrize('plan', [
    dict(dt_ms=0), dict(duration_ms=10**400), dict(dt_ms=float('nan')),
    dict(duration_ms=1.2), dict(v_threshold_mv=-80),
    dict(current_na=float('inf')), dict(refractory_ms=-1),
    dict(pulses=(DCPulse(0,1,1),),dt_ms=3),
])
def test_pynn_invalid_plan_is_rejected(plan):
    with pytest.raises(ValueError):
        LIFPlan(**plan)


def test_pynn_spike_comparison_rejects_incomplete_or_shifted_backend_trace():
    expected = simulate_lif(LIFPlan(dt_ms=1,duration_ms=70,current_na=1))
    assert compare_spikes(expected.spikes_ms,expected.spikes_ms,tolerance_ms=0.0) is True
    assert compare_spikes(expected.spikes_ms,tuple(t+2 for t in expected.spikes_ms),tolerance_ms=.5) is False
    assert compare_spikes(expected.spikes_ms,(),tolerance_ms=.5) is False
    with pytest.raises(ValueError):
        compare_spikes(expected.spikes_ms,(float('nan'),),tolerance_ms=.5)


def test_pynn_exact_leak_solution_below_threshold():
    import math
    plan = LIFPlan(dt_ms=1,duration_ms=1,current_na=.25,tau_m_ms=20,resistance_mohm=20)
    result = simulate_lif(plan)
    assert result.spikes_ms == ()
    assert result.final_v_mv == pytest.approx(-65 + 5*(1-math.exp(-1/20)),abs=1e-12)


def test_haee_rejects_unreachable_output_without_side_effects():
    g, e = synthetic_examples()
    g['edges'] = [g['edges'][0]]
    with pytest.raises(ValueError, match='unreachable'):
        admit_haee(g, e)


def test_haee_rejects_experiment_budget_overrun_before_running():
    g, e = synthetic_examples()
    e['max_evaluations'] = 200
    e['max_parallel_evaluations'] = 201
    with pytest.raises(ValueError, match='quotas'):
        admit_haee(g, e)


def test_haee_digest_is_bound_to_restrictive_admission_policy():
    g, e = synthetic_examples()
    a = admit_haee(g, e)
    b = admit_haee(g, e, AdmissionPolicy(max_nodes=100))
    assert a.sha256 != b.sha256
    assert a.can_promote is False and b.can_promote is False


def test_pynn_rejects_incorrect_segment_boundary_and_reversed_spikes():
    plan = LIFPlan(dt_ms=1, duration_ms=100, current_na=1)
    with pytest.raises(ValueError):
        simulate_lif(plan,segments_ms=(30,30))
    with pytest.raises(ValueError):
        simulate_lif(plan,segments_ms=(20,.5,79.5))
    with pytest.raises(ValueError):
        compare_spikes((10.,9.),(9.,10.))
