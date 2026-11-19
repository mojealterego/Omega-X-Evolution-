import pytest
from omega_x_evolution.benchmarks import compare

def test_paired_equal_budget():
    a=compare(seeds=(81,82),budget=60,tasks=('sum','product'))
    assert a==compare(seeds=(81,82),budget=60,tasks=('sum','product'))
    assert len(a['runs'])==12
    assert {r['strategy'] for r in a['runs']}=={'enumeration','random','evolution'}
    assert all(r['attempts']==60 for r in a['runs'])
    assert all(r['pairs']==4 for r in a['comparisons'])
    assert a['external_systems_compared']==[]

def test_limits():
    with pytest.raises(ValueError): compare(seeds=(4,4))
    with pytest.raises(ValueError): compare(tasks=('fake',))
    with pytest.raises(ValueError): compare(budget=0)
