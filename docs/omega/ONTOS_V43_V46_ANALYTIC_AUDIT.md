# ONTOS v43/v46 — independent zero-gradient and statistical reference audit

Base main: 258f4a822f620e010d94212cfad39e7007b407f3. Date: 2026-11-20. Implementation is a new, isolated synthetic numerical audit, not an import of private source code or a pretrained checkpoint.

## Scope and rationale

Analytic fitting is not the same as obtaining pretrained semantic knowledge without data. SVD reconstructs a known linear operator, not a monosemantic SAE. RLS estimates an affine predictor given observations without optimizer or gradient updates. Neither creates the weights of a large pretrained JEPA encoder. A pre-existing qualified encoder and independent representation/holdout evidence are still needed. No model loading, model export, runtime adaptation, promotion, safety-control modification or generated action execution is provided.

For v46, the fixed Bernoulli null is p=1/4 and the alternative is p=1/2. The likelihood ratio factors 2 and 2/3 have unit expectation. Exact rational enumeration covers all 4096 paths of length 12, weighted by their null probabilities. A crossing of wealth 20 corresponds to a Ville bound 1/20. The comparator clamps wealth to at least one after each update. This comparator loses the unit-expectation property; it is not valid merely by reusing the original proof. This is a counterexample for a fixed statistical diagnostic, not a replacement test or a certified sequential policy, and not a statement about all possible e-process formulations.

## Reproducible results

Python 3.13.5; NumPy 2.3.5; pytest 9.0.2. An isolated namespace-package subset contained the two new files only. Direct git access failed DNS; no full regression or wheel build.

| ID | Command | Observed result |
|---|---|---|
| V43-46-RED | python -m pytest -q tests/test_ontos_analytic_audit.py | exit 2, missing module |
| V43-46-GREEN | OPENBLAS_NUM_THREADS=1 python -m pytest -q tests/test_ontos_analytic_audit.py | 9 passed, 0.19s |
| V43-46-COMPILE | python -m compileall -q omega_x_evolution tests | exit 0 |
| V43-46-CAMPAIGN | evaluate analytic_audit for seeds 9100+29*i, i=0..29, then repeat | 30/30 replay identical; max holdout MSE 5.030621544383152e-16; max RLS/batch coefficient difference 7.771561172376096e-16 |

Seed 42: train 64 rows, holdout 32, 0 gradient steps, SVD reconstruction error 1.2424228414451936e-15, batch/RLS difference 2.220446049250313e-16, holdout MSE 4.875383022562045e-16, persistence MSE 0.11891243297122521. Known noiseless linear ground truth; not a benchmark of general or visual intelligence.

Exact stopping audit: total null mass=1; terminal expected wealth=1; clamped comparator terminal expectation=2.7757409811019897; crossing probability=0.011269092559814453, below 0.05. Finite horizon only. No changes to operational evaluator, gates or statistical acceptance.

## Integrity

| Artifact | Git blob or SHA-256 |
|---|---|
| ontos_analytic_audit.py Git blob | 256429cd85564f8365d302561c50e6ec37b686fe |
| ontos_analytic_audit.py SHA-256 | b6ef0febb0be97bdd1fdd4bb8ce194e47cf045fcbfe0e5f302783894d8f8172f |
| test_ontos_analytic_audit.py Git blob | dde02aeb67a0892e4fd1a6036010b012fc84c6b1 |
| test_ontos_analytic_audit.py SHA-256 | 8b47d52c89b6e143d7c40bbdc51997ee1a64b5f64853258e994055ec55caf3bb |
| Local RED log SHA-256 | d2bb7f6caf330836106464f028251d03a73dd5bb26c2d0c250c864328c6e7136 |
| Local GREEN log SHA-256 | 5e57a2b2595d85d09977593cf77dfe39775b2732484bc91bd38d1223f0243d6d |
| Local 30-seed JSON evidence SHA-256 | 33cf4a60854d63ffb8771d2bc99463e4fa69c4e7b443bde628e79bfe26e5b89a |

Local artifacts not embedded in public repository; command and sample data reproducible from source.

## Status

v43 analytic reference sub-contract TESTED; realistic frozen encoder, native SAE/JEPA integration and large model evidence OPEN. v46 fixed-null optional-stopping sub-contract TESTED; full PACE/VaG/GSAI/SAE diagnostic coverage OPEN. v47 and v48 not completed or tested by this increment. Existing bounded GATE-09 unchanged. No runtime integration or production acceptance. No private source data, weights or documents included.
