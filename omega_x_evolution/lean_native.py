"""Native Lean proof checking, using core BitVec arithmetic when possible.

The core route uses the genuine upstream BitVec.add/sub definitions and
kernel-checked Nat lemmas. It requires no Mathlib or external SAT solver.
All six IR operations additionally support a kernel-checked lemma route.
Unsolved equations use the original Std BVDecide route, never a fake solver.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from .polyglot import Program

# The modular arithmetic and BitVec extensionality lemmas below are adapted
# from Lean's Apache-2.0 licensed Init.Data.Nat.Lemmas, Init.Data.BitVec.Bootstrap
# and Init.Data.BitVec.Lemmas (Lean 4.36.0). See docs/omega/NATIVE_LEAN_V363.md.
_CORE_HEADER = r'''prelude
import Init.Data.BitVec.BasicAux
import Init.Data.Nat.Div.Basic
import Init.TacticsExtra
set_option linter.unusedVariables false
set_option linter.unusedSimpArgs false
set_option maxHeartbeats 200000

private theorem omega_mod_add_mod (m n k : Nat) : (m % n + k) % n = (m + k) % n := by
  have h := (Nat.add_mul_mod_self_left (m % n + k) n (m / n)).symm
  rwa [Nat.add_right_comm, Nat.mod_add_div] at h

private theorem omega_eq_of_toNat_eq {n : Nat} : ∀ {x y : BitVec n}, x.toNat = y.toNat → x = y
  | ⟨_, _⟩, ⟨_, _⟩, rfl => rfl

private theorem omega_cancel (x y : BitVec 16) : x + y - y = x := by
  apply omega_eq_of_toNat_eq
  change (65536 - y.toNat + (x.toNat + y.toNat) % 65536) % 65536 = x.toNat
  rw [Nat.add_comm (65536 - y.toNat), omega_mod_add_mod, Nat.add_assoc,
      Nat.add_comm y.toNat (65536 - y.toNat), Nat.sub_add_cancel (Nat.le_of_lt y.isLt),
      Nat.add_mod_right, Nat.mod_eq_of_lt x.isLt]

private theorem omega_add_zero (x : BitVec 16) : x + 0 = x := by
  apply omega_eq_of_toNat_eq
  change (x.toNat + 0) % 65536 = x.toNat
  rw [Nat.add_zero, Nat.mod_eq_of_lt x.isLt]

private theorem omega_zero_add (x : BitVec 16) : 0 + x = x := by
  apply omega_eq_of_toNat_eq
  change (0 + x.toNat) % 65536 = x.toNat
  rw [Nat.zero_add, Nat.mod_eq_of_lt x.isLt]

private theorem omega_sub_zero (x : BitVec 16) : x - 0 = x := by
  apply omega_eq_of_toNat_eq
  change (65536 - 0 + x.toNat) % 65536 = x.toNat
  rw [Nat.sub_zero, Nat.add_mod_left, Nat.mod_eq_of_lt x.isLt]

private theorem omega_sub_self (x : BitVec 16) : x - x = 0 := by
  apply omega_eq_of_toNat_eq
  change (65536 - x.toNat + x.toNat) % 65536 = 0
  rw [Nat.sub_add_cancel (Nat.le_of_lt x.isLt), Nat.mod_self]

'''


def _expression(tree: tuple, operators: dict[str, str]) -> str:
    op = tree[0]
    if op in ('x', 'y'):
        return op
    if op == 'lit':
        return f'({tree[1]} : BitVec 16)'
    if op not in operators:
        raise LookupError(op)
    return f'({_expression(tree[1], operators)} {operators[op]} {_expression(tree[2], operators)})'


def _validate(a: Program, b: Program) -> None:
    if not isinstance(a, Program) or not isinstance(b, Program):
        raise ValueError('validated typed programs required')
    # Recheck immutable IR boundaries even if a hostile caller forged a dataclass.
    Program(a.tree)
    Program(b.tree)


def lean_core_source(a: Program, b: Program) -> str | None:
    """Generate a true Lean theorem using only actual add/sub BitVec operations.

    Unsupported operators are not translated into alternative semantics.
    Failure of the bounded tactic is unknown, not a negative proof.
    """
    _validate(a, b)
    try:
        left, right = (_expression(p.tree, {'add': '+', 'sub': '-'}) for p in (a, b))
    except LookupError:
        return None
    return _CORE_HEADER + (
        'theorem omega_extensional_equivalence :\n'
        f'  (fun (x y : BitVec 16) => {left}) =\n'
        f'  (fun (x y : BitVec 16) => {right}) :=\n'
        '  funext (fun x => funext (fun y => by\n'
        '    first\n'
        '    | rfl\n'
        '    | simp only [omega_cancel, omega_add_zero, omega_zero_add, omega_sub_zero, omega_sub_self]))\n'
    )


def lean_source(a: Program, b: Program, *, extensional: bool = True) -> str:
    _validate(a, b)
    operators = {'add': '+', 'sub': '-', 'mul': '*', 'xor': '^^^', 'and': '&&&', 'or': '|||'}
    left, right = (_expression(p.tree, operators) for p in (a, b))
    header = ('import Std.Tactic.BVDecide\nset_option maxHeartbeats 200000\n'
              'set_option linter.unusedVariables false\nset_option debug.skipKernelTC false\n')
    if extensional:
        return (header + 'theorem omega_extensional_equivalence :\n'
                f'  (fun (x y : BitVec 16) => {left}) =\n'
                f'  (fun (x y : BitVec 16) => {right}) := by\n'
                '  funext x y\n  bv_decide\n')
    return header + f'theorem omega_equivalence (x y : BitVec 16) :\n  {left} = {right} := by\n  bv_decide\n'


# These u16 lemmas are derived directly from the upstream BitVec.Basic
# definitions and Nat lemmas. All declarations are checked by the Lean kernel.
# Rewriting is incomplete; the full BVDecide route remains available.
_BITVEC_HEADER = _CORE_HEADER.replace(
    'import Init.Data.BitVec.BasicAux\n',
    'import Init.Data.BitVec.Basic\nimport Init.Data.Nat.Bitwise.Lemmas\nimport Init.Data.Nat.Lemmas\n',
).replace('set_option maxHeartbeats 200000\n',
          'set_option maxHeartbeats 200000\nset_option debug.skipKernelTC false\n') + r'''
private theorem omega_mul_one (x : BitVec 16) : x * 1 = x := by
  apply omega_eq_of_toNat_eq
  change (x.toNat * 1) % 65536 = x.toNat
  rw [Nat.mul_one, Nat.mod_eq_of_lt x.isLt]
private theorem omega_mul_zero (x : BitVec 16) : x * 0 = 0 := by
  apply omega_eq_of_toNat_eq
  change (x.toNat * 0) % 65536 = 0
  rw [Nat.mul_zero, Nat.zero_mod]
private theorem omega_mul_comm (x y : BitVec 16) : x * y = y * x := by
  apply omega_eq_of_toNat_eq
  change (x.toNat * y.toNat) % 65536 = (y.toNat * x.toNat) % 65536
  rw [Nat.mul_comm]
private theorem omega_xor_self (x : BitVec 16) : x ^^^ x = 0 := by
  apply omega_eq_of_toNat_eq
  change x.toNat ^^^ x.toNat = 0
  exact Nat.xor_self _
private theorem omega_and_self (x : BitVec 16) : x &&& x = x := by
  apply omega_eq_of_toNat_eq
  change x.toNat &&& x.toNat = x.toNat
  exact Nat.and_self _
private theorem omega_or_zero (x : BitVec 16) : x ||| 0 = x := by
  apply omega_eq_of_toNat_eq
  change x.toNat ||| 0 = x.toNat
  exact Nat.or_zero _
private theorem omega_mul_add (x y z : BitVec 16) : x * (y + z) = x*y + x*z := by
  apply omega_eq_of_toNat_eq
  change (x.toNat * ((y.toNat + z.toNat) % 65536)) % 65536 = ((x.toNat * y.toNat) % 65536 + (x.toNat * z.toNat) % 65536) % 65536
  rw [Nat.mul_mod_mod, Nat.mul_add, Nat.mod_add_mod, Nat.add_mod_mod]
private theorem omega_one_mul (x : BitVec 16) : 1 * x = x := by
  rw [omega_mul_comm, omega_mul_one]
private theorem omega_zero_mul (x : BitVec 16) : 0 * x = 0 := by
  rw [omega_mul_comm, omega_mul_zero]
private theorem omega_xor_zero (x : BitVec 16) : x ^^^ 0 = x := by
  apply omega_eq_of_toNat_eq
  change x.toNat ^^^ 0 = x.toNat
  exact Nat.xor_zero _
private theorem omega_and_zero (x : BitVec 16) : x &&& 0 = 0 := by
  apply omega_eq_of_toNat_eq
  change x.toNat &&& 0 = 0
  exact Nat.and_zero _
private theorem omega_or_self (x : BitVec 16) : x ||| x = x := by
  apply omega_eq_of_toNat_eq
  change x.toNat ||| x.toNat = x.toNat
  exact Nat.or_self _
'''

_BITVEC_SIMPS = (
    'cancel', 'add_zero', 'zero_add', 'sub_zero', 'sub_self',
    'mul_one', 'one_mul', 'mul_zero', 'zero_mul', 'mul_comm', 'mul_add',
    'and_self', 'or_self', 'xor_self', 'and_zero', 'or_zero', 'xor_zero',
)


def lean_bitvec_source(a: Program, b: Program, *, extensional: bool = True) -> str:
    """Fixed theorem using all six upstream BitVec operations and lemmas."""
    _validate(a, b)
    if type(extensional) is not bool:
        raise ValueError('Lean mode')
    operators = {'add': '+', 'sub': '-', 'mul': '*', 'xor': '^^^', 'and': '&&&', 'or': '|||'}
    left, right = (_expression(p.tree, operators) for p in (a, b))
    header = _BITVEC_HEADER
    if extensional:
        statement = ('theorem omega_extensional_equivalence :\n'
                     f'  (fun (x y : BitVec 16) => {left}) =\n'
                     f'  (fun (x y : BitVec 16) => {right}) := by\n  funext x y\n')
    else:
        statement = f'theorem omega_equivalence (x y : BitVec 16) :\n  {left} = {right} := by\n'
    return header + statement + '  first\n  | rfl\n  | simp only [' + ', '.join('omega_' + n for n in _BITVEC_SIMPS) + ']\n'


def _report(source: str, strategy: str) -> dict:
    return {'backend': 'lean', 'strategy': strategy,
            'source_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(), 'proved': False}


def _run(binary: str, source: str, strategy: str, version: str, timeout: float) -> dict:
    report = _report(source, strategy)
    if timeout <= 0:
        return {**report, 'status': 'failed-or-timeout', 'version': version}
    with tempfile.TemporaryDirectory(prefix='omega-lean-') as directory:
        path = Path(directory) / 'Proof.lean'
        path.write_text(source, encoding='utf-8')
        try:
            proc = subprocess.run([binary, '-t', '0', '-DwarningAsError=true', str(path)],
                                  cwd=directory, capture_output=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError):
            return {**report, 'status': 'failed-or-timeout', 'version': version}
    ok = proc.returncode == 0 and not proc.stdout.strip() and not proc.stderr.strip()
    return {**report, 'status': 'checked' if ok else 'rejected', 'proved': ok, 'version': version}


def check_lean(a: Program, b: Program, *, timeout: int = 30,
               extensional: bool = True, core_only: bool = False) -> dict:
    if type(timeout) is not int or not 1 <= timeout <= 60:
        raise ValueError('Lean timeout')
    if type(core_only) is not bool or type(extensional) is not bool:
        raise ValueError('Lean mode')
    full = lean_source(a, b, extensional=extensional)
    core = lean_core_source(a, b)
    if core_only and core is None:
        return {**_report(full, 'core-addsub'), 'status': 'unsupported'}
    binary = shutil.which('lean')
    initial = _report(core if core is not None else full,
                      'core-addsub' if core is not None else 'bv-decide')
    if not binary:
        return {**initial, 'status': 'unavailable'}
    deadline = time.monotonic() + timeout
    try:
        version_result = subprocess.run([binary, '--version'], capture_output=True,
                                        timeout=min(5, timeout), check=True)
        version = version_result.stdout.decode(errors='replace')[:256].strip()
    except (OSError, subprocess.SubprocessError):
        return {**initial, 'status': 'failed-or-timeout'}
    if core is not None:
        result = _run(binary, core, 'core-addsub', version, deadline - time.monotonic())
        if result['proved'] or core_only:
            return result
    lemmas = lean_bitvec_source(a, b, extensional=extensional)
    result = _run(binary, lemmas, 'bitvec-lemmas', version, deadline - time.monotonic())
    if result['proved']:
        return result
    return _run(binary, full, 'bv-decide', version, deadline - time.monotonic())
