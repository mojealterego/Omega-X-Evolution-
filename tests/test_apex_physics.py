from decimal import Decimal as D, localcontext
import pytest
from omega_x_evolution.apex_physics import (
    neel_log_seconds, tddb_log_cycles, disturb_probability, reram_resistance,
    ir_drop_uv, shared_transfer_ns,
)


def test_neel_temperature_and_units():
    assert neel_log_seconds(25000, 1_000_000, 1000) > neel_log_seconds(85000, 1_000_000, 1000)
    assert neel_log_seconds(25000, 2_000_000, 1000) > neel_log_seconds(25000, 1_000_000, 1000)


def test_tddb_reference_and_slope():
    assert tddb_log_cycles(600000, 600000, 35000, 12) == D(12)*D(10).ln() or abs(tddb_log_cycles(600000, 600000, 35000, 12)-D(12)*D(10).ln()) < D('1e-25')
    assert tddb_log_cycles(900000, 600000, 35000, 12) < tddb_log_cycles(600000, 600000, 35000, 12)


def test_disturb_probability_bound_and_monotone():
    assert disturb_probability(25000, 1000000, 1000, 0, 0, 1000) == 0
    a = disturb_probability(25000, 500000, 1000, 100, 100, 1000)
    b = disturb_probability(25000, 500000, 1000, 100, 200, 1000)
    assert 0 < a < b < 1


def test_reram_reference_and_drift():
    assert reram_resistance(10000, 1000, 1000, 20000) == 10000
    assert reram_resistance(10000, 1000, 1000000, 20000) > 10000
    assert reram_resistance(10000, 1000, 1000000, 0) == 10000


def test_ir_drop_and_bandwidth_integer_ceil():
    assert ir_drop_uv(1000, 1500) == 1500
    assert ir_drop_uv(1, 1) == 1
    assert shared_transfer_ns(1000, 1000, 0) == 1000000000
    assert shared_transfer_ns(1000, 1000, 500) == 2000000000
    assert shared_transfer_ns(1, 3, 0) == 333333334


@pytest.mark.parametrize('call', [
    lambda: neel_log_seconds(True, 1, 1),
    lambda: neel_log_seconds(-40001, 1, 1),
    lambda: tddb_log_cycles(0, 600000, 1, 12),
    lambda: disturb_probability(25000, 1, 1, 1, 201, 1000),
    lambda: reram_resistance(100, 1000, 999, 1),
    lambda: ir_drop_uv(-1, 1),
    lambda: shared_transfer_ns(1, 10, 10),
])
def test_invalid_domain(call):
    with pytest.raises(ValueError):
        call()


def test_decimal_context_independent():
    a = neel_log_seconds(25000, 1000000, 1000)
    with localcontext() as ctx:
        ctx.prec = 6
        assert neel_log_seconds(25000, 1000000, 1000) == a
