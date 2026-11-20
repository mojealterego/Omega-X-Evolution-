# v27 — Ocean aggregated-read accounting

Base main: `aa239c1823c557b90657f26f5efe2dc2face1e96`. Mode: DETERMINISTIC-SIMULATION for the Ocean SDK boundary; NATIVE for classical QUBO and Python compilation. A new corrective increment, not a new roadmap stage.

Ocean SampleSet may aggregate duplicate reads into one row with num_occurrences (https://docs.dwavequantum.com/en/latest/ocean/api_ref_dimod/generated/dimod.SampleSet.from_samples.html). Previously the adapter ignored this count. The production adapter now requires an integral positive multiplicity, bounds cumulative reads before expanding, and preserves local fitness verification. The callback contract and explicit paid submission authorization remain unchanged.

## Evidence

Python 3.13.5, isolated copy of exact original Git blob c1fba4ff8fac0d54cdce832f94886eba660df01c, actual NumPy integer used; SDK response is contract-simulated, not a native Ocean installation. No external QPU submission.

- V27-OCC-RED: `python -m pytest -q tests/test_omega_ocean_occurrences.py`: 8 failed, 3 passed in 0.13s; exit 1. Under-count, overflow and malformed multiplicities reproduced.
- V27-OCC-GREEN: same command: 11 passed in 0.04s; exit 0.
- V27-OCC-BUILD: `python -m compileall -q omega_x_evolution tests`: exit 0 (isolated copied module and tests).
- V27-OCC-SMOKE: `python -m omega_x_evolution.quantum --seed 42 --steps 512`: exit 0, exact and classical annealing both energy -3724, indices [2,7,9,15], 1820 and 513 objective evaluations respectively.

Source SHA-256: quantum.py 35fe86e2e2b89d83a4193c48270b570133da8715be437e63301de7ecdcb7bccb; tests 3878ab7089eb07f30ef7dd35cb2820c5e850a121b62c573b452cf1a8cd0bc127. Verified focused source blob IDs: fac96be0ab5434a4831b2a465ae55fdc5bf72cd4 and 5adfe95d232cbbdd52754049fd639c674858ee59.

PASS for aggregate read-accounting property in the tested contract. Native Ocean dependency and full repository regression were not available in this session (container DNS failed, SDK absent). Native SDK compatibility remains open; no new GATE-09 decision.
