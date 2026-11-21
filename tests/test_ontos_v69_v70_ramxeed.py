"""V69/V70 bounded real-code tests against vendor facts and fault scenarios.

Device constants: RAMXEED MB85RQ8MX DS501-00074-1v1-E (page 1).
"""
from __future__ import annotations

import math
import random
import pytest

from omega_x_evolution.ontos_v69_substrate import (
    SUBSTRATES, FeRAMSegment, FeRAMSupplyScenario, PowerComponents, SubstrateScenario,
)
from omega_x_evolution.ontos_v70_endurance import (
    Access, EnduranceExceeded, FeRAMWear, rated_cycle_budget, predict_hotspot,
)


@pytest.mark.parametrize('family', sorted(SUBSTRATES))
def test_v69_all_six_heterogeneous_families_admit_explicit_scenario(family):
    s = SubstrateScenario(family, 0.1, PowerComponents(1, 2, 3, 4, 5, 6, 7, 8), 0.8, None)
    r = s.report()
    assert r['substrate'] == family
    assert r['energy_core_j'] == pytest.approx(0.1)
    assert r['energy_wall_j'] == pytest.approx(((1+2+3+4+5+6)/.8 + 7+8)*.1)
    assert r['physical_measurement_verified'] is False
    assert r['uncertainty_interval_wall_j'] is None


def test_v69_unknown_components_never_implicitly_zero():
    p = PowerComponents(core_w=5, memory_w=1)
    r = SubstrateScenario('H100_FP8', .5, p, 0.9, 0.15).report()
    assert r['power_wall_w'] is None
    assert r['energy_wall_j'] is None
    assert r['energy_core_j'] == pytest.approx(2.5)
    assert r['uncertainty_interval_wall_j'] is None


def test_v69_scenario_uncertainty_interval_and_no_claim_of_calibration():
    p = PowerComponents(1,2,0,0,0,0,0,0)
    r = SubstrateScenario('RRAM_PCM', 2., p, 0.75, 0.1).report()
    assert r['power_wall_w'] == pytest.approx(4.)
    assert r['energy_wall_j'] == pytest.approx(8.)
    assert r['uncertainty_interval_wall_j'] == pytest.approx((7.2,8.8))
    assert r['uncertainty_type'] == 'operator_sensitivity_not_calibrated_CI'


@pytest.mark.parametrize('bad', [0., -1., 1.001, float('nan'), True])
def test_v69_reject_psu_efficiency_not_in_0_1(bad):
    with pytest.raises(ValueError):
        SubstrateScenario('H100_FP8',1,PowerComponents(0,0,0,0,0,0,0,0),bad,None)


@pytest.mark.parametrize('bad', [float('inf'), float('nan'), -1, True, 1e60])
def test_v69_invalid_physical_power_rejected(bad):
    with pytest.raises(ValueError): PowerComponents(core_w=bad)


def test_v69_unknown_efficiency_keeps_wall_energy_unknown():
    r=SubstrateScenario('H100_FP8',1., PowerComponents(1,1,0,0,0,0,0,0),None,None).report()
    assert r['energy_wall_j'] is None


def test_v69_fram_chip_spec_max_currents_and_bandwidth():
    active = FeRAMSegment('quad_active_108mhz', 0.02, bytes_transferred=1_048_576)
    idle = FeRAMSegment('standby', 1.)
    sleep = FeRAMSegment('deep_power_down', 2.)
    hibernate = FeRAMSegment('hibernation', 3.)
    out = FeRAMSupplyScenario(3.6, (active,idle,sleep,hibernate)).report()
    upper_j = 3.6 * (0.018*.02 + .000180*1 + .000010*2 + .000005*3)
    assert out['supply_energy_upper_j'] == pytest.approx(upper_j)
    assert out['physical_measurement_verified'] is False
    assert out['wall_energy_j'] is None
    assert out['bytes_transferred'] == 1_048_576
    assert out['throughput_claim_mb_s'] == 54.


def test_v69_fram_invalid_too_short_transfer_rejected():
    with pytest.raises(ValueError): FeRAMSegment('quad_active_108mhz', 0.001, bytes_transferred=1_048_576)
    with pytest.raises(ValueError): FeRAMSegment('standby', 1., bytes_transferred=1)
    with pytest.raises(ValueError): FeRAMSegment('quad_active_108mhz', 1., bytes_transferred=1_048_577)


@pytest.mark.parametrize('bad', [2.69,3.61,True,float('nan'),float('inf'),'3.3'])
def test_v69_supply_must_be_in_vendor_range(bad):
    with pytest.raises(ValueError): FeRAMSupplyScenario(bad, (FeRAMSegment('standby',1),))


