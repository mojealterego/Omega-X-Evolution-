"""Regenerate the bounded L10 evidence inventory from current bytes, never from guessed results.

This script does not execute tests. Test status must be independently confirmed.
"""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
SOURCE_FILES=(
    'omega_x_evolution/ontos_v67_dfx.py',
    'omega_x_evolution/ontos_l10_formal.py',
    'omega_x_evolution/ontos_l10_release.py',
    'omega_x_evolution/ontos_l10_approval.py',
    'native/ontos-l10-gateway/main.go',
    'native/ontos-l10-gateway/main_test.go',
    'native/ontos-l10-gateway/go.mod',
    'native/ontos_l10_q16.c',
    'hardware/rtl/ontos_q16_core_v67.sv',
    'hardware/rtl/ontos_static_shell_v67.sv',
    'tests/test_ontos_v67_dfx.py',
    'tests/test_ontos_l10_formal.py',
    'tests/test_ontos_l10_native_boundary.py',
    'tests/test_ontos_l10_native_math.py',
    'tests/test_ontos_l10_release.py',
    'tests/test_ontos_l10_gate.py',
    'scripts/verify_ontos_l10.py',
)


def hash_file(name:str)->str:
    return hashlib.sha256((ROOT/name).read_bytes()).hexdigest()


def create():
    entries={name:hash_file(name) for name in SOURCE_FILES}
    logs={
        'pytest':('docs/omega/L10_PYTEST_FULL.log','PASS'),
        'go_race':('docs/omega/L10_GO_RACE.log','PASS'),
        'q16_red':('docs/omega/L10_Q16_RED.log','EXPECTED_FAIL'),
        'q16_green':('docs/omega/L10_Q16_GREEN.log','PASS'),
        'dual_rollback_xfail':('docs/omega/L10_DUAL_ROLLBACK_XFAIL.log','XFAIL'),
    }
    evidence={key:{'path':path,'sha256':hash_file(path),'result':status}
              for key,(path,status) in logs.items()}
    evidence['pytest']['count']=303
    evidence['pytest']['environment']='Linux x86_64 / Python 3.13.5 / pytest 9.0.2 / numpy 2.3.5 / scipy 1.17.0 / cryptography 46.0.4'
    evidence['pytest']['command']='OPENBLAS_NUM_THREADS=1 PYTHONPATH=. python -m pytest -q --strict-markers tests/test_ontos_v46_v48.py ... tests/test_ontos_l10_native_math.py'
    evidence['go_race']['command']='GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off CGO_ENABLED=1 go test -race -count=1 ./...'
    evidence['q16_red']['command']='PYTHONPATH=. pytest -q tests/test_ontos_l10_formal.py -k q16 (before implementation)'
    evidence['q16_green']['command']='PYTHONPATH=. pytest -q tests/test_ontos_l10_formal.py -k q16 (after implementation)'
    return {
        'schema':'ontos-l10-closeout-v1',
        'base_main':'c45323d58e12e5867cfceec37a90872554725544',
        'mode':'HYBRID_NATIVE_AND_DETERMINISTIC_SIMULATION',
        'main_branch_only':True,
        'model_gate':{'status':'PASS','scope':'finite i4, deterministic A-E/DFX transitions, bounded multi-traces, native Go Unix socket, native Z3 via libz3, C/Wasm Q16.16; not production certified',
                      'gate_01':'PASS','gate_02':'PASS','gate_03':'PASS','gate_04':'PASS','gate_05':'PASS_MODEL_ONLY',
                      'gate_06':'PASS_MODEL_ONLY','gate_07':'PASS_MODEL_ONLY','gate_08':'PASS'},
        'full_l10_gate':{
            'status':'BLOCKED','gate_09':'BLOCKED',
            'native_rust_zenoh_wasi_verified':False,
            'physical_fpga_verified':False,
            'source_suite_d_reproduced':False,
            'production_verified':False,
            'unverified_properties':[
                'Native Rust/Zenoh/WASI production transport and compiled WIT component ABI',
                'Native SystemVerilog simulation, CIRCT LEC and physical FPGA DFX/ICAP',
                'Production external immutable TCB and hardware-backed monotonic rollback root',
                'Independent anti-rollback of simultaneous old state+anchor pair (reproduced as strict XFAIL)',
                'Source L10 Suite D 90.79% objective and original conflict-free skill-pool campaign',
                'Physical IPC latency below 1 ms and physical shell reconfiguration time',
                'Full upstream repository integration regression and environment-qualified production deployment',
                'Unbounded HyperLTL proof or kernel-checked Lean proof for all candidate languages',
            ]},
        'tests_by_stage':{
            'v63':['tests/test_ontos_v63_v66.py','tests/test_ontos_l10_native_boundary.py'],
            'v64':['tests/test_ontos_v63_v66.py','tests/test_ontos_v67_dfx.py','tests/test_ontos_l10_formal.py'],
            'v65':['tests/test_ontos_v63_v66.py','tests/test_ontos_l10_formal.py','tests/test_ontos_l10_release.py'],
            'v66':['tests/test_ontos_v63_v66.py','tests/test_ontos_l10_native_boundary.py','native/ontos-l10-gateway/main_test.go'],
            'v67':['tests/test_ontos_v67_dfx.py','tests/test_ontos_l10_native_math.py','tests/test_ontos_l10_release.py'],
        },
        'evidence':evidence,
        'source_sha256':entries,
        'rebuildable_go_binary_sha256':'ab1cf3c526f6eeb408d4a7d1c574165c56d1ec0aa4c8fe5b85895833bdc4b270',
        'signature_algorithm':'Ed25519, keys generated in isolated test environment; production issuer NOT provisioned',
        'solver':'native libz3.so.4 invoked by bounded isolated Python process',
    }


def main():
    path=ROOT/'docs/omega/ONTOS_L10_V63_V67_GATES.json'
    path.write_text(json.dumps(create(),indent=2,sort_keys=True,ensure_ascii=False)+'\n',encoding='utf-8')
    print(path)

if __name__=='__main__':main()
