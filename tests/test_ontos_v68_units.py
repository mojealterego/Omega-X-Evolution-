"""ONTOS L11-v68 deterministic SI accounting / safety tests."""
import math
import random
import pytest

from omega_x_evolution.ontos_v68_units import (
    BOLTZMANN_J_PER_K, bits_to_nats, nats_to_bits,
    landauer_min_j, ThermodynamicEpisode, EnergyAggregate,
)


def test_v68_si_constants_and_1bit_300k_reference():
    assert BOLTZMANN_J_PER_K == 1.380649e-23
    assert landauer_min_j(1, 300.0) == pytest.approx(2.870978885e-21, rel=1e-9)
    assert landauer_min_j(0, 300.0) == 0.0


def test_v68_bits_nats_are_inverse_with_explicit_units():
    for bits in (0.0, 1e-6, 0.5, 1.0, 1e3, 1e8):
        assert nats_to_bits(bits_to_nats(bits)) == pytest.approx(bits)
    assert bits_to_nats(1) == pytest.approx(math.log(2.0))
    assert nats_to_bits(math.log(2.0)) == pytest.approx(1)


@pytest.mark.parametrize('bad', [True, False, -1, -1.0, None, float('inf'), float('nan'), '5', 10**400])
def test_v68_nonnegative_information_rejects_invalid(bad):
    with pytest.raises(ValueError): bits_to_nats(bad)
    with pytest.raises(ValueError): nats_to_bits(bad)


@pytest.mark.parametrize('bad', [0., -1., True, None, float('inf'), float('nan'), '300'])
def test_v68_temperature_must_be_strictly_positive(bad):
    with pytest.raises(ValueError): landauer_min_j(1, bad)


@pytest.mark.parametrize('bad', [-1, True, 1.5, float('nan'), 10**30, '10'])
def test_v68_bit_erasure_is_exact_bounded_integer(bad):
    with pytest.raises(ValueError): landauer_min_j(bad, 300.0)


def test_v68_unknown_erasure_does_not_invent_physical_lower_bound():
    ep = ThermodynamicEpisode(operations=350_000, temperature_k=300.0, information_gain_bits=4.0)
    report = ep.report()
    assert report['operations'] == 350_000
    assert report['irreversibly_erased_bits'] is None
    assert report['landauer_lower_bound_j'] is None
    assert report['wall_energy_j'] is None
    assert report['joules_per_operation'] is None
    assert report['physical_measurement_verified'] is False


def test_v68_operations_not_equated_with_erased_bits():
    no_erasure = ThermodynamicEpisode(operations=350_000, temperature_k=300., erased_bits=0)
    yes_erasure = ThermodynamicEpisode(operations=350_000, temperature_k=300., erased_bits=21)
    assert no_erasure.report()['landauer_lower_bound_j'] == 0
    assert yes_erasure.report()['landauer_lower_bound_j'] == pytest.approx(21 * landauer_min_j(1, 300.))


def test_v68_real_and_scenario_energy_are_different_units_of_evidence():
    sample = ThermodynamicEpisode(operations=350_000, temperature_k=300., erased_bits=2,
                                  core_energy_j=2e-9, wall_energy_j=5e-9, information_gain_bits=1.)
    report = sample.report()
    assert report['core_energy_j'] == pytest.approx(2e-9)
    assert report['wall_energy_j'] == pytest.approx(5e-9)
    assert report['joules_per_operation'] == pytest.approx(5e-9 / 350_000)
    assert report['information_gain_nats'] == pytest.approx(math.log(2))
    assert report['physical_measurement_verified'] is False
    with pytest.raises(ValueError):
        ThermodynamicEpisode(operations=1, temperature_k=300., core_energy_j=5, wall_energy_j=2)


@pytest.mark.parametrize('args', [
    {'operations': True}, {'operations': -1}, {'operations': 1.2},
    {'information_gain_bits': -1}, {'information_gain_bits': float('nan')},
    {'core_energy_j': -1}, {'core_energy_j': float('inf')},
    {'wall_energy_j': float('nan')}, {'erased_bits': -1},
    {'temperature_k': 0}, {'temperature_k': 1e20},
])
def test_v68_episode_domain_rejects_bad_inputs(args):
    with pytest.raises(ValueError): ThermodynamicEpisode(**({'operations': 1, 'temperature_k': 300.} | args))


def test_v68_aggregate_additivity_incomplete_energy_is_unknown():
    a = ThermodynamicEpisode(operations=1, erased_bits=2, temperature_k=300., wall_energy_j=1e-9)
    b = ThermodynamicEpisode(operations=5, erased_bits=3, temperature_k=600.)
    out = EnergyAggregate((a, b)).report()
    assert out['operations'] == 6
    assert out['irreversibly_erased_bits'] == 5
    assert out['landauer_lower_bound_j'] == pytest.approx(8 * landauer_min_j(1, 300.))
    assert out['wall_energy_j'] is None  # no implicit zero for missing values
    assert out['wall_energy_known_episodes'] == 1
    assert out['joules_per_operation'] is None


def test_v68_unknown_erasure_propagates_through_sum():
    known = ThermodynamicEpisode(operations=4, erased_bits=10, temperature_k=300.)
    unknown = ThermodynamicEpisode(operations=8, temperature_k=300.)
    r = EnergyAggregate((known, unknown)).report()
    assert r['operations'] == 12
    assert r['irreversibly_erased_bits'] is None
    assert r['landauer_lower_bound_j'] is None
    assert r['erasure_known_episodes'] == 1


def test_v68_scale_monotonicity_and_order_are_deterministic():
    r = random.Random(68)
    for _ in range(300):
        b = r.randrange(1, 10**7)
        t = r.uniform(1, 2000)
        e = landauer_min_j(b, t)
        assert 0 <= e <= landauer_min_j(b+1, t)
        assert 0 <= e < landauer_min_j(b, 2*t)
        assert landauer_min_j(b*2, t) == pytest.approx(e*2, rel=1e-14)


def test_v68_no_divide_by_zero_and_empty_aggregate():
    z = ThermodynamicEpisode(operations=0, erased_bits=0, temperature_k=300., wall_energy_j=0.)
    assert z.report()['joules_per_operation'] is None
    assert EnergyAggregate(()).report()['operations'] == 0
    assert EnergyAggregate(()).report()['landauer_lower_bound_j'] is None


def test_v68_does_not_claim_power_without_time_or_samples():
    r = ThermodynamicEpisode(operations=100, temperature_k=300., wall_energy_j=3.0).report()
    assert r['wall_power_w'] is None
    assert r['physical_measurement_verified'] is False
