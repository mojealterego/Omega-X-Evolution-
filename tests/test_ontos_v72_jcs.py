"""JCS vectors and bounded I-JSON admission for v72 receipts."""
import json
import math
import random
import shutil
import struct
import subprocess

import pytest

from omega_x_evolution.ontos_v72_jcs import canonical_json, parse_json


def test_utf16_order_and_mandatory_escaping():
    data = {'\ue000': 1, '\U0001f600': 2, 'a': '\x00\b\t\n\f\r"\\/é'}
    assert canonical_json(data) == '{"a":"\\u0000\\b\\t\\n\\f\\r\\"\\\\/é","😀":2,"\ue000":1}'.encode()


@pytest.mark.parametrize('value, expected', [
    (-0.0, '0'), (5e-324, '5e-324'), (-5e-324, '-5e-324'),
    (1.7976931348623157e308, '1.7976931348623157e+308'),
    (1e21, '1e+21'), (1e20, '100000000000000000000'),
    (1e-6, '0.000001'), (1e-7, '1e-7'),
    (999999999999999700000.0, '999999999999999700000'),
    (333333333.33333329, '333333333.3333333'),
])
def test_number_vectors(value, expected):
    assert canonical_json(value) == expected.encode()
    assert canonical_json(parse_json(expected.encode())) == expected.encode()


@pytest.mark.parametrize('raw', [
    b'{"a":1,"a":2}', b'NaN', b'Infinity', b'1e999', b'"\\ud800"',
    b'\xff', b'[' * 33 + b'0' + b']' * 33, b' ' * (1024 * 1024 + 1),
    b'{"x":1} garbage', b'\xef\xbb\xbf{}',
])
def test_parser_fails_closed(raw):
    with pytest.raises(ValueError): parse_json(raw)


def test_direct_rejects_unsafe_ints_cycles_and_hooks():
    class Evil(dict):
        def items(self): raise AssertionError('custom hook')
    cyclic = []
    cyclic.append(cyclic)
    for obj in (2**53, -(2**53), float('nan'), float('inf'), cyclic, Evil(),
                {'\ud800': 1}, {1: 'value'}, 'a' * (1024 * 1024)):
        with pytest.raises(ValueError): canonical_json(obj)


def test_roundtrip_and_order():
    obj = {'b': [True, False, None, 0.5], 'a': {'z': 1, 'c': -3}}
    wire = canonical_json(obj)
    assert wire == b'{"a":{"c":-3,"z":1},"b":[true,false,null,0.5]}'
    assert parse_json(wire) == obj
    assert canonical_json(parse_json(wire)) == wire


def test_ecmascript_differential_seed_72():
    node = shutil.which('node')
    if node is None:
        pytest.skip('optional independent ECMAScript oracle not installed')
    rng = random.Random(72)
    numbers = []
    for _ in range(10000):
        f = struct.unpack('>d', rng.getrandbits(64).to_bytes(8, 'big'))[0]
        if math.isfinite(f): numbers.append(f)
    encoded = json.dumps(numbers, allow_nan=False)
    run = subprocess.run([node, '-e',
                          'let s=require("fs").readFileSync(0,"utf8");process.stdout.write(JSON.stringify(JSON.parse(s)))'],
                         input=encoded, text=True, capture_output=True, timeout=10, check=True)
    assert canonical_json(numbers).decode() == run.stdout
