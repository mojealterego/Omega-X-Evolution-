# ONTOS v43–v45 — fixed-data audit and finite mathematical references

Base main: 2547b1173f62a17b033b8e69246df1a8deee15c4. Source: L7 roadmap, supplied L7 PDF SHA-256 4dc81655621585b8c2443983b6362195c8e548448fd263cb1594e31596c46a19; pages 22–26 (Titans/CMS, JEPA, Hopfield, VSA, temporal graph), 7–9 and 18–19 (assembly and causal quantities). Python 3.13.5, NumPy 2.3.5, pytest 9.0.2. Direct Git clone failed DNS. Existing nine subset source/test files byte-identified against pinned Git blobs; no mocks. New code and prior reference tests executed together in the isolated subset. No wheel build or full upstream regression.

## Scope

- v43: fixed synthetic two-dimensional dataset, 96 generated samples split 64/16/16, linear multirate fit at clocks 1/4/16, fixed zero-weight comparator. Learned state remains local; metrics only, no model export or live promotion. Holdout and retention are disjoint same-distribution samples, not a test of catastrophic forgetting or continual learning across regimes. Collapse diagnostic is a simple variance ratio, not VICReg. Native Titans/HOPE/JEPA and their integrated training remain OPEN. Existing operational memories and policies unchanged.
- v44: immutable bounded snapshot (256 facts) of synthetic bitemporal records, separate valid-time half-open interval and known-at transaction timestamp, latest applicable revision, provenance labels, duplicate and overlapping same-transaction rejection. Namespace filtering is logical, not authentication. No database writes or live consolidation. Fixed Hopfield one-step energy and cosine-deviation diagnostic with quarantine flag; VSA bipolar binding/unbinding measurement with explicit bit-error rate, not error correction or a learned retrieval system. Durable production integration, authenticated provenance and broader retention remain OPEN.
- v45: exact tiny string assembly cost over all binary decompositions, union of distinct nonterminal substrings; any reusable construction unfolds to such a tree and each union is constructible by increasing substring length. Domain ASCII alphanumeric length 1..8. Separate midpoint heuristic, not a generic greedy minimum. Separate independent BFS checks all 62 binary strings of length 1..5; bounds checked for all 126 of length 1..6. Finite EI under uniform interventions, macro transition with uniform within-cell interventions, CP defined explicitly as EI/log2(number of states), delta macro minus micro. Validated partition and known interventions only; no causal inference from observation-only data, no general CE2.0 result or physical Assembly Theory proof. Uncertainty for learned transition matrices remains OPEN.

## Actual executed evidence

| ID | Command | Result |
|---|---|---|
| V43-45-RED | python -m pytest -q tests/test_ontos_v43_v45.py | exit 2, missing module (collection) |
| V43-45-FIRST | python -m pytest -q tests/test_ontos_v43_v45.py tests/test_ontos_v40_v42.py tests/test_ontos_reference.py | 108 passed in 0.24s |
| V43-45-ORACLE | same command with independent BFS, KL and added seeds | 115 passed in 0.22s |
| V44-VSA-RED | python -m pytest -q tests/test_ontos_v43_v45.py | 1 failed, 35 passed in 0.13s, missing VSA diagnostic |
| V43-45-FINAL | python -m pytest -q tests/test_ontos_v43_v45.py tests/test_ontos_v40_v42.py tests/test_ontos_reference.py | 117 passed in 0.24s, exit 0 |
| V43-45-COMPILE | python -m compileall -q omega_x_evolution tests | exit 0 |

36 new tests (9 signal, 6 history/prototypes, 21 mathematical), 81 prior regression cases; no skips. Synthetic seed 42: update counts [64,16,4], holdout MSE 0.00391682686644042 vs zero comparator 0.09663833834296531; retention MSE 0.004796542381459259 vs 0.1229816766880561. Five seeds checked. This easy fixed target is not evidence of superior agent learning. VSA fixed 30% bit flips result in 30% bit error rate and cosine 0.4; not correction. Three-state example EI micro = H(2/3,1/3), macro = 1 bit under explicit partition. Exact small mathematical references only.

| File | Tested Git blob | SHA-256 |
|---|---|---|
| ontos_signal_audit.py | 68a733da22c95f296918a16d058eb2f731d43220 | c742211e9f31a9b98bcc2f599e4978e070da4a7e4a7706f76a03ef061eeeae4e |
| ontos_history.py | ca0bb738f974b17588afbbe493f021591d4c6577 | b12070121f6651e3b46facd5b20db5442972eae8e9db3325fa0078ddb3d81777 |
| ontos_metrics.py | ac0e221ff41b87ef97a14c6fb4a9fd3e5ed32626 | 83d45f0afad42cc3a9b519c4ce1cc33690e4ca8567a8f322e30d4b24af2f5ecd |
| test_ontos_v43_v45.py | c110d7f6ae679af74184389bd2d99010e2c08ce1 | bfb24335e6284336faa446313e0964dd544b7c1b7285754ab573bd69a9513c4e |

Local log SHA-256: RED 683beb1bcde5431e7b27a7ef027a7b87d4e8ee1befda43423762b2a12e7b2aed; FIRST 566e25577cc73e8f1d806ef39648a2b7ed5a154185d23b77dae54e3867f4dbb9; VSA-RED 11b77bfdff7b750c1b8f267f74ce17a6301c5afebb70cfefb826ec175eec9bad; FINAL 791ab4ea21eecca22d3cee837fb1e66ca1718896ad8d5585f2e0856340950d1e. Raw logs remain local.

## Gate disposition

GATE-01/02 scoped requirements and numerical definitions documented; GATE-03/04 implementation and focused tests; GATE-05 prior isolated ONTOS regression, not full runtime integration; GATE-06 local data bounds, no authorization or system isolation claim; GATE-07 deterministic rerun and immutable history; GATE-08 evidence and hashes; preserve existing bounded GATE-09, no new release certification. v43 fixed synthetic audit TESTED, v44 finite snapshot and diagnostic contracts TESTED, v45 exact tiny string and finite channel references PASS in stated domain; broader requirements remain OPEN. No operational self-modification, runtime adaptation, evaluator changes, credentials, external execution or deployment. All previous residuals retained.
