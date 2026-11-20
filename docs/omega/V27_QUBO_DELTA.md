# v27 — exact classical QUBO swap delta

Base main: e91113ec70980b2d1dc22066b480e1fd4f2b063e. Production source blob before change: fac96be0ab5434a4831b2a465ae55fdc5bf72cd4. Tested on 2026-11-20 with Python 3.13.5, pytest 9.0.2. Direct Git access failed DNS; source and prior contract test were fetched at the pinned revision through GitHub API and reconstructed byte-identically (verified Git blob hashes). Local execution was an isolated focused subset, not a full repository checkout.

## Scope and invariant

For selected set S, removed element o and inserted element i, the exact new energy is E(S)+quality[o]-quality[i]+sum(diversity(o,j)-diversity(i,j) for j in S excluding o). Symmetric pair contributions retained by both sets cancel. Integer arithmetic needs no numerical tolerance. Full scoring stays in use for k<=4 and final reporting; the delta branch is used only for k>=5. Proposal order, RNG draws, temperature, ties, candidate caps, objective, hardware authorization and provider adapters are unchanged. The objective_evaluations field counts logical evaluated candidates, not full rescoring calls.

## Observed evidence

| ID | Command | Result |
|---|---|---|
| V27-DELTA-RED | python -m pytest -q --strict-markers tests/test_omega_qubo_delta.py (original module) | 4 failed, 32 passed in 0.45s |
| V27-DELTA-GREEN | same command (patched module) | 36 passed in 0.40s |
| V27-DELTA-REG | python -m pytest -q --strict-markers tests/test_omega_qubo_delta.py tests/test_omega_ocean_occurrences.py | 47 passed in 0.39s |
| V27-DELTA-COMPILE | python -m compileall -q omega_x_evolution/quantum.py tests/test_omega_qubo_delta.py | exit 0 |

27 seeded result comparisons across n, k and steps, 8 pair-work bounds and 1 tied-candidate comparison. Existing Ocean contract simulation test blob: 5adfe95d232cbbdd52754049fd639c674858ee59 (11 cases). No skipped tests in this subset.

Measured operation accounting with n=32, k=8, seed=42, steps=128: 3640 -> 1848 diversity calls including initial/final scoring; both use 129 logical evaluations, final energy -9155, indices [4, 8, 9, 10, 17, 22, 23, 31]. Each proposal uses 14 rather than 28 pair terms. This is an operation-count improvement, not a measured latency gain.

Corrected production Git blob: 664cb7ff44d716b628488f33efb9e99c2a6eefc3; SHA-256 e12d75e60f54719f648cc14ab99a87b29d1e98669f053a3cb1cf077542855c88.
New tests Git blob: 64b792374ce8e597ea3aa7299e4d9b75790c7959; SHA-256 818a8265f08e87d7a0b6533e1bde18e261901205dfb9ba03e55618d2d01d32ea.
Local log SHA-256: RED b023c568b969acfabab8268c2fb0786be778413831330f5f718807fa67d6e9ce; GREEN d9cf6bd5c7303b6e771b533eb862a97eee26ae7f7406b4228891c7b3987bf843; REG 79bc0f903bbd1262fffbe756c25c4bb454b096f04b7d64a4c27fb4a1d488e447. Logs are local; the evidence above records their observed summaries and checksums.

PASS only for the tested classical-reference optimization and simulated provider regression. Native Ocean SDK and physical QPU validation remain unverified (dimod and dwave are absent). Full repository regression was not performed. The existing bounded GATE-09 decision remains unchanged. No external submission, credential, deployment, or paid job was used.
