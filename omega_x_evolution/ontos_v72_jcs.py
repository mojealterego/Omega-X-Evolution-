"""ONTOS v72: bounded RFC 8785-style canonical JSON for evidence preimages.

Uses finite binary64 number semantics. Direct Python integers outside the safe
integer range are rejected; JSON decimal tokens outside that range are parsed
as binary64, not as exact identifiers. This is not an evidence schema validator.
"""
from __future__ import annotations

import json
import math
from typing import Any

MAX_BYTES = 1024 * 1024
MAX_DEPTH = 32
MAX_NODES = 65536
MAX_SAFE_INT = 2**53 - 1


def _number(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError('nonfinite binary64 number')
    if value == 0:
        return '0'
    sign = '-' if value < 0 else ''
    mantissa, _, exponent = repr(abs(value)).partition('e')
    exp = int(exponent or '0')
    whole, _, frac = mantissa.partition('.')
    digits = (whole + frac).lstrip('0')
    exp -= len(frac)
    trimmed = digits.rstrip('0')
    exp += len(digits) - len(trimmed)
    digits = trimmed
    n = exp + len(digits)
    if len(digits) <= n <= 21:
        result = digits + '0' * (n - len(digits))
    elif 0 < n <= 21:
        result = digits[:n] + '.' + digits[n:]
    elif -6 < n <= 0:
        result = '0.' + '0' * (-n) + digits
    else:
        result = digits[0] + ('.' + digits[1:] if len(digits) > 1 else '') + f'e{n-1:+d}'
    return sign + result


def _string(value: str) -> bytes:
    if len(value) > MAX_BYTES:
        raise ValueError('string exceeds input budget')
    try:
        return json.dumps(value, ensure_ascii=False).encode('utf-8')
    except UnicodeError as exc:
        raise ValueError('invalid Unicode scalar') from exc


def canonical_json(value: Any) -> bytes:
    """Return canonical UTF-8 bytes, rejecting invalid or excessive inputs."""
    output = bytearray()
    nodes = 0

    def emit(data: bytes) -> None:
        if len(output) + len(data) > MAX_BYTES:
            raise ValueError('canonical output exceeds byte budget')
        output.extend(data)

    def visit(obj: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_NODES:
            raise ValueError('JSON node budget exceeded')
        typ = type(obj)
        if obj is None:
            emit(b'null')
        elif typ is bool:
            emit(b'true' if obj else b'false')
        elif typ is int:
            if not -MAX_SAFE_INT <= obj <= MAX_SAFE_INT:
                raise ValueError('direct integer exceeds exact safe range')
            emit(str(obj).encode('ascii'))
        elif typ is float:
            emit(_number(obj).encode('ascii'))
        elif typ is str:
            emit(_string(obj))
        elif typ in (list, dict):
            if depth >= MAX_DEPTH or len(obj) > MAX_NODES - nodes:
                raise ValueError('JSON container budget exceeded')
            if typ is list:
                emit(b'[')
                for i, child in enumerate(obj):
                    if i: emit(b',')
                    visit(child, depth + 1)
                emit(b']')
            else:
                if any(type(k) is not str for k in obj):
                    raise ValueError('JSON object keys must be strings')
                if sum(len(k) for k in obj) > MAX_BYTES:
                    raise ValueError('JSON key budget exceeded')
                try:
                    keys = sorted(obj, key=lambda k: k.encode('utf-16-be'))
                except UnicodeError as exc:
                    raise ValueError('invalid Unicode key') from exc
                emit(b'{')
                for i, key in enumerate(keys):
                    if i: emit(b',')
                    emit(_string(key)); emit(b':')
                    visit(obj[key], depth + 1)
                emit(b'}')
        else:
            raise ValueError('unsupported JSON value type')

    visit(value, 0)
    return bytes(output)


def _check_depth(text: str) -> None:
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in '[{':
            depth += 1
            if depth > MAX_DEPTH:
                raise ValueError('JSON nesting exceeds bound')
        elif char in ']}':
            depth -= 1
            if depth < 0:
                raise ValueError('invalid JSON nesting')


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for k, v in items:
        if k in obj:
            raise ValueError('duplicate JSON key')
        obj[k] = v
    return obj


def _parse_int(token: str) -> int | float:
    if len(token) > 310:
        raise ValueError('integer token exceeds binary64 range')
    value = int(token)
    return value if -MAX_SAFE_INT <= value <= MAX_SAFE_INT else float(token)


def _reject_constant(token: str) -> Any:
    raise ValueError('nonstandard JSON constant')


def parse_json(raw: bytes) -> Any:
    """Admit bounded UTF-8 JSON; reject duplicates, nonfinite and lone surrogates."""
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError('bounded JSON bytes required')
    try:
        text = raw.decode('utf-8')
        _check_depth(text)
        obj = json.loads(text, object_pairs_hook=_pairs, parse_int=_parse_int,
                         parse_constant=_reject_constant)
        canonical_json(obj)
        return obj
    except (UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError('invalid JSON encoding or numeric range') from exc
