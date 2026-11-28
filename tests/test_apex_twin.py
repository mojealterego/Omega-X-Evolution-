import pytest
from omega_x_evolution.apex_shield import Limits, HTP, FeRAM, ReRAM, MTJ
from omega_x_evolution.apex_twin import Twin, Parameters

L = Limits(100, 43000, 1024, 600000, 650000, 1000)
P = Parameters(25000, 10, 100, 3, 2, 64)


def twin():
    return Twin(L, P)


def test_vtcm_and_revision():
    t = twin()
    assert t.step(0, 0, HTP(1024, 0)).allowed
    assert not t.step(0, 0, HTP(1, 0)).allowed
    assert not t.step(1, 0, HTP(1, 0)).allowed
    assert t.snapshot.vtcm_used_bytes == 1024
    assert t.advance(1, 1, release_bytes=1024).allowed
    assert t.step(2, 1, HTP(1024, 0)).allowed


def test_poll_consumed_and_busy_completion():
    t = twin()
    assert not t.step(0, 0, ReRAM('write', 4)).allowed
    assert t.step(0, 0, ReRAM('poll', 0)).allowed
    assert t.step(1, 0, ReRAM('write', 4)).allowed
    assert t.step(2, 1, ReRAM('poll', 0)).allowed
    assert not t.step(3, 3, ReRAM('write', 4)).allowed
    assert t.step(3, 3, ReRAM('poll', 0)).allowed
    assert t.step(4, 3, ReRAM('write', 4)).allowed


def test_por_row_wear_and_atomic_denial():
    t = twin()
    assert not t.step(0, 0, FeRAM('frqad', 'qpi', 80, 0, 4)).allowed
    assert t.step(0, 0, FeRAM('status', 'qpi', 80, 0, 0)).allowed
    assert t.step(1, 0, FeRAM('write', 'qpi', 80, 0, 4)).allowed
    assert t.step(2, 0, FeRAM('write', 'qpi', 80, 0, 4)).allowed
    before = t.snapshot
    assert not t.step(3, 0, FeRAM('write', 'qpi', 80, 0, 8)).allowed
    assert t.snapshot == before
    assert t.step(3, 0, FeRAM('write', 'qpi', 80, 4, 4)).allowed


def test_thermal_prediction_and_cooling():
    t = Twin(L, Parameters(42850, 10, 100, 3, 2, 64))
    assert t.step(0, 0, MTJ('read', 100)).allowed
    assert not t.step(1, 0, MTJ('read', 100)).allowed
    assert t.advance(1, 20).allowed
    assert t.step(2, 20, MTJ('read', 100)).allowed


@pytest.mark.parametrize('now', [-1, True, 2**63, 1000001])
def test_invalid_time_is_atomic(now):
    t = twin()
    before = t.snapshot
    assert not t.step(0, now, HTP(1, 0)).allowed
    assert t.snapshot == before


def test_deterministic_replay():
    def run():
        t = twin()
        for i in range(20):
            assert t.step(i, i, MTJ('read', 100)).allowed
        return t.snapshot
    assert run() == run()


def test_competing_revision_commits_once():
    from concurrent.futures import ThreadPoolExecutor
    t = twin()
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: t.step(0, 0, HTP(1, 0)).allowed, range(32)))
    assert sum(outcomes) == 1
    assert t.snapshot.revision == t.snapshot.vtcm_used_bytes == 1


def test_rejects_base_shield_violations_and_bad_release():
    t = twin()
    before = t.snapshot
    for action in (HTP(1, 1), MTJ('read', 201), MTJ('write', 650000),
                   FeRAM('write', 'qpi', 79, 0, 4), ReRAM('write', 257), object()):
        assert not t.step(0, 0, action).allowed
        assert t.snapshot == before
    assert not t.advance(0, 0, release_bytes=1).allowed
    assert t.snapshot == before


def test_row_capacity_and_invalid_parameters():
    from dataclasses import replace
    t = Twin(L, replace(P, max_tracked_rows=1))
    assert not t.step(0, 0, FeRAM('write', 'qpi', 80, 0, 8)).allowed
    assert t.step(0, 0, FeRAM('write', 'qpi', 80, 0, 4)).allowed
    assert not t.step(1, 0, FeRAM('write', 'qpi', 80, 4, 4)).allowed
    with pytest.raises(ValueError):
        Twin(L, replace(P, thermal_tau_ms=0))


def test_clock_rollback_and_bool_revision():
    t = twin()
    assert t.advance(0, 5).allowed
    before = t.snapshot
    assert not t.step(1, 4, HTP(1, 0)).allowed
    assert not t.step(True, 5, HTP(1, 0)).allowed
    assert t.snapshot == before
