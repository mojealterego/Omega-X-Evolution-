"""Deterministic observability contract tests; real v69 and v71 code exercised."""
import asyncio
import io
import json
import math
import pytest

from omega_x_evolution.ontos_v69_substrate import PowerComponents, SubstrateScenario
from omega_x_evolution.ontos_v71_energy_pareto import (
    Candidate, Interval, Workload, compare,
)
from omega_x_evolution.ontos_observability import (
    AsyncJsonlExporter, make_snapshot, render_jsonl, render_prometheus,
)

SHA = 'c' * 64


def real_scenario(*, complete=True):
    if complete:
        return SubstrateScenario('H100_FP8', 2., PowerComponents(2., 3., 0., 0., 0., 0., 1., 0.), .5, .1)
    return SubstrateScenario('H100_FP8', 2., PowerComponents(core_w=2), None, .1)


def real_pareto():
    work = Workload(SHA, 100, .9)
    scenario = real_scenario()
    candidate = Candidate('candidate-1', SHA, 100, scenario, Interval(.99, 1.))
    return compare(work, (candidate,))


def test_report_bridge_uses_real_v69_and_v71():
    snap = make_snapshot('trial_42', 1, substrate_report=real_scenario().report(),
                         pareto_report=real_pareto(), free_energy_error_nats=.125,
                         generation=3)
    values = dict(snap.metrics)
    assert values['omega_ontos_substrate_wall_energy_j'] == pytest.approx(22.)
    assert values['omega_ontos_substrate_core_energy_j'] == pytest.approx(4.)
    assert values['omega_ontos_pareto_front_size'] == 1
    assert values['omega_ontos_free_energy_error_nats'] == .125
    assert values['omega_ontos_generation'] == 3
    assert snap.physical_measurement_verified is False


def test_known_unknown_not_mapped_to_zero():
    snap = make_snapshot('test', 0, substrate_report=real_scenario(complete=False).report())
    parsed = json.loads(render_jsonl(snap))
    assert parsed['metrics']['omega_ontos_substrate_wall_energy_j'] is None
    assert parsed['known']['omega_ontos_substrate_wall_energy_j'] is False
    exposition = render_prometheus(snap)
    assert 'omega_ontos_substrate_wall_energy_j_known 0' in exposition
    assert '\nomega_ontos_substrate_wall_energy_j ' not in exposition
    assert 'omega_ontos_substrate_core_energy_j 4.0' in exposition


def test_emitted_prometheus_fixed_metric_allowlist():
    snap = make_snapshot('a', 1, substrate_report=real_scenario().report())
    prom = render_prometheus(snap)
    assert prom.startswith('# HELP omega_ontos_substrate_core_energy_j')
    assert 'trial_42' not in prom
    assert '\nomega_ontos_substrate_wall_energy_j 22.0\n' in prom
    assert 'physical_measurement' in prom


def test_jsonl_is_canonical_and_single_line():
    snap = make_snapshot('abc_007', 4, pareto_report=real_pareto())
    one = render_jsonl(snap)
    two = render_jsonl(snap)
    assert one == two and one.endswith('\n')
    assert one.count('\n') == 1
    event = json.loads(one)
    assert event['schema'] == 'omega-ontos-telemetry-v1'
    assert event['run_id'] == 'abc_007'
    assert event['sequence'] == 4
    assert event['physical_measurement_verified'] is False
    assert event['release_authorized'] is False


@pytest.mark.parametrize('bad', ['', 'bad\nmetric 1', 'ab"c', 'ą', 'x'*65, 'x{bad}'])
def test_run_id_prevents_injection(bad):
    with pytest.raises(ValueError): make_snapshot(bad, 0)


@pytest.mark.parametrize('bad', [True, -1, 10**400, 2.2, None])
def test_sequence_is_exact_bounded_integer(bad):
    with pytest.raises(ValueError): make_snapshot('run', bad)


@pytest.mark.parametrize('bad', [True, -1.0, 1e300, 10**400, float('nan'), float('inf')])
def test_free_energy_error_requires_finite_nonnegative_nats(bad):
    with pytest.raises(ValueError): make_snapshot('run', 0, free_energy_error_nats=bad)


def test_no_fake_hardware_verification_from_external_data():
    v = real_scenario().report()
    v['physical_measurement_verified'] = True
    with pytest.raises(ValueError): make_snapshot('r', 0, substrate_report=v)
    r = real_pareto()
    r['release_authorized'] = True
    with pytest.raises(ValueError): make_snapshot('r', 0, pareto_report=r)


