# OMEGA-X ONTOS Ω∞ — v55–v58: causal inference, LP, information and OOD

**Project/branch:** `mojealterego/Omega-X-Evolution-` / `main`  
**Verified base HEAD:** `d7299c39fd3cdd47e6551cfcd8695097aec8fe48`  
**Scope:** finite read-only L8 research contracts; no autonomous action, no changes to operational evaluator, security policy, runtime permissions or scheduler. **New stage GATE-09: NOT PASSED**; prior bounded GATE-09 remains unchanged.  
**Source requirements:** `docs/omega/ONTOS_OMEGA_INFINITY_ROADMAP.md`, v55–v58. Model source: Argon, 91-page ONTOS report SHA-256 `95c2794d9a3b5e237781b296b2aa6da0b6cdb174d6a73e5f754f48e7264edc36`.  
**Research primary references:** Balke & Pearl (1997), [Bounds on Treatment Effects from Studies With Imperfect Compliance](https://ftp.cs.ucla.edu/pub/stat_ser/r199-jasa.pdf); [GUDHI Vietoris–Rips](https://gudhi.inria.fr/python/latest/). Reference use is methodological only; reproduction of published experiments is not claimed.

## v55 — finite binary structural causal models (TESTED, broader stage OPEN)

`ontos_v55_scm.py`: `BinaryIVSCM` with 16 deterministic response types \(X(0),X(1),Y(0),Y(1)\), rational weights, strict validation, exact conditional observational \(P(X,Y\mid Z=z)\), interventional \(P(Y=1\mid do(X=x))\), ATE and harm probability \(P(Y(0)=1,Y(1)=0)\). `Z ⟂ U` is assumed in the model, not inferred from data. The confounding fixture has observed risk difference 1 while the true interventional ATE is 0. Missing observational treatment support returns `None`, not a guessed conditional probability. No oracle or hidden-label access in an agent policy. Native integration/general causal discovery remain OPEN.

## v56 — Balke–Pearl style IV bounds (TESTED, broader stage OPEN)

`ontos_v56_bounds.py`: all 16 binary latent response types, `scipy.optimize.linprog` bounded LP under **exclusion, independent instrument and consistency**. Endpoints of ATE/harm/benefit/\(E[Y(0)]\)/\(E[Y(1)]\) are found by dual simplex and interior-point HiGHS, with primal equality residual and cross-solver objective checks (tolerance 1e-8). The two HiGHS methods are not independent formal proofs. Infeasible observational arms return `INFEASIBLE`; missing counterfactual support yields wide intervals (e.g. \([0,1]\)), never fictitious certainty. Eight random latent distributions, all 16 single-response models and deliberately conflicting instrument data tested. No proof of validity of assumptions for any real dataset. Direct dependency `scipy>=1.11,<2` added to project dependencies.

## v57 — information-theoretic diagnostics (TESTED, broader stage OPEN)

`ontos_v57_causal_metrics.py`: reuse v39 `ontos_information.capacity` and `ontos_metabolism` for prior-dependent mutual information, uniform-intervention Effective Information, numerical Blahut–Arimoto capacity interval (proxy for empowerment with explicitly fixed action/channel domain), and nonnegative finite Value of Information over user-supplied utility matrices. Bits and utility units are distinguished. Observational associations are not silently promoted to `do` channels. General causal identification, policy optimization and semantic planning remain OPEN.

## v58 — frozen synthetic OOD benchmark (TESTED; statistical certification OPEN)

`ontos_v58_ood.py`: true zero-dimensional Vietoris–Rips persistence computed via a minimum spanning tree (MST) on the complete bounded Euclidean graph; no claim of H1 or full dDCA. Test vectors include translated triangles, unit squares, and 32-point subsets from actual held-out cohorts. The operational benchmark remains a **separate Euclidean nearest-reference detector**, calibrated exclusively on development in-distribution samples (`scipy.spatial.cKDTree`), with a fixed 10/10/10 seed split. No holdout truth is passed to fitting or scoring. Point estimate alone does not certify a quality target.

**Suite C: 30 seeds × 240 steps, 2,180 dev-reference inliers, 2,189 dev-calibration inliers, 2,400 holdout samples.**

| Held-out metric | Observed |
|---|---:|
| Actual OOD / in-distribution | 247 / 2,153 |
| True positives / false negatives | 246 / 1 |
| False positives / true negatives | 101 / 2,052 |
| Recall (point estimate) | 99.595% |
| FPR (point estimate) | 4.691% |
| Recall Wilson 95% CI | 97.743% – 99.928% |
| FPR Wilson 95% CI | **3.876% – 5.668%** |
| ROC AUC / Average Precision | 0.998240 / 0.995455 |
| Coverage | 100% |
| VR H0 finite deaths in 32-point dev / holdout subsamples | 31 / 31 |
| Source point goal: ≥70% recall and ≤5% FPR | **PASS (point values only)** |
| Stronger 95% CI goal: lower recall ≥70%, upper FPR ≤5% | **FAIL** |
| Deployment/release approval | **FALSE** |

The high OOD separation arises partly from the **synthetic testbed’s severe variance increase for generated OOD data**; it is not evidence of general OOD robustness or safety in real imagery, language or operational systems. Also, the 10 holdout seeds share a common synthetic generator; Wilson intervals treat individual rows as independent and can be overoptimistic under within-seed correlation. Per-seed cluster bootstrap and external OOD distributions remain OPEN.

## Executed verification

Environment: Python 3.13.5; NumPy 2.3.5; SciPy 1.17.0; pytest 9.0.2; Linux x86-64. Code recovered from checked-in previous ONTOS delta archives and checked against Git blob SHA; direct full repo clone unavailable due DNS. No mocks of production-facing reference functions. Full upstream suite not run.

| Test ID | Command | Result |
|---|---|---|
| L8-RED | `PYTHONPATH=. python -m pytest -q --strict-markers tests/test_ontos_v55_v58.py` before modules | exit 2, `ModuleNotFoundError` |
| L8-GREEN-01 | same command after v55-v58 implementation | 43 passed in 1.45 s |
| L8-REGRESSION-01 | 4 ONTOS test files | 158 passed, **1 failure: missing copied source manifest in test workspace** |
| L8-CI-RED | `-k confidence_gate` before new gate | 1 failed, missing CI gate |
| L8-H0-RED | `-k h0_actual_bounded` before cohort topological summary | 1 failed, missing cohort diagnostics |
| L8-FINAL | `PYTHONPATH=. python -m pytest -q --strict-markers tests/test_ontos_v46_v48.py tests/test_ontos_v49_v51.py tests/test_ontos_v52_v54.py tests/test_ontos_v55_v58.py` | **164 passed in 7.11 s, exit 0** |
| L8-COMPILE | `python -m compileall -q omega_x_evolution tests` | exit 0 |
| L8-REPLAY | `run_suite_c()` executed twice | matching results |

48 new tests (including parameterized cases) + 116 prior ONTOS reference regression tests. Negative tests for malformed fractions, infeasible IV, absent counterfactuals, cap violations, malformed vectors, tampering, and threshold ties. No native 64-bit hardware performance assessment, no authenticated provenance, no training, no real device or production evidence.

## SHA identity and evidence

| File | Git blob SHA | SHA-256 bytes |
|---|---|---|
| `ontos_v55_scm.py` | `9bd6ba9872d5bb63c9ef64b70f4895db45189594` | `90668b54ef2deb568230d3db3c48ca036fee7161405029ab0ede86445d1d0421` |
| `ontos_v56_bounds.py` | `0c91758e65ba24d2418a79bdd60cf440d98dc1ed` | `f7a2caa9cb7c442215e2f955e1dd8c990e59fbe03be3ad41de5f22a24c159930` |
| `ontos_v57_causal_metrics.py` | `474506464ab38617aa53b7e7412c48ae0ca2bf22` | `065b7f717b9313c941ec703702f3808aec3cf47ceebcd936065965d425f7f8e1` |
| `ontos_v58_ood.py` | `534baf1790cf0db8ff86285e0fd7100c4abb352b` | `25f8757f63920f56b7bcafa831369a5755003dc999543d7335aa4013b59bb7c5` |
| `test_ontos_v55_v58.py` | `23f5cca1ea113a340efb58fa2861c46195a42e37` | `18455d9fac0579d811962ff8a9b4da0f55419b3175f834dbe5ee82a56c95702d` |
| `V58_SUITE_C_HOLDOUT.json` | `b8d31698094dab42497896724ce620386ecedd07` | `813bda7be2048e77254518fd476121769ce60a2a8ece46b4d07bdf6947ec25b3` |
| `V55_V58_TEST.log` | `cd24643a4c6c9fff406dc0c820bb9137e8b14ae4` | `4faa21b91c9850574a45140e494b2258d35c1f94be6845cdff9fcd0930cb7e14` |

## Gate disposition

- **GATE-01/02:** bounded requirements and assumptions documented.
- **GATE-03/04:** code implemented, tested on local offline subset; 164/164.
- **GATE-05:** new modules integrated with previously checked-in v39, v37 and v54 references; no full runtime E2E.
- **GATE-06:** strict input bounds, no evaluator changes; not a comprehensive security audit.
- **GATE-07:** deterministic replay; no physical device recovery tests.
- **GATE-08:** SHA and commands recorded; machine-readable Suite C report.
- **GATE-09:** no new PASS; v58 95% confidence target FAIL, full source code/program and operational integration remain OPEN. Original bounded GATE-09 unchanged.

**Next backlog:** v59–v62 (oscillator, sheaf, fault and proofreading) after outstanding v55–v58 extensions, seed-level intervals, native instrumentation and authentic datasets.
