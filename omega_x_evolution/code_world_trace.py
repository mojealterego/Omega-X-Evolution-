"""Ground CWM-style line-free execution predictions in validated Omega u16 IR.

This is a data-only, finite AST-step evaluator for the existing ``Program`` IR.
It neither executes arbitrary candidate source nor claims to run Meta CWM.
Predicted traces are untrusted and NEVER authorize mutation/deployment.

Reference: Meta FAIR, CWM: An Open-Weights LLM for Research on Code
Generation with World Models, arXiv:2510.02387, Figure 3, section 2.2.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .polyglot import MASK, OPS, Program, _validated_tree, evaluate

SCHEMA = 'omega-cwm-u16-trace-v1'
BATCH_SCHEMA = 'omega-cwm-u16-batch-v1'
MAX_STEPS = 63
MAX_DEPTH = 8
MAX_PREDICTION_BYTES = 32768
MAX_BATCH = 128
_FIELDS = frozenset({'schema', 'program_sha256', 'x', 'y', 'steps', 'output'})
_STEP_FIELDS = frozenset({'path', 'op', 'value'})
_OPERATORS = frozenset(OPS) | {'x', 'y', 'lit'}
_SHA256 = re.compile(r'[a-f0-9]{64}\Z')
_PATH = re.compile(r'[LR]{0,8}\Z')


def _u16(value: object) -> int:
    if type(value) is not int or not 0 <= value <= MASK:
        raise ValueError('u16 expected')
    return value


def _distinct_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError('duplicate JSON key')
        output[key] = value
    return output


def _parse_json(raw: str) -> Any:
    if type(raw) is not str or len(raw.encode('utf-8')) > MAX_PREDICTION_BYTES:
        raise ValueError('JSON prediction budget')
    try:
        return json.loads(raw, object_pairs_hook=_distinct_pairs,
                          parse_constant=lambda _name: (_ for _ in ()).throw(ValueError('non-finite constant')))
    except (json.JSONDecodeError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError('invalid JSON prediction') from exc


def _validate_prediction(value: object) -> dict[str, Any]:
    obj = _parse_json(value) if type(value) is str else value
    if type(obj) is not dict or obj.keys() != _FIELDS:
        raise ValueError('prediction fields')
    if type(obj['schema']) is not str or obj['schema'] != SCHEMA:
        raise ValueError('trace schema')
    if type(obj['program_sha256']) is not str or _SHA256.fullmatch(obj['program_sha256']) is None:
        raise ValueError('program digest shape')
    _u16(obj['x']); _u16(obj['y']); _u16(obj['output'])
    steps = obj['steps']
    if type(steps) is not list or not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError('trace step budget')
    for step in steps:
        if type(step) is not dict or step.keys() != _STEP_FIELDS:
            raise ValueError('trace step shape')
        if (type(step['path']) is not str or _PATH.fullmatch(step['path']) is None
                or type(step['op']) is not str or step['op'] not in _OPERATORS):
            raise ValueError('trace instruction shape')
        _u16(step['value'])
    return obj


def trace_program(program: Program, x: int, y: int) -> dict[str, Any]:
    """Independently replay a bounded AST and emit immutable-value observations.

    Postorder step paths are L/R child edges from the root. Every intermediate
    value follows u16 modular semantics. This is *not* a Python stack trace.
    """
    tree = _validated_tree(program)
    x = _u16(x)
    y = _u16(y)
    steps: list[dict[str, Any]] = []

    def walk(node: tuple, path: str) -> int:
        op = node[0]
        if op == 'x':
            result = x
        elif op == 'y':
            result = y
        elif op == 'lit':
            result = node[1]
        else:
            left = walk(node[1], path + 'L')
            right = walk(node[2], path + 'R')
            if op == 'add':
                result = (left + right) & MASK
            elif op == 'sub':
                result = (left - right) & MASK
            elif op == 'mul':
                result = (left * right) & MASK
            elif op == 'xor':
                result = left ^ right
            elif op == 'and':
                result = left & right
            elif op == 'or':
                result = left | right
            else:
                raise ValueError('unsupported IR operation')
        steps.append({'path': path, 'op': op, 'value': result})
        return result

    out = walk(tree, '')
    if len(steps) > MAX_STEPS or out != evaluate(program, x, y):
        raise RuntimeError('trace and runtime semantics diverged')
    return {
        'schema': SCHEMA,
        'program_sha256': hashlib.sha256(json.dumps(tree, separators=(',', ':')).encode('ascii')).hexdigest(),
        'x': x,
        'y': y,
        'steps': steps,
        'output': out,
    }


def verify_prediction(program: Program, x: int, y: int,
                      prediction: object) -> dict[str, Any]:
    """Compare untrusted predicted events against computed finite IR semantics.

    An invalid prediction is a failure, never a pass. Invalid trusted Program or
    coordinates raise ValueError. This predicate is NOT a proof about arbitrary
    Python code, side effects, unknown compilers, LLM accuracy or RSI alignment.
    """
    expected = trace_program(program, x, y)
    base: dict[str, Any] = {
        'status': 'TRACE_INVALID', 'matched_prefix_steps': 0,
        'first_mismatch_step': None, 'total_expected_steps': len(expected['steps']),
        'semantics_scope': 'FINITE_U16_IR', 'release_authorized': False,
    }
    try:
        predicted = _validate_prediction(prediction)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return base

    for field in ('schema', 'program_sha256', 'x', 'y'):
        if predicted[field] != expected[field]:
            return {**base, 'status': 'TRACE_MISMATCH', 'first_mismatch_step': 0}

    a = expected['steps']
    b = predicted['steps']
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            return {**base, 'status': 'TRACE_MISMATCH',
                    'matched_prefix_steps': i, 'first_mismatch_step': i}
    if len(a) != len(b) or predicted['output'] != expected['output']:
        n = min(len(a), len(b))
        return {**base, 'status': 'TRACE_MISMATCH',
                'matched_prefix_steps': n, 'first_mismatch_step': n}
    return {**base, 'status': 'TRACE_MATCH_FINITE',
            'matched_prefix_steps': len(a),
            'trace_sha256': hashlib.sha256(json.dumps(expected, sort_keys=True,
                             separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest()}


def score_predictions(cases: tuple[tuple[Program, int, int, object], ...]) -> dict[str, Any]:
    """Failure-inclusive exact trace accuracy over an operator-controlled fixture."""
    if type(cases) is not tuple or not 1 <= len(cases) <= MAX_BATCH:
        raise ValueError('batch budget')
    counts = {'TRACE_MATCH_FINITE': 0, 'TRACE_MISMATCH': 0, 'TRACE_INVALID': 0}
    for item in cases:
        if type(item) is not tuple or len(item) != 4:
            raise ValueError('batch record')
        p, x, y, prediction = item
        result = verify_prediction(p, x, y, prediction)
        counts[result['status']] += 1
    return {
        'schema': BATCH_SCHEMA,
        'total': len(cases),
        'matched': counts['TRACE_MATCH_FINITE'],
        'mismatched': counts['TRACE_MISMATCH'],
        'invalid': counts['TRACE_INVALID'],
        'accuracy': counts['TRACE_MATCH_FINITE'] / len(cases),
        'release_authorized': False,
    }


def _nested_tuple(value: object, depth: int = 0) -> object:
    """Convert bounded JSON IR to immutable tree, never evaluating source."""
    if depth > MAX_DEPTH:
        raise ValueError('IR nesting depth exceeded')
    if type(value) is list:
        return tuple(_nested_tuple(v, depth + 1) for v in value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--program', required=True, help='JSON array in Omega u16 IR grammar')
    parser.add_argument('--x', type=int, required=True)
    parser.add_argument('--y', type=int, required=True)
    parser.add_argument('--prediction-file', type=Path)
    args = parser.parse_args()
    if len(args.program) > 8192:
        parser.error('IR JSON budget exceeded')
    try:
        program = Program(_nested_tuple(_parse_json(args.program)))
        if args.prediction_file is None:
            result = trace_program(program, args.x, args.y)
            status = 0
        else:
            with args.prediction_file.open('rb') as stream:
                data = stream.read(MAX_PREDICTION_BYTES + 1)
            if len(data) > MAX_PREDICTION_BYTES:
                raise ValueError('prediction file budget exceeded')
            result = verify_prediction(program, args.x, args.y, data.decode('utf-8'))
            status = 0 if result['status'] == 'TRACE_MATCH_FINITE' else 2
    except (ValueError, UnicodeError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