def test_tampered_and_invalid_report_rejected():
    v = real_scenario().report()
    v['energy_wall_j'] = -2.
    with pytest.raises(ValueError): make_snapshot('r', 1, substrate_report=v)
    v['energy_wall_j'] = float('nan')
    with pytest.raises(ValueError): make_snapshot('r', 1, substrate_report=v)
    v = real_pareto()
    v['robust_frontier'] = ['x'] * 65
    with pytest.raises(ValueError): make_snapshot('r', 1, pareto_report=v)


def test_episode_energy_and_work_report_bridge():
    episode = {
        'operations': 123,
        'landauer_lower_bound_j': 1e-15,
        'wall_energy_j': None,
        'physical_measurement_verified': False,
    }
    work = {
        'used_compute_units': 123,
        'used_io_bytes': 65536,
        'verification': 'UNKNOWN_ACTUAL_WORK',
        'physical_joules': 'UNKNOWN',
    }
    metrics = dict(make_snapshot('run', 0, episode_report=episode, work_report=work).metrics)
    assert metrics['omega_ontos_work_compute_units'] == 123
    assert metrics['omega_ontos_work_io_bytes'] == 65536
    assert metrics['omega_ontos_landauer_lower_bound_j'] == 1e-15
    assert metrics['omega_ontos_episode_wall_energy_j'] is None


def test_async_exporter_orders_and_checks_sequences():
    async def execute():
        stream=io.StringIO()
        writer=AsyncJsonlExporter(stream)
        await writer.emit(make_snapshot('run', 1))
        await writer.emit(make_snapshot('run', 2))
        await writer.flush()
        with pytest.raises(ValueError):
            await writer.emit(make_snapshot('run', 2))
        assert [json.loads(line)['sequence'] for line in stream.getvalue().splitlines()] == [1,2]
    asyncio.run(execute())


def test_async_exporter_serializes_simultaneous_writers():
    async def execute():
        sink=io.StringIO()
        writer=AsyncJsonlExporter(sink)
        await asyncio.gather(*(writer.emit(make_snapshot(f'r{i}', i)) for i in range(20)))
        assert len(sink.getvalue().splitlines()) == 20
        assert {json.loads(line)['run_id'] for line in sink.getvalue().splitlines()} == {f'r{i}' for i in range(20)}
    asyncio.run(execute())


def test_async_failed_sink_does_not_confirm_sequence():
    class Failed:
        def write(self, data):
            raise OSError('disk exhausted')
        def flush(self): pass
    async def execute():
        writer=AsyncJsonlExporter(Failed())
        with pytest.raises(OSError):
            await writer.emit(make_snapshot('run', 1))
        with pytest.raises(OSError):
            await writer.emit(make_snapshot('run', 1))
    asyncio.run(execute())


def test_async_writer_does_not_silently_accept_partial_writes():
    class Partial:
        def write(self, data): return len(data) // 2
        def flush(self): pass
    async def execute():
        with pytest.raises(OSError):
            await AsyncJsonlExporter(Partial()).emit(make_snapshot('run', 1))
    asyncio.run(execute())


def test_invalid_report_limits_and_inconsistent_core_energy():
    with pytest.raises(ValueError): make_snapshot('run', 0, substrate_report={'source':'OPERATOR_ASSUMED_SCENARIO', **{str(i):i for i in range(65)}})
    r = real_scenario().report()
    r['energy_core_j'] = 23.
    with pytest.raises(ValueError): make_snapshot('run', 0, substrate_report=r)


def test_untrusted_episode_and_work_status_rejected():
    with pytest.raises(ValueError): make_snapshot('run',0,episode_report={'physical_measurement_verified': True})
    with pytest.raises(ValueError): make_snapshot('run',0,work_report={'verification':'PASS', 'physical_joules': 0})
    with pytest.raises(ValueError): make_snapshot('run',0,generation=True)


def test_mutated_frozen_snapshot_fails_validation_and_wrong_type_rejected():
    from omega_x_evolution.ontos_observability import TelemetrySnapshot
    base=make_snapshot('run',1)
    with pytest.raises(ValueError): render_jsonl(object())
    with pytest.raises(ValueError): render_prometheus(object())
    with pytest.raises(ValueError): AsyncJsonlExporter(None)
    object.__setattr__(base,'metrics',tuple(reversed(base.metrics)))
    with pytest.raises(ValueError): render_jsonl(base)
    object.__setattr__(base,'metrics',tuple((k,True if i==0 else v) for i,(k,v) in enumerate(reversed(base.metrics))))
    with pytest.raises(ValueError): render_prometheus(base)


def test_failed_exporter_flush_is_rejected():
    class Failed:
        def write(self, line): raise OSError('io failure')
        def flush(self): pass
    async def execute():
        writer = AsyncJsonlExporter(Failed())
        with pytest.raises(OSError): await writer.emit(make_snapshot('run',1))
        with pytest.raises(OSError): await writer.flush()
    asyncio.run(execute())
