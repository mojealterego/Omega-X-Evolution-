"""Symbolic, rather than four-example, finite HyperLTL and shell proof."""
import pytest
from omega_x_evolution.ontos_v47_pure_ir import PureIR
from omega_x_evolution.ontos_l10_formal import (
    check_symbolic_noninterference, prove_cap_attenuation,
    prove_static_shell_guard, model_proof_suite,
)


def test_symbolic_noninterference_all_secret_pairs():
    safe=PureIR(('add',('x',),('lit',1)))
    r=check_symbolic_noninterference(safe)
    assert r['status']=='PASS_QFBV_UNSAT' and r['solver']=='unsat'
    assert r['domain']['low_bits']==4 and r['domain']['secret_bits']==4
    assert not r['unbounded_hyperltl_proved']


def test_symbolic_discovered_secret_leak():
    leak=PureIR(('xor',('x',),('y',)))
    r=check_symbolic_noninterference(leak)
    assert r['status']=='FAIL_COUNTEREXAMPLE' and r['solver']=='sat'


def test_z3_proves_cap_monotonicity_for_all_8_masks_and_reset():
    r=prove_cap_attenuation()
    assert r['status']=='PASS_QFBV_UNSAT' and r['solver']=='unsat'
    assert r['width']==3
    assert not r['real_tcb_verified']


def test_z3_mutated_grant_after_restart_yields_counterexample():
    bad=prove_cap_attenuation(restart_restores_root=True)
    assert bad['status']=='FAIL_COUNTEREXAMPLE' and bad['solver']=='sat'


def test_static_shell_fixed_across_candidate_and_fault_reset():
    r=prove_static_shell_guard()
    assert r['status']=='PASS_QFBV_UNSAT'
    assert r['shell_width_bits']==256
    assert not r['physical_fpga_verified']


def test_static_shell_unprotected_negative_control_fails():
    r=prove_static_shell_guard(allow_shell_mutation=True)
    assert r['status']=='FAIL_COUNTEREXAMPLE'


def test_formal_suite_fail_closed_and_idempotent():
    a=model_proof_suite()
    assert a==model_proof_suite()
    assert all(x['solver']=='unsat' for x in a.values())


def test_q16_arithmetic_shift_matches_independent_floor_div_for_products():
    from omega_x_evolution.ontos_l10_formal import prove_q16_floor_shift
    r=prove_q16_floor_shift()
    assert r['status']=='PASS_QFBV_UNSAT' and r['solver']=='unsat'
    assert r['width']==64
    assert not r['native_verilog_compiled']


def test_q16_wrong_towards_zero_rule_generates_real_counterexample():
    from omega_x_evolution.ontos_l10_formal import prove_q16_floor_shift
    r=prove_q16_floor_shift(round_toward_zero=True)
    assert r['status']=='FAIL_COUNTEREXAMPLE' and r['solver']=='sat'
