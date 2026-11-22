# OMEGA-X / HYPERION-X — research intake and finite conformal compute advisory

**Date:** 2026-11-22  
**Target:** `mojealterego/Omega-X-Evolution-`, existing `main` only  
**Source:** user-supplied 24-page `Projekt Zaawansowanego Silnika AI.PDF`, especially pp. 1–3, 9, 16, 18–19.  
**SHA-256 of source:** see adjacent evidence manifest.

## Source triage: five HYPERION-X layers

| HYPERION-X layer | Document proposals | OMEGA-X intake decision |
|---|---|---|
| 1: causality and data | TabSyn, OT-CFM, do-calculus, selection bias | Research-only: not a license to fabricate causal identification; requires causal graph, conditioning and separate validation population |
| 2: hybrid geometric sequence core | Mamba-2/SSD, FlashAttention-4, EGNN, E(n) equivariance | Hardware/model research only; CPU/NumPy benchmarks cannot be substituted for real GPU benchmarks |
| 3: neuro-symbolic reasoning | DeepLog, CDCL/Kissat, MCGS/Lean, Wake–Sleep/RLVR | Explore as bounded proof-bearing extensions; do not accept AI-generated axioms as proof or bypass existing audit kernel |
| 4: uncertainty and generalization | split/weighted conformal, RAPS, PAC-Bayes | **Implemented here**: finite, fail-closed conformal threshold and optional non-authorizing compute-budget advisory |
| 5: training and silicon | Muon, SPlus, FOAM, RGD, Triton/XLA, NVFP4/TurboQuant | Hold for hardware-qualified benchmarks, dimensionality/dtype checks, memory-footprint and correctness tests |

## Mathematical scope and proof assumptions

New `omega_x_evolution/hyperion_conformal.py` uses a finite list of **nonnegative conformity violations** (higher is worse), `n<=4096`, and `alpha in [0.001,0.5]`.

For split conformal the threshold is the `(1-alpha)`-quantile of **n observed calibration scores plus a test atom at +infinity**. For covariate shift, each calibration observation uses a caller-supplied nonnegative density ratio `w_i`; the test atom has positive weight `w_test`:

`Q_(1-alpha)[ sum_i w_i delta_(s_i) + w_test delta_(+infinity) ]`.

The weighted quantile is found from numerically bounded input using `Decimal` weighted accumulation to avoid unsafe floating-point threshold switches. `+infinity` yields `UNBOUNDED` and **abstention**, never a fake finite confidence band. `effective_n` is Kish's diagnostic `(sum w_i)^2 / sum(w_i^2)`, **not** a guarantee of coverage.

Claims are *conditional*:
- Unweighted finite-sample marginal coverage needs calibration/test exchangeability.
- Known-ratio covariate shift requires the actual density ratio, unchanged `Y|X`, supported target distribution, and the relevant weighted exchangeability assumptions.
- For **estimated** ratios there is **no automatic exact finite-sample coverage claim**; routing can demand extended verification.
- The code does **not** attest the source's claim of known weights; `assumptions_attested=false` and `coverage_certified=false` always.

Reference: Tibshirani, Barber, Candes, Ramdas (2019), *Conformal Prediction Under Covariate Shift*, NeurIPS, https://proceedings.neurips.cc/paper/2019/hash/8fb21ee7a2207526da55a679f0332de2-Abstract.html .

## Interface and safety

`calibrate(scores, alpha=..., weights=..., test_weight=..., ratio_source=..., source_id=...)` returns a frozen `Calibration`. `route_budget(calibration, BudgetPolicy(...), expected_digest=...)` returns one of `BASELINE_COMPUTE`, `EXTENDED_VERIFICATION`, `ABSTAIN_INSUFFICIENT_CALIBRATION`. SHA-256 is the content integrity identifier for a canonical set of score/weight pairs; **it is not a signature and does not prove who made the inputs**. The comparison digest must be pinned by a separately trusted caller. `export_jsonl()` writes a fixed payload with **no raw calibration inputs**, no labels, no scripts and `release_authorized=false`.

No automatic mutation approval, write to model weights, code generation, external calls, parallel scheduler modification, data-center power estimates, or hardware speed claims. Integrate only as an **opt-in advisory** in a future explicit acceptance-gated control path. A decision of `BASELINE_COMPUTE` is a compute suggestion, **not a truth guarantee**.

## Corrections and evidence hygiene

1. The document's statement around Cook–Levin and `P != NP` must not be treated as a theorem proving `P != NP`: Cook–Levin shows SAT NP-complete; `P` versus `NP` remains open (Clay Mathematics Institute).
2. Measured 168.47x CPU/NumPy vs naive attention is benchmark-specific. It is **not** evidence of 168.47x GPU production inference speedup for OMEGA-X.
3. Weighted conformal coverage claimed for a fitted density ratio requires additional accuracy/assumption checks; neither the source's 90.33% example nor the new module proves universal coverage under arbitrary drift.
4. PAC-Bayes guarantees are bound to the model, prior, posterior and selected data assumptions in the certificate, not any arbitrary replacement model.
5. The report contains proposed architectures and numbers; a Python test of this new finite conformal algorithm does not verify Mamba-2, FA-4, Lean 4, Triton, FHE, CDCL, or a HYPERION-X system deployment.

## Verification and status

- TDD RED: `PYTHONPATH=. python -m pytest -q tests/test_hyperion_conformal.py` failed because the new module did not exist.
- GREEN: `PYTHONPATH=. python -m pytest -q tests/test_hyperion_conformal.py` **66 PASS** including seeded synthetic coverage sanity checks.
- `PYTHONPATH=. python -m coverage run --branch --source=omega_x_evolution.hyperion_conformal -m pytest -q tests/test_hyperion_conformal.py` and `coverage report -m`: **100% branch-inclusive coverage** of *new module only*.
- `python -m compileall -q omega_x_evolution/hyperion_conformal.py tests/test_hyperion_conformal.py`: PASS.
- No direct integration into engine/cluster execution, no native model training, full repository regression, remote CI or hardware validation. GATE-09 is unchanged.

## Licensing and roadmap

Original implementation from published mathematical specification, not copied from external third-party repos. Supplied PDF serves as a research reference and does not itself create mandatory requirements. No additions to obligatory ONTOS L11–L111 roadmap and no change to historical acceptance statuses.
