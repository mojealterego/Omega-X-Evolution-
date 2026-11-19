import pytest
from omega_x_evolution.green import Calibration, Reading, estimate, paired_discovery, counter_energy


def test_exact_units_and_uncertainty():
    c = Calibration(10, 20, 30, 'lab CPU active watts', 400, 'grid inventory 2026')
    e = estimate(Reading(3_600_000_000_000, 3_600_000_000_000), c)
    assert e['energy_wh'] == {'low': 10., 'central': 20., 'high': 30.}
    assert e['carbon_g'] == {'low': 4., 'central': 8., 'high': 12.}
    assert e['method'] == 'estimated-process-cpu'
    assert estimate(Reading(100, 0), c)['energy_wh']['central'] == 0


@pytest.mark.parametrize('params', [(20,10,30,'a',400,'b'), (0,1,float('nan'),'a',400,'b'), (1,2,3,'',400,'b'), (1,2,3,'a',-1,'b')])
def test_invalid_calibration(params):
    with pytest.raises(ValueError): Calibration(*params)


def test_counter_wrap_and_ambiguity():
    assert counter_energy(90, 10, 100, 500, 100) == 20
    assert counter_energy(10, 20, 100, 500, 100) == 10
    with pytest.raises(ValueError): counter_energy(90, 10, 100, 100_000, 100)
    with pytest.raises(ValueError): counter_energy(90, 10, 100, 1, 100)


def test_workload_real_and_paired():
    c = Calibration(5, 10, 20, 'assumed CPU W', 100, 'scenario intensity')
    r = paired_discovery(calibration=c, task='sum', seed=5, budget=16, repeats=2)
    assert r['mode']=='estimated-process-cpu'
    assert len(r['runs']) == 4
    assert [x['strategy'] for x in r['runs']] == ['enumeration','evolution','evolution','enumeration']
    for row in r['runs']:
        assert row['result']['attempts']==16 and row['result']['dataset_sha256']==r['dataset_sha256']
        assert row['reading']['cpu_ns']>0 and row['reading']['wall_ns']>0
        assert row['estimate']['energy_wh']['low'] <= row['estimate']['energy_wh']['high']
    assert r['comparisons']['equal_proposal_budget']
    with pytest.raises(ValueError): paired_discovery(calibration=c, task='sum', budget=4097)
