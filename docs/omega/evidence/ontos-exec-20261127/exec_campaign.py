from dataclasses import asdict
import hashlib
import json
from omega_x_evolution.ontos_exec_boundary import Identity, TenantRegistry, run_exec_episode
from omega_x_evolution.ontos_observation_policy import SEEDS, run_observation_episode

if __name__ == '__main__':
    registry=TenantRegistry((Identity('alpha',61001,61001),Identity('beta',61002,61002)))
    results=[]
    for i,seed in enumerate(SEEDS):
        tenant=registry.identities[i%2].tenant
        actual=run_exec_episode(registry,tenant,seed)
        assert actual==run_observation_episode(seed)
        raw=json.dumps([asdict(r) for r in actual],sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        results.append(dict(tenant=tenant,seed=seed,steps=len(actual),correct=sum(r.correct for r in actual),trace_sha256=hashlib.sha256(raw).hexdigest()))
    print(json.dumps(results,sort_keys=True,separators=(',',':')))
