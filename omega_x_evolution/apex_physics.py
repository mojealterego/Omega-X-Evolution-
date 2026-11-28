"""Parameterized NVM and bandwidth equations, not calibrated silicon limits.

Decimal arithmetic uses a fixed context. Inputs are integer SI subunits;
outputs are estimates, never permissions to bypass apex_shield.
"""
from decimal import Context, Decimal as D, localcontext
from .apex_twin import integer

_CTX = Context(prec=40)
_K_EV = D('0.00008617333262145')


def _require(*bounds):
    if not all(integer(value, lo, hi) for value, lo, hi in bounds):
        raise ValueError('model domain')


def _barrier(temp_mc, barrier_uev):
    _require((temp_mc, -40000, 125000), (barrier_uev, 1, 10000000))
    return D(barrier_uev)/1000000/(_K_EV*(D(temp_mc)/1000+D('273.15')))


def neel_log_seconds(temp_mc: int, barrier_uev: int, attempt_ps: int) -> D:
    """Natural log of tau = attempt time * exp(Ea/kT)."""
    _require((attempt_ps, 1, 10**12))
    with localcontext(_CTX):
        return (D(attempt_ps)/10**12).ln()+_barrier(temp_mc, barrier_uev)


def tddb_log_cycles(voltage_uv: int, reference_uv: int, slope_per_mv_ppm: int, log10_cycles: int) -> D:
    """Exponential E-model: ln N = log10(Nref)*ln(10)-gamma*(V-Vref).

    slope_per_mv_ppm is gamma in inverse mV multiplied by 10**6.
    """
    _require((voltage_uv, 1, 10**7), (reference_uv, 1, 10**7),
             (slope_per_mv_ppm, 0, 10**8), (log10_cycles, 0, 30))
    with localcontext(_CTX):
        return D(log10_cycles)*D(10).ln()-D(slope_per_mv_ppm)*(voltage_uv-reference_uv)/10**9


def disturb_probability(temp_mc: int, barrier_uev: int, attempt_ps: int,
                        pulse_ns: int, current_ua: int, critical_ua: int) -> D:
    """Single-pulse Poisson model with illustrative linear barrier reduction."""
    _require((attempt_ps, 1, 10**12), (pulse_ns, 0, 10**9),
             (critical_ua, 1, 10**7), (current_ua, 0, 10**7))
    if current_ua*5 > critical_ua:
        raise ValueError('outside modeled read envelope')
    with localcontext(_CTX):
        barrier = _barrier(temp_mc, barrier_uev)*(1-D(current_ua)/critical_ua)
        hazard = D(pulse_ns)*1000/attempt_ps*(-barrier).exp()
        if hazard < D('1e-20'):
            return hazard-hazard*hazard/2
        return 1-(-hazard).exp()


def reram_resistance(reference_mohm: int, reference_ms: int, age_ms: int, exponent_ppm: int) -> D:
    """R(t)=R0*(t/t0)**nu; result in milliohms."""
    _require((reference_mohm, 1, 10**15), (reference_ms, 1, 10**15),
             (age_ms, reference_ms, 10**15), (exponent_ppm, 0, 1000000))
    with localcontext(_CTX):
        return D(reference_mohm)*(D(exponent_ppm)/1000000*(D(age_ms)/reference_ms).ln()).exp()


def ir_drop_uv(current_ua: int, resistance_mohm: int) -> int:
    """Ceiling of I*R in microvolts."""
    _require((current_ua, 0, 10**9), (resistance_mohm, 0, 10**12))
    return (current_ua*resistance_mohm+999)//1000


def shared_transfer_ns(size_bytes: int, capacity_bps: int, competing_bps: int) -> int:
    """Constant-rate residual bandwidth model, no queue or burst effects."""
    _require((size_bytes, 0, 10**12), (capacity_bps, 1, 10**15),
             (competing_bps, 0, capacity_bps-1))
    rate = capacity_bps-competing_bps
    return (size_bytes*10**9+rate-1)//rate
