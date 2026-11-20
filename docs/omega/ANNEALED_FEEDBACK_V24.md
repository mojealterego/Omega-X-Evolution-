# v24 — annealed feedback boundary correction

Base main: `c65536b63cabe7bf8339ae1a16a67a21e49c494c`. No new roadmap stage.

Negative integer actions silently indexed NumPy arrays from the end. Invalid positive indices could be ignored, boolean indices and nonfinite or out-of-domain rewards/weights could corrupt the policy. Both feedback paths now reject invalid values with ValueError. Action 6 remains the documented non-tensor sentinel; valid actions 0–5, fixed TT score, exploration floor, generator, evaluator and promotion gates are unchanged.

## Executed evidence — focused native Python/NumPy

Python 3.13.5, NumPy 2.3.5, pytest 9.0.2; OPENBLAS_NUM_THREADS=1. Git clone was unavailable (DNS failure). The production annealed.py was fetched at the pinned SHA; its original Git blob was verified locally as 61642b50432f4ff2a4fea06a149f257b5e8366f1. For the isolated test, the exact relevant production Expression AST constructor/validator and BIN/FUN definitions were extracted from engine.py (base blob 31c6674ad48a6fd05cfa0859a0c46487124a4a65). No mock feedback or NumPy implementation. This was not a full repository checkout; cluster integration and full suite were not executed.

| ID | Command | Result |
|---|---|---|
| V24-RED | OPENBLAS_NUM_THREADS=1 python -m pytest -q tests/test_omega_annealed_bounds.py | 29 failed, 5 passed, 2 warnings in 0.18s; exit 1 |
| V24-GREEN | same command, corrected module | 34 passed in 0.06s; exit 0 |
| V24-BUILD | python -m compileall -q omega_x_evolution/annealed.py tests/test_omega_annealed_bounds.py | exit 0 |

Tests cover negative/out-of-range and non-integer actions on both paths, nonfinite/out-of-domain and wrong-type rewards, invalid association weights, sentinel preservation, exploration, seeded proposal and TT rank-one reconstruction.

Tested corrected module SHA-256: d9b69f2e95efab3b91d082249c234be07b8c489feb40264db3ab2f08efaae935; Git blob c4c0e6e020522ce2e02d2ced3b797498f55f8990.
Test file SHA-256: b17bfb762daf59866f668022732a5577bbbaa1816c0a7d5c3ad445a8bc0733a6; Git blob d34ee9d8f92490fed83fbbc9092d3259d8b89776.

Local RED log SHA-256 c55dae2ecd9842227e1d9437faabebb9aadfcef8834d1ee86a6f61a7f320f4e0; GREEN log SHA-256 a4e15bdab964997c4484e43be97367891dc0171345e880def3924bd7c34d9322 (local session logs, not stored in repository).

PASS only for tested feedback properties. No native external LLM integration, distributed regression, production validation or final engineering gate is claimed. Existing bounded GATE-09 release decision remains unchanged.