def test_v69_fram_merged_into_system_only_as_explicit_memory_budget():
    f = FeRAMSupplyScenario(3.6,(FeRAMSegment('standby', 2),)).report()
    watts = f['supply_energy_upper_j']/2
    r = SubstrateScenario('SOT_MRAM', 2, PowerComponents(1,watts,0,0,0,0,0,0),1,0).report()
    assert r['energy_wall_j'] == pytest.approx(2+f['supply_energy_upper_j'])
    assert f['wall_energy_j'] is None  # Chip supply != wall plug


def test_v70_vendor_temperature_qualified_endurance():
    assert rated_cycle_budget(85) == 10**14
    assert rated_cycle_budget(105) == 10**13
    assert rated_cycle_budget(55) is None
    assert rated_cycle_budget(100) is None  # no interpolation or extrapolation


@pytest.mark.parametrize('t', [-45.,125.,float('nan'),True,None])
def test_v70_invalid_temperature_is_not_a_qualified_device(t):
    with pytest.raises(ValueError): FeRAMWear(t)


def test_v70_sparse_wear_uses_both_reads_and_writes_per_cell():
    s = FeRAMWear(85)
    s, a = s.apply(Access('write', 100, 2, 3))
    assert a['complete'] is True
    s, b = s.apply(Access('read', 101, 3, 2))
    assert s.count_for(100) == 3
    assert s.count_for(101) == 5
    assert s.count_for(102) == 2
    assert s.count_for(103) == 2
    assert s.report()['used_cells'] == 4
    assert s.report()['qualified_endurance_cycles'] == 10**14


def test_v70_interrupted_multibyte_write_can_be_torn():
    s=FeRAMWear(105)
    damaged, result = s.apply(Access('write',20,4,1), interrupted_after_bytes=2)
    assert result['complete'] is False
    assert result['torn_write_possible'] is True
    assert result['bytes_accounted'] == 2
    assert [damaged.count_for(i) for i in range(20,24)] == [1,1,0,0]
    assert all(s.count_for(i)==0 for i in range(20,24))


def test_v70_limit_is_enforced_fail_closed_without_partial_mutation():
    s = FeRAMWear(105)
    s, _ = s.apply(Access('write',0,1,10**13))
    with pytest.raises(EnduranceExceeded):
        s.apply(Access('write',0,1,1))
    assert s.count_for(0) == 10**13


def test_v70_out_of_range_and_repetition_limit_rejected():
    for args in [('write',1_048_576,1,1),('write',1_048_570,8,1),
                 ('write',0,4097,1),('read',0,1,10**15),('execute',0,1,1)]:
        with pytest.raises(ValueError): Access(*args)
    with pytest.raises(ValueError): FeRAMWear(85).apply(Access('write',0,4),interrupted_after_bytes=5)


def test_v70_100hz_5years_source_qualified_model_only():
    r=predict_hotspot(temperature_c=105,events_hz=100,years=5)
    assert r['projected_cycles'] == 15_778_800_000
    assert r['endurance_budget_cycles'] == 10**13
    assert r['within_rated_cycles_model'] is True
    assert r['physical_lifetime_verified'] is False
    assert r['retention_requirement_verified'] is False


def test_v70_unqualified_temperature_keeps_result_unknown():
    r=predict_hotspot(temperature_c=55,events_hz=100,years=5)
    assert r['within_rated_cycles_model'] is None
    assert r['endurance_budget_cycles'] is None


def test_v70_monotonicity_over_randomized_hotspots():
    rng=random.Random(70)
    for _ in range(300):
        start=rng.randrange(1,1_000_000)
        count=rng.randrange(1,10000)
        s=FeRAMWear(85)
        s,_=s.apply(Access('write',start,1,count))
        s2,_=s.apply(Access('read',start,1,1))
        assert s2.count_for(start)==s.count_for(start)+1
        assert s2.report()['remaining_worst_cell_cycles']<=s.report()['remaining_worst_cell_cycles']


def test_v70_unknown_device_retention_is_not_fabricated():
    assert FeRAMWear(85).report()['retention_years_at_temperature'] is None
    assert FeRAMWear(105).report()['retention_years_at_temperature']==10


def test_v70_extreme_integer_inputs_fail_closed_with_value_error():
    huge = 10**400
    with pytest.raises(ValueError): FeRAMWear(huge)
    with pytest.raises(ValueError): rated_cycle_budget(huge)
    with pytest.raises(ValueError): predict_hotspot(temperature_c=85, events_hz=huge, years=1)
    with pytest.raises(ValueError): predict_hotspot(temperature_c=85, events_hz=1, years=huge)


def test_v70_mutated_frozen_registry_rejected_on_report():
    model = FeRAMWear(85)
    object.__setattr__(model, 'temperature_c', 10**400)
    with pytest.raises(ValueError): model.report()
