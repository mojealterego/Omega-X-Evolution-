import pytest
from test_ontos_living_memory import batch, evidence, boundary
from omega_x_evolution.ontos_living_profile import profile_diagnostic, profile_review


def test_native_clock_samples_and_deterministic_digest():
    b=batch(); r=profile_diagnostic(b,repeats=3)
    assert r['candidate_sha256']==b.sha256
    assert r['scope']=='OFFLINE_DIAGNOSTIC'
    assert len(r['samples'])==3
    assert r['energy_joules'] is None and r['hardware_flops'] is None
    assert r['peak_memory_bytes'] is None and not r['promotion_authorized']
    for name in ('wall_ns','process_cpu_ns','thread_cpu_ns'):
        values=sorted(x[name] for x in r['samples'])
        assert all(type(x) is int and x>=0 for x in values)
        assert r['median_low'][name]==values[1]
    assert r['result']['predictive_bit_accuracy']==1


@pytest.mark.parametrize('repeats',[0,33,True,1.5])
def test_repeat_budget(repeats):
    with pytest.raises(ValueError): profile_diagnostic(batch(),repeats=repeats)


@pytest.mark.parametrize('alarm',[False,True])
def test_signed_review_measurement_does_not_bypass_gate(alarm):
    b=batch(); p,t,h=evidence(b); bp,m,bh=boundary(p,b,h,alarm)
    r=profile_review(b,p,p.sha256,t,h,bp,bp.sha256,m,bh,repeats=2)
    assert r['scope']=='AUTHENTICATED_REVIEW'
    assert r['result']['decision']==('QUARANTINED_BLOCKED' if alarm else 'QUARANTINED_DIAGNOSTIC')
    assert (r['result']['diagnostic'] is None)==alarm
    assert not r['promotion_authorized']
    with pytest.raises(ValueError): profile_review(b,p,p.sha256,t[:-1],h,bp,bp.sha256,m,bh,repeats=1)
