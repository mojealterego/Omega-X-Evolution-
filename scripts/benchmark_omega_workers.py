"""Compare serial and process-pool results on exactly the same offline campaign."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
import time


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    records = []
    for seed in (5, 17, 77):
        results = []
        for processes in (1, 2):
            start = time.perf_counter()
            output = subprocess.check_output([sys.executable, '-m', 'shinka.omega', '--seed', str(seed), '--generations', '5', '--evaluation-processes', str(processes)], cwd=root, timeout=60)
            results.append((json.loads(output), round(time.perf_counter()-start,6)))
        serial, parallel = results
        if serial[0] != parallel[0]:
            raise RuntimeError(f'backend result mismatch: seed {seed}')
        records.append({'seed': seed, 'matches': True, 'attempts': serial[0]['attempts'], 'champion_score': serial[0]['champion_score'], 'serial_seconds': serial[1], 'process_pool_seconds': parallel[1]})
    print(json.dumps({'python':sys.version.split()[0], 'note':'Wall time includes process startup; single observation per configuration, not a throughput benchmark.', 'records':records}, indent=2))


if __name__ == '__main__':
    main()
