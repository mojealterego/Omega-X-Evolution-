"""Reproducible L10 engineering gate; reports only evidence actually executed.

This runner never upgrades modeled evidence to production verification and
never executes candidate-generated instructions or arbitrary source files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
GATES=ROOT/'docs/omega/ONTOS_L10_V63_V67_GATES.json'
TESTS=(
    'tests/test_ontos_v46_v48.py',
    'tests/test_ontos_v49_v51.py',
    'tests/test_ontos_v52_v54.py',
    'tests/test_ontos_v55_v58.py',
    'tests/test_ontos_v59_v62.py',
    'tests/test_ontos_phase0_diagnostics.py',
    'tests/test_ontos_extensions_docs.py',
    'tests/test_ontos_v63_v66.py',
    'tests/test_ontos_v63_v66_campaign.py',
    'tests/test_ontos_v67_dfx.py',
    'tests/test_ontos_l10_formal.py',
    'tests/test_ontos_l10_release.py',
    'tests/test_ontos_l10_native_boundary.py',
    'tests/test_ontos_l10_native_math.py',
    'tests/test_ontos_l10_gate.py',
)


def _sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_sources(manifest:dict)->bool:
    for name,expected in manifest['source_sha256'].items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or _sha(path)!=expected:
            return False
    return True


def _invoke(command:list[str], *, cwd:Path, timeout:int, env:dict[str,str]):
    try:
        proc=subprocess.run(command,cwd=cwd,env=env,capture_output=True,text=True,
                            timeout=timeout,check=False)
        return {'status':'PASS' if proc.returncode==0 else 'FAIL',
                'exit_code':proc.returncode, 'stdout':proc.stdout[-1800:],
                'stderr':proc.stderr[-1800:]}
    except (OSError,subprocess.TimeoutExpired) as err:
        return {'status':'BLOCKED', 'error':type(err).__name__}


def run()->dict:
    manifest=json.loads(GATES.read_text(encoding='utf-8'))
    if manifest['schema']!='ontos-l10-closeout-v1' or not verify_sources(manifest):
        return {'model_gate':'FAIL','full_l10_gate':'BLOCKED',
                'reason':'source inventory checksum mismatch'}
    env={**os.environ,'PYTHONPATH':str(ROOT),'OPENBLAS_NUM_THREADS':'1',
         'GOTOOLCHAIN':'local','GOPROXY':'off','GOSUMDB':'off'}
    jobs={
        'compileall':_invoke([sys.executable,'-m','compileall','-q','omega_x_evolution','scripts','tests'],cwd=ROOT,timeout=30,env=env),
        'pytest':_invoke([sys.executable,'-m','pytest','-q','--strict-markers',*TESTS],cwd=ROOT,timeout=300,env=env),
        'go_race':_invoke(['go','test','-race','-count=1','./...'],cwd=ROOT/'native/ontos-l10-gateway',timeout=120,env=env),
    }
    passed=all(x['status']=='PASS' for x in jobs.values())
    return {'schema':'ontos-l10-execution-v1','model_gate':'PASS' if passed else 'FAIL',
            'full_l10_gate':'BLOCKED','native_rust_zenoh_wasi_verified':False,
            'physical_fpga_verified':False,
            'source_suite_d_reproduced':False,'jobs':jobs}


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-full',action='store_true')
    args=parser.parse_args()
    result=run()
    print(json.dumps(result,sort_keys=True,indent=2,allow_nan=False))
    if result['model_gate']!='PASS':return 1
    return 2 if args.require_full else 0


if __name__=='__main__':
    sys.exit(main())
