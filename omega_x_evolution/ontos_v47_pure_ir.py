"""Typed, *finite* i4 IR compatibility reference. No source or host execution.

The serializer emits only a small explicitly modeled MLIR-like arith subset.
Without a native MLIR parser/compiler this is not native MLIR certification.
Complete domain checking is exhaustive only for this 4-bit, 2-input grammar.
"""
from dataclasses import dataclass
import hashlib
import json

_BINARY = {
    'add': 'addi', 'sub': 'subi', 'mul': 'muli',
    'xor': 'xori', 'and': 'andi', 'or': 'ori',
}
_MASK = 0xF


def _validate(tree: tuple, depth: int = 0) -> int:
    if type(tree) is not tuple or not tree or depth > 6:
        raise ValueError('IR tuple/depth invariant')
    op = tree[0]
    if type(op) is not str:
        raise ValueError('IR opcode type')
    if op in ('x', 'y') and len(tree) == 1:
        return 1
    if op == 'lit' and len(tree) == 2 and type(tree[1]) is int and 0 <= tree[1] <= 15:
        return 1
    if op in _BINARY and len(tree) == 3:
        nodes = 1 + _validate(tree[1], depth + 1) + _validate(tree[2], depth + 1)
        if nodes > 48:
            raise ValueError('IR node budget')
        return nodes
    raise ValueError('unsupported typed IR operation')


@dataclass(frozen=True)
class PureIR:
    tree: tuple

    def __post_init__(self) -> None:
        _validate(self.tree)


def _eval(tree: tuple, x: int, y: int) -> int:
    op = tree[0]
    if op == 'x':
        return x
    if op == 'y':
        return y
    if op == 'lit':
        return tree[1]
    left = _eval(tree[1], x, y)
    right = _eval(tree[2], x, y)
    if op == 'add':
        return (left + right) & _MASK
    if op == 'sub':
        return (left - right) & _MASK
    if op == 'mul':
        return (left * right) & _MASK
    if op == 'xor':
        return left ^ right
    if op == 'and':
        return left & right
    if op == 'or':
        return left | right
    raise AssertionError('unreachable after validation')


def evaluate(program: PureIR, x: int, y: int) -> int:
    if (
        type(program) is not PureIR or type(x) is not int
        or type(y) is not int or not (0 <= x <= 15 and 0 <= y <= 15)
    ):
        raise ValueError('validated i4 inputs required')
    tree = program.tree
    _validate(tree)
    return _eval(tree, x, y)


def _digest(tree: tuple) -> str:
    data = json.dumps(tree, separators=(',', ':'), ensure_ascii=True).encode('ascii')
    return hashlib.sha256(data).hexdigest()


def compare(left: PureIR, right: PureIR, *, max_cases: int = 256) -> dict:
    if (
        type(left) is not PureIR or type(right) is not PureIR
        or type(max_cases) is not int or not 1 <= max_cases <= 256
    ):
        raise ValueError('comparison contract')
    left_tree, right_tree = left.tree, right.tree
    _validate(left_tree)
    _validate(right_tree)
    common = {'left_sha256': _digest(left_tree), 'right_sha256': _digest(right_tree)}
    checked = 0
    for x in range(16):
        for y in range(16):
            if checked == max_cases:
                return {**common, 'verdict': 'UNKNOWN_BOUND', 'domain_cases': checked,
                        'counterexample': None, 'semantics': 'pure i4; two inputs'}
            checked += 1
            if _eval(left_tree, x, y) != _eval(right_tree, x, y):
                return {**common, 'verdict': 'FAIL_COUNTEREXAMPLE',
                        'domain_cases': checked, 'counterexample': (x, y),
                        'semantics': 'pure i4; two inputs'}
    return {**common, 'verdict': 'PASS_EXHAUSTIVE', 'domain_cases': 256,
            'counterexample': None, 'semantics': 'pure i4; two inputs'}


def render_mlir_subset(program: PureIR) -> str:
    """Deterministic text for a modelled arith subset; not an executable adapter."""
    if type(program) is not PureIR:
        raise ValueError('IR required')
    tree = program.tree
    _validate(tree)
    lines = ['func.func @compute(%x: i4, %y: i4) -> i4 {']
    index = 0

    def walk(t: tuple) -> str:
        nonlocal index
        op = t[0]
        if op in ('x', 'y'):
            return '%' + op
        if op == 'lit':
            name = '%' + str(index)
            index += 1
            lines.append(f'  {name} = arith.constant {t[1]} : i4')
            return name
        a, b = walk(t[1]), walk(t[2])
        name = '%' + str(index)
        index += 1
        lines.append(f'  {name} = arith.{_BINARY[op]} {a}, {b} : i4')
        return name

    result = walk(tree)
    lines.extend([f'  func.return {result} : i4', '}'])
    return '\n'.join(lines) + '\n'
