"""Deterministic bit blasting of validated u16 IR; independent native LRAT check.

The solver is untrusted. The trusted base includes this CNF encoding, the
Isabelle-exported checker and the local toolchain. No external candidate code.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from .polyglot import Program, _validated_tree

MAX_VARIABLES = 100_000
MAX_CLAUSES = 400_000
MAX_PROOF_BYTES = 64 * 1024 * 1024


class Circuit:
    def __init__(self, width: int):
        self.width = width
        self.variables = 1 + 2 * width
        self.clauses = [(1,)]
        self.gates = []
        self.memo = {}
        self.x = tuple(range(2, width + 2))
        self.y = tuple(range(width + 2, 2 * width + 2))

    def gate(self, op: str, a: int, b: int) -> int:
        # Signed literals; variable 1 is constrained true.
        if op == 'and':
            if a == -1 or b == -1 or a == -b: return -1
            if a == 1 or a == b: return b
            if b == 1: return a
        elif op == 'xor':
            if a == b: return -1
            if a == -b: return 1
            if a == -1: return b
            if b == -1: return a
            if a == 1: return -b
            if b == 1: return -a
        else:
            raise ValueError('gate operation')
        a, b = sorted((a, b))
        key = (op, a, b)
        if key in self.memo: return self.memo[key]
        self.variables += 1
        z = self.variables
        clauses = [(-a, -b, z), (a, -z), (b, -z)] if op == 'and' else [
            (-a, -b, -z), (a, b, -z), (-a, b, z), (a, -b, z)]
        if z > MAX_VARIABLES or len(self.clauses) + len(clauses) > MAX_CLAUSES:
            raise ValueError('CNF budget exceeded')
        self.clauses.extend(clauses)
        self.gates.append((op, a, b, z))
        self.memo[key] = z
        return z

    def either(self, a, b):
        return -self.gate('and', -a, -b)

    def add(self, a, b, carry=-1):
        out = []
        for x, y in zip(a, b):
            p = self.gate('xor', x, y)
            out.append(self.gate('xor', p, carry))
            carry = self.either(self.gate('and', x, y), self.gate('and', p, carry))
        return tuple(out)

    def tree(self, t):
        op = t[0]
        if op == 'x': return self.x
        if op == 'y': return self.y
        if op == 'lit': return tuple(1 if t[1] >> i & 1 else -1 for i in range(self.width))
        a, b = self.tree(t[1]), self.tree(t[2])
        if op == 'add': return self.add(a, b)
        if op == 'sub': return self.add(a, tuple(-v for v in b), 1)
        if op == 'mul':
            result = (-1,) * self.width
            for i, bit in enumerate(b):
                row = (-1,) * i + tuple(self.gate('and', v, bit) for v in a[:self.width-i])
                result = self.add(result, row)
            return result
        if op == 'or': return tuple(self.either(x, y) for x, y in zip(a, b))
        return tuple(self.gate(op, x, y) for x, y in zip(a, b))

    def evaluate(self, output, x, y):
        values = {1: True}
        for value, bits in ((x, self.x), (y, self.y)):
            if type(value) is not int or not 0 <= value < 2**self.width: raise ValueError('input range')
            values.update({b: bool(value >> i & 1) for i, b in enumerate(bits)})
        def val(lit): return values[abs(lit)] != (lit < 0)
        for op, a, b, z in self.gates:
            values[z] = (val(a) and val(b)) if op == 'and' else val(a) != val(b)
        return sum(int(val(b)) << i for i, b in enumerate(output))


def compile_circuit(program: Program, *, width: int = 16):
    if type(width) is not int or not 1 <= width <= 16: raise ValueError('circuit width')
    c = Circuit(width)
    return c, c.tree(_validated_tree(program))


def cnf(a: Program, b: Program) -> bytes:
    c, left = compile_circuit(a)
    right = c.tree(_validated_tree(b))
    # A satisfying assignment witnesses inequivalence. A verified refutation
    # establishes equality over all 2**32 input pairs for the encoded IR.
    c.clauses.append(tuple(c.gate('xor', x, y) for x, y in zip(left, right)))
    return (f'p cnf {c.variables} {len(c.clauses)}\n' + ''.join(
        ' '.join(map(str, row)) + ' 0\n' for row in c.clauses)).encode('ascii')


def _binding(a: Program, b: Program, data: bytes) -> dict:
    trees = [_validated_tree(a), _validated_tree(b)]
    return {'backend': 'lrat_isa', 'cnf_sha256': hashlib.sha256(data).hexdigest(),
            'ir_sha256': hashlib.sha256(json.dumps(trees, separators=(',', ':')).encode('ascii')).hexdigest(),
            'domain_size': 2**32}


def _check(prefix, checker, dimacs, certificate, root, timeout):
    if timeout <= 0:
        return False
    p = subprocess.run(prefix + [checker, str(dimacs), str(certificate)], cwd=root,
                       capture_output=True, timeout=timeout)
    return p.returncode == 0 and b's VERIFIED UNSAT' in p.stdout.splitlines()


def prove(a: Program, b: Program, *, timeout: int = 30) -> dict:
    if type(timeout) is not int or not 1 <= timeout <= 60: raise ValueError('LRAT timeout')
    a, b = Program(_validated_tree(a)), Program(_validated_tree(b))
    data = cnf(a, b)
    report = {**_binding(a, b, data), 'proved': False}
    solver, checker, limit = (shutil.which(n) for n in ('cadical', 'lrat_isa', 'prlimit'))
    if not all((solver, checker, limit)): return {**report, 'status': 'unavailable'}
    deadline = time.monotonic() + timeout
    with tempfile.TemporaryDirectory(prefix='omega-lrat-') as root:
        dimacs, certificate = Path(root)/'query.cnf', Path(root)/'query.lrat'
        dimacs.write_bytes(data)
        try:
            # The size limit applies in the native solver process, before disk
            # allocation can exceed the bound. Both tools share one deadline.
            prefix = [limit, '--core=0:0', '--as=1073741824:1073741824', f'--fsize={MAX_PROOF_BYTES}:{MAX_PROOF_BYTES}', '--']
            s = subprocess.run(prefix + [solver, '-q', '--lrat', '--binary', '--plain', str(dimacs), str(certificate)],
                               cwd=root, capture_output=True, timeout=max(.001, deadline-time.monotonic()))
            if s.returncode == 10: return {**report, 'status': 'sat'}
            if s.returncode != 20 or not certificate.is_file() or not 0 < certificate.stat().st_size <= MAX_PROOF_BYTES:
                return {**report, 'status': 'unknown'}
            if not _check(prefix, checker, dimacs, certificate, root, deadline-time.monotonic()):
                return {**report, 'status': 'rejected'}
            raw = certificate.read_bytes()
            if not 0 < len(raw) <= MAX_PROOF_BYTES:
                return {**report, 'status': 'rejected'}
            return {**report, 'status': 'checked', 'proved': True,
                    'proof_sha256': hashlib.sha256(raw).hexdigest(),
                    'proof': base64.b64encode(raw).decode('ascii')}
        except (OSError, subprocess.SubprocessError):
            return {**report, 'status': 'failed-or-timeout'}


def verify(a: Program, b: Program, report: dict, *, timeout: int = 30) -> bool:
    """Check the supplied certificate against regenerated CNF without CaDiCaL."""
    if type(timeout) is not int or not 1 <= timeout <= 60:
        raise ValueError('LRAT timeout')
    if type(report) is not dict or report.get('proved') is not True or report.get('status') != 'checked':
        return False
    try:
        a, b = Program(_validated_tree(a)), Program(_validated_tree(b))
        data = cnf(a, b)
        expected = _binding(a, b, data)
        if set(report) != set(expected) | {'proved', 'status', 'proof', 'proof_sha256'}:
            return False
        if any(report[k] != v or type(report[k]) is not type(v) for k, v in expected.items()):
            return False
        encoded = report['proof']
        if type(encoded) is not str or not 0 < len(encoded) <= 4*((MAX_PROOF_BYTES+2)//3):
            return False
        raw = base64.b64decode(encoded, validate=True)
        if not 0 < len(raw) <= MAX_PROOF_BYTES or hashlib.sha256(raw).hexdigest() != report['proof_sha256']:
            return False
        checker, limit = (shutil.which(n) for n in ('lrat_isa', 'prlimit'))
        if not checker or not limit:
            return False
        with tempfile.TemporaryDirectory(prefix='omega-lrat-replay-') as root:
            dimacs, certificate = Path(root)/'query.cnf', Path(root)/'query.lrat'
            dimacs.write_bytes(data); certificate.write_bytes(raw)
            prefix = [limit, '--core=0:0', '--as=1073741824:1073741824', f'--fsize={MAX_PROOF_BYTES}:{MAX_PROOF_BYTES}', '--']
            return _check(prefix, checker, dimacs, certificate, root, timeout)
    except (ValueError, TypeError, OSError, subprocess.SubprocessError, binascii.Error):
        return False
