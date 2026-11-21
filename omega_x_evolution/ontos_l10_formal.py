"""Native libz3 bounded QF_BV proof obligations for ONTOS L10.

Symbols and SMT are generated from a validated, closed IR grammar. Queries
run in a separate Python process with native libz3; no arbitrary SMT or code
from a candidate is executed. PASS means unsatisfiable *negation* over the
finite declared domain, not universal runtime/HyperLTL or hardware safety.
"""
from __future__ import annotations
import subprocess
import sys
from .ontos_v47_pure_ir import PureIR
from .ontos_v67_dfx import _smt_tree


def _query(q: str) -> str:
    if type(q) is not str or len(q)>8192:raise ValueError('bounded query')
    try:
        p=subprocess.run([sys.executable,'-m','omega_x_evolution.ontos_v67_dfx','--worker'],
                         input=q,text=True,capture_output=True,timeout=6,check=False)
    except (OSError,subprocess.TimeoutExpired):return 'unknown'
    if p.returncode or p.stderr.strip():return 'unknown'
    return p.stdout.strip() if p.stdout.strip() in ('unsat','sat','unknown') else 'unknown'


def _verdict(status: str) -> str:
    return {'unsat':'PASS_QFBV_UNSAT','sat':'FAIL_COUNTEREXAMPLE'}.get(status,'UNKNOWN_SOLVER')


def check_symbolic_noninterference(program: PureIR) -> dict:
    """Exists equal public x, unequal secrets y1,y2, differing public outputs?"""
    if type(program) is not PureIR:raise ValueError('PureIR required')
    program.__post_init__()
    source=_smt_tree(program.tree)
    a=source.replace(' y',' y1').replace('y)', 'y1)').replace(' y\n',' y1\n')
    b=source.replace(' y',' y2').replace('y)', 'y2)').replace(' y\n',' y2\n')
    # The regex approach above is only for compiler-produced QF_BV grammar;
    # never runs attacker-provided SMT strings. Explicit token guard protects
    # against accidental modifications to literal opcodes or variables.
    # In the grammar all variables are bare "x" or "y" tokens.
    import re
    a=re.sub(r'(?<![A-Za-z0-9_])y(?![A-Za-z0-9_])','y1',source)
    b=re.sub(r'(?<![A-Za-z0-9_])y(?![A-Za-z0-9_])','y2',source)
    query='\n'.join(['(set-logic QF_BV)','(set-option :timeout 3000)',
                     '(declare-const x (_ BitVec 4))',
                     '(declare-const y1 (_ BitVec 4))','(declare-const y2 (_ BitVec 4))',
                     '(assert (distinct y1 y2))',
                     f'(assert (distinct {a} {b}))','(check-sat)',''])
    solver=_query(query)
    return {'status':_verdict(solver),'solver':solver,'unbounded_hyperltl_proved':False,
            'domain':{'low_bits':4,'secret_bits':4,'traces':2},
            'program_semantics':'finite i4; independent solver'}


def prove_cap_attenuation(*,restart_restores_root: bool=False) -> dict:
    if type(restart_restores_root) is not bool:raise ValueError('model variant')
    next_caps='root' if restart_restores_root else '(bvand caps proposed)'
    # Witness: root, caps, proposed such that caps ⊆ root but next gains a cap
    # absent from caps. Covers all 2^(3*3) assignments in one QF_BV query.
    query='\n'.join(['(set-logic QF_BV)','(set-option :timeout 3000)',
                     '(declare-const root (_ BitVec 3))',
                     '(declare-const caps (_ BitVec 3))',
                     '(declare-const proposed (_ BitVec 3))',
                     '(assert (= (bvand caps (bvnot root)) (_ bv0 3)))',
                     f'(assert (distinct (bvand {next_caps} (bvnot caps)) (_ bv0 3)))',
                     '(check-sat)',''])
    solver=_query(query)
    return {'status':_verdict(solver),'solver':solver,'width':3,
            'real_tcb_verified':False,'state_model':'subset monotonicity and restart'}


def prove_static_shell_guard(*,allow_shell_mutation: bool=False) -> dict:
    if type(allow_shell_mutation) is not bool:raise ValueError('model variant')
    transformed='(bvnot shell)' if allow_shell_mutation else 'shell'
    query='\n'.join(['(set-logic QF_BV)','(set-option :timeout 3000)',
                     '(declare-const shell (_ BitVec 256))',
                     f'(assert (distinct shell {transformed}))','(check-sat)',''])
    solver=_query(query)
    return {'status':_verdict(solver),'solver':solver,'shell_width_bits':256,
            'physical_fpga_verified':False,'model':'immutable shell across DFX swap'}


def model_proof_suite() -> dict:
    return {'no_secret_leak':check_symbolic_noninterference(PureIR(('add',('x',),('lit',1)))),
            'caps_monotone':prove_cap_attenuation(),
            'shell_unchanged':prove_static_shell_guard()}


def prove_q16_floor_shift(*, round_toward_zero: bool = False) -> dict:
    """Check Q16.16 arithmetic shift against independently expressed floor division.

    Signed 64-bit input is the widened product of two signed 32-bit operands;
    INT64_MIN cannot occur for such products. The negative quotient uses the
    mathematical floor rule, not C truncation towards zero. A deliberately
    incorrect C rule is available solely for falsification tests.
    """
    if type(round_toward_zero) is not bool:
        raise ValueError('rounding variant must be boolean')
    neg = ('(bvneg (bvlshr (bvneg v) (_ bv16 64)))' if round_toward_zero
           else '(bvneg (bvlshr (bvadd (bvneg v) (_ bv65535 64)) (_ bv16 64)))')
    query = '\n'.join([
        '(set-logic QF_BV)', '(set-option :timeout 3000)',
        '(declare-const v (_ BitVec 64))',
        '(assert (distinct v #x8000000000000000))',
        f'(assert (distinct (bvashr v (_ bv16 64)) '
        f'(ite (= ((_ extract 63 63) v) #b1) {neg} (bvlshr v (_ bv16 64)))))',
        '(check-sat)', '',
    ])
    solver = _query(query)
    return {'status': _verdict(solver), 'solver': solver, 'width': 64,
            'native_verilog_compiled': False,
            'domain': 'signed 64-bit except INT64_MIN; proof over all such v'}
