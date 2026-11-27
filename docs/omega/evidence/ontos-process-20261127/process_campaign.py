"""Reproduce isolated controller/evaluator trace equality on a fixed seed partition."""
from dataclasses import asdict
import hashlib
import json
import multiprocessing
from pathlib import Path
import sys

from omega_x_evolution.ontos_observation_policy import SEEDS, run_observation_episode
from omega_x_evolution.ontos_process_boundary import run_isolated_episode


def main(part):
    seeds=SEEDS[part*15:(part+1)*15]
    records=[]
    before={x.pid for x in multiprocessing.active_children()}
    for seed in seeds:
        rows=run_isolated_episode(seed)
        assert rows==run_observation_episode(seed)
        digest=hashlib.sha256(json.dumps([asdict(x) for x in rows],sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        records.append({'seed':seed,'steps':len(rows),'correct':sum(x.correct for x in rows),'trace_sha256':digest})
    assert {x.pid for x in multiprocessing.active_children()}==before
    Path(f'new-evidence/process-part{part}.json').write_text(json.dumps(records,sort_keys=True,separators=(',',':'))+'\n')
    print(f'{len(records)} episodes / {sum(x["steps"] for x in records)} steps; exact match; no active child leaks')


if __name__=='__main__':
    part=int(sys.argv[1]); assert part in (0,1); main(part)
