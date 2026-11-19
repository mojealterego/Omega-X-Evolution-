"""Paired energy/carbon estimation for actual bounded discovery workloads.

Process CPU seconds are measured; watts per CPU-second and grid intensity are
operator-supplied scenario parameters, never claimed as measured electricity.
No effect on fitness, admission or safety gates.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import threading
import time

from .discovery import TASKS, discover, fixture

_LOCK = threading.Lock()


def _number(x, low, high):
    return type(x) in (int, float) and math.isfinite(x) and low <= x <= high


def _text(x):
    return isinstance(x, str) and 1 <= len(x.strip()) <= 512 and len(x) <= 512


@dataclass(frozen=True)
class Calibration:
    low_w: float
    central_w: float
    high_w: float
    power_source: str
    intensity_g_per_kwh: float
    intensity_source: str

    def __post_init__(self):
        if not (all(_number(x, 0, 10000) for x in (self.low_w, self.central_w, self.high_w))
                and self.low_w <= self.central_w <= self.high_w and self.high_w > 0
                and _number(self.intensity_g_per_kwh, 0, 10000)
                and _text(self.power_source) and _text(self.intensity_source)):
            raise ValueError('invalid power calibration or carbon provenance')


@dataclass(frozen=True)
class Reading:
    wall_ns: int
    cpu_ns: int

    def __post_init__(self):
        if (type(self.wall_ns) is not int or type(self.cpu_ns) is not int
                or not 0 < self.wall_ns <= 86_400_000_000_000
                or not 0 <= self.cpu_ns <= 1024*self.wall_ns):
            raise ValueError('invalid or out-of-range clocks')


def estimate(reading: Reading, calibration: Calibration):
    if not isinstance(reading, Reading) or not isinstance(calibration, Calibration):
        raise ValueError('typed reading and calibration required')
    hours = reading.cpu_ns / 3_600_000_000_000
    energy = {k: getattr(calibration, k+'_w')*hours for k in ('low','central','high')}
    carbon = {k: v*calibration.intensity_g_per_kwh/1000 for k,v in energy.items()}
    return {'method':'estimated-process-cpu', 'energy_wh':energy, 'carbon_g':carbon,
            'scope':'process CPU only; excludes idle, GPU, DRAM, network, embodied carbon',
            'interval':'operator power scenario bounds, not statistical confidence interval; intensity fixed'}


def counter_energy(start_uj, end_uj, range_uj, elapsed_ns, max_w):
    """Validate a counter delta with at most one wrap under a trusted power bound.

    Only meaningful for a monotonic cyclic counter with no reset. No automatic
    hardware claim: callers must establish the bound and counter provenance.
    """
    if (any(type(x) is not int for x in (start_uj,end_uj,range_uj,elapsed_ns))
            or not 1 <= range_uj <= 2**63-1 or not 0 <= start_uj < range_uj
            or not 0 <= end_uj < range_uj or not 0 < elapsed_ns <= 86_400_000_000_000
            or not _number(max_w, 0.001, 10000)):
        raise ValueError('counter contract')
    maximum = max_w * elapsed_ns / 1000
    delta = (end_uj-start_uj) % range_uj
    if maximum >= range_uj or delta > maximum:
        raise ValueError('counter wrap ambiguous or implausible')
    return delta


def _hardware():
    cpu = platform.processor()
    if not cpu:
        try:
            with open('/proc/cpuinfo', encoding='utf-8') as f:
                cpu = next((l.split(':',1)[1].strip() for l in f if l.startswith('model name')), '')
        except OSError:
            pass
    return {'machine':platform.machine(),'system':platform.system(),'cpu':cpu or 'unknown',
            'python':platform.python_version(),'clock':'perf_counter_ns/process_time_ns',
            'code_sha256':{name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                           for name in ('green.py','discovery.py','engine.py')}}


def paired_discovery(*, calibration: Calibration, task='squares', seed=42, budget=128, repeats=3):
    if (not isinstance(calibration,Calibration) or task not in TASKS
            or type(seed) is not int or not 0 <= seed < 2**32
            or type(budget) is not int or not 1 <= budget <= 4096
            or type(repeats) is not int or not 2 <= repeats <= 8
            or 2*budget*repeats > 32768):
        raise ValueError('paired workload bounds')
    data = fixture(task,seed=seed)
    methods = ('enumeration','evolution')
    runs = []
    with _LOCK:
        # Warm both actual implementations; setup/warmup excluded from profiles.
        for method in methods:
            discover(data,seed=seed,budget=min(8,budget),strategy=method)
        for i in range(repeats):
            for method in (methods if i%2==0 else methods[::-1]):
                wall0=time.perf_counter_ns();cpu0=time.process_time_ns()
                result=discover(data,seed=seed,budget=budget,strategy=method)
                cpu=time.process_time_ns()-cpu0;wall=time.perf_counter_ns()-wall0
                reading=Reading(wall,cpu)
                runs.append({'pair':i,'strategy':method,'result':result,'reading':asdict(reading),
                             'estimate':estimate(reading,calibration)})
    pairs = {(r['pair'],r['strategy']):r for r in runs}
    deltas=[];quality=[]
    for i in range(repeats):
        a,b=(pairs[i,m] for m in methods)
        deltas.append(b['estimate']['energy_wh']['central']-a['estimate']['energy_wh']['central'])
        aa,bb=a['result']['holdout_rmse'],b['result']['holdout_rmse']
        quality.append(None if aa is None or bb is None else bb-aa)
    return {'schema':'omega-green-v1','mode':'estimated-process-cpu','task':task,'seed':seed,
            'dataset_sha256':data.digest(),'budget_per_run':budget,'repeats':repeats,
            'calibration':asdict(calibration),'hardware':_hardware(),'runs':runs,
            'comparisons':{'equal_proposal_budget':True,'candidate':'evolution','baseline':'enumeration',
                           'paired_energy_delta_wh':deltas,'median_energy_delta_wh':statistics.median(deltas),
                           'paired_holdout_rmse_delta':quality},
            'limitations':'CPU time is measured for the process, not an isolated meter; results are host-specific, not a carbon reduction claim.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--task', choices=TASKS, default='squares');p.add_argument('--seed',type=int,default=42)
    p.add_argument('--budget',type=int,default=128);p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--watts',type=float,nargs=3,metavar=('LOW','CENTRAL','HIGH'),required=True)
    p.add_argument('--power-source',required=True);p.add_argument('--intensity',type=float,required=True)
    p.add_argument('--intensity-source',required=True)
    a=p.parse_args()
    try:
        c=Calibration(*a.watts,a.power_source,a.intensity,a.intensity_source)
        report=paired_discovery(calibration=c,task=a.task,seed=a.seed,budget=a.budget,repeats=a.repeats)
    except ValueError as exc:
        p.error(str(exc))
    print(json.dumps(report,indent=2,allow_nan=False))


if __name__=='__main__':
    main()
