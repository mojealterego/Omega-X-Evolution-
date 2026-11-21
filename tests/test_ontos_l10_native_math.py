"""Native x86 and freestanding WebAssembly check RTL-defined fixed-point blend."""
from pathlib import Path
import ctypes
import json
import os
import random
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]
C=ROOT/'native/ontos_l10_q16.c'
SV=ROOT/'hardware/rtl/ontos_q16_core_v67.sv'
GUARD=ROOT/'hardware/rtl/ontos_static_shell_v67.sv'


def reference(mu, drive, decay):
    d = ((decay+2**31) % 2**32)-2**31
    om = ((65536-d+2**31) % 2**32)-2**31
    m = ((mu+2**31) % 2**32)-2**31
    dr = ((drive+2**31) % 2**32)-2**31
    out = ((d*dr) >> 16) + ((om*m)>>16)
    return ((out+2**31) % 2**32)-2**31


@pytest.fixture(scope='module')
def native_lib(tmp_path_factory):
    out=tmp_path_factory.mktemp('q16_native')/'q16.so'
    c=subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',
                      str(C),'-o',str(out)],capture_output=True,text=True,timeout=20)
    if c.returncode:pytest.fail(c.stderr)
    lib=ctypes.CDLL(str(out))
    fn=lib.ontos_q16_blend
    fn.argtypes=(ctypes.c_int32,ctypes.c_int32,ctypes.c_int32)
    fn.restype=ctypes.c_int32
    return fn


def test_native_c_reference_matches_1000_fixed_point_vectors(native_lib):
    rng=random.Random(39000)
    vectors=[(0,0,0),(65536,0,65536),(65536,-65536,32768),
             (-(2**31), 2**31-1,65536),(2**31-1,-2**31,-65536)]
    vectors.extend(tuple(rng.randrange(-2**31,2**31) for _ in range(3)) for _ in range(1000))
    for args in vectors:
        assert native_lib(*args)==reference(*args)


def test_freestanding_wasm_executes_exact_reference_in_node(tmp_path):
    wasm=tmp_path/'q16.wasm'
    c=subprocess.run(['clang','--target=wasm32','-O2','-nostdlib',
                      '-Wl,--no-entry','-Wl,--export=ontos_q16_blend','-o',str(wasm),str(C)],
                     capture_output=True,text=True,timeout=20)
    if c.returncode:pytest.fail(c.stderr)
    code='''const fs=require('fs');(async()=>{
      const {instance}=await WebAssembly.instantiate(fs.readFileSync(process.argv[1]));
      const f=instance.exports.ontos_q16_blend;
      const cases=[[0,0,0],[65536,-65536,32768],[2147483647,-2147483648,-65536]];
      console.log(JSON.stringify(cases.map(v=>f(...v))));
    })().catch(e=>{console.error(e);process.exit(2)})'''
    p=subprocess.run(['node','-e',code,str(wasm)],capture_output=True,text=True,timeout=20)
    assert p.returncode==0,p.stderr
    values=json.loads(p.stdout)
    assert values==[reference(*row) for row in [(0,0,0),(65536,-65536,32768),(2147483647,-2147483648,-65536)]]


def test_rtl_declares_separate_immutable_static_shell():
    source=SV.read_text(encoding='utf-8')
    guard=GUARD.read_text(encoding='utf-8')
    assert 'module ontos_q16_core_v67' in source
    assert 'module ontos_static_shell_v67' in guard
    for signal in ('icap_write_en','lockdown_out','dfx_decouple','signed_receipt_valid'):
        assert signal in guard
    assert 'EXPECTED_SHELL_SHA256' in guard
    assert 'always_ff' in guard
    assert 'decouple_in' in source
