"""Reproduce fixed native sandbox trace comparisons; execute as a script."""
from dataclasses import asdict
from hashlib import sha256
import json
import multiprocessing
import os
import sys

from omega_x_evolution.ontos_observation_policy import SEEDS, run_observation_episode
from omega_x_evolution.ontos_sandbox import run_sandboxed_episode


def main(part):
    seeds=SEEDS[part*15:(part+1)*15]
    before={p.pid for p in multiprocessing.active_children()}
    records=[]
    for seed in seeds:
        actual=run_sandboxed_episode(seed)
        assert actual==run_observation_episode(seed)
        raw=json.dumps([asdict(row) for row in actual],sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        records.append({'seed':seed,'steps':len(actual),'correct':sum(x.correct for x in actual),'trace_sha256':sha256(raw).hexdigest()})
    assert before=={p.pid for p in multiprocessing.active_children()}
    report={'parent_uid':os.getuid(),'episodes':records,'total_steps':sum(r['steps'] for r in records),'exact_reference_match':True,'active_child_leaks':False,'release_authorized':False}
    print(json.dumps(report,sort_keys=True,separators=(',',':')))


if __name__=='__main__':
    part=int(sys.argv[1]);assert part in (0,1);main(part)
