# ONTOS v40–v42 — sampled state, repair-data model and finite logic

Base main: 2a7264d89d3dde61c79e54b30210044e6da81d59. Source: L7 supplemental roadmap, supplied L7 PDF SHA-256 4dc81655621585b8c2443983b6362195c8e548448fd263cb1594e31596c46a19, pp.17–22 (ContinuousCfCCTMCore, RosenMRClosureMonitor, PolyLens, FiniteHeytingAlgebra, NARSTruth). Python 3.13.5, NumPy 2.3.5, pytest 9.0.2. Direct clone blocked by DNS. All five pre-existing subset files (package init, three v37–39 modules, reference tests) verified by Git blob hashes against pinned main. New author-written modules executed locally in isolated subset, no mocks. Full repository regression and wheel not run.

## Scope and engineering decisions

- v40: pure numerical transition using fixed seeded weights, bounded dimensions 1..64, 1–4 adaptive internal ticks, dt in [1e-9,1], bounded finite inputs and symmetric history-weighted pair synchronization. Exact immutable replay for identical inputs in the tested environment. The scalar reference checks each synchronized pair. This is the sampled source-inspired formula, not a full native CfC/CTM architecture or a proof of continuous ODE stability.
- v41: pure fault injection into bounded numerical residual vectors, simulated contraction with fixed integer accounting units, no mutation of source state. Rate = 0.65 * paid/initial_budget * integrity, remaining budget never falls below 15% of original in a paid repair; no debit/no improvement if reserve insufficient. Source's ratio-only rate permits the same improvement for a tiny and a large debit; the regression exposed it and proportional debit closes the modeled defect. TAME radius/horizon values are explicitly proxies, not measured competence or proof of biological closure. No actual host, process or code repair.
- v42: finite polynomial objects represented by fiber cardinalities, forward position maps and backward direction maps, structural type compatibility, checked composition/identity and empty fibers. Finite open-set Heyting implication by union of admissible opens; invalid families rejected. Exhaustive enumeration of all 29 labeled topologies on three points and adjunction for each triple; exhaustive associativity of single-position lenses with fibers up to size two. NARS-inspired finite evidence revision with stable IDs, duplicate/conflicting identity rejection, confidence and frequency, explicit conflict flag and abstention. IDs alone do not prove source independence or authentication. Allostatic mode is a string diagnostic only, never a capability or authorization change. No full NARS inference engine claim.

## Executed test evidence

| ID | Command | Observed result |
|---|---|---|
| V40-42-RED | python -m pytest -q tests/test_ontos_v40_v42.py | missing module, exit 2 |
| V40-42-FIRST | python -m pytest -q tests/test_ontos_v40_v42.py tests/test_ontos_reference.py | 72 passed in 0.19s |
| V41-DOSE-RED | python -m pytest -q tests/test_ontos_v40_v42.py | 1 failed, 32 passed in 0.13s; same repair at different debit |
| V42-MODE-RED | same focused command following new label tests | 6 failed, 33 passed in 0.17s; missing label function |
| V40-42-FINAL | python -m pytest -q tests/test_ontos_v40_v42.py tests/test_ontos_reference.py | 81 passed in 0.17s, exit 0 |
| V40-42-COMPILE | python -m compileall -q omega_x_evolution tests | exit 0 |

39 new tests (12 v40, 7 v41, 19 v42, 1 integration), 42 v37–39 regression tests, no skips. The new integration uses 80 fixed-tape steps, no optimization or autonomous policy. Tests include negative dimensions, nonfinite input, source tick thresholds, budget exhaustion, reserve, invalid topology, duplicate evidence, finite-algebra laws and composition. Full upstream test suite not available.

| File | Tested Git blob | SHA-256 |
|---|---|---|
| ontos_continuous.py | ec35f0d6522190dea8c0cf41a2985bdcd77adf6d | 6d2d97b9c78dd0da535f02839bf5ef0556e574b4cef21191d6de59d7f7d308bd |
| ontos_repair.py | 454fcfb2164722748e486e9067c5b66732893dfd | 5a829302db17c1ed01bbea1ce01a558c5de56517fd3863ee7c24db4dc0dc1ef0 |
| ontos_logic.py | 99f4d433bf6c64088426a4bfb652caa0072a2b54 | 032b96af0b3c74ca31d3dbbe453e7d3e598be55fc862dfd0aafc41e56416393e |
| test_ontos_v40_v42.py | b7544c81211c1be4e67ad165f0b86daedbfc074c | 7be59f821ccfaa7c561e9f7d103673c6a5dc8e32b6f781cfbaaed5645d337c2d |

Local log hashes (raw logs remain local): RED 68cdd9c7f35749f0c0150bd97157a571d9d131283ab4a6ad6819f1b976c94915; FIRST a91c2949f430ac9652b2730e7f70833601f265d955eb3c4a7bfbf0a7f9f27252; DOSE-RED 4bb61a879e55713351f933762620d5e4b1624026d9ff4facb6bf453f127da28e; MODE-RED 3cfc7faaf442d0c6857501d7ef418e0ec04bdb24fe89734df4ecf8a397432aba; FINAL 29688b882702daba3f94de67a7e05a47b991fb404d91135e40997f0650715698.

## Acceptance

GATE-01/02 scoped numerical and finite-algebra contracts documented; GATE-03/04 implemented and tested; GATE-05 focused offline integration and earlier subset regression; GATE-06 input-boundary tests and code review of pure data-only modules, not a global security audit; GATE-07 immutable replay and modeled reserve; GATE-08 recorded commands, source and hashes. v40 PASS within sampled numerical model, native compatibility OPEN. v41 PASS for bounded contraction/debit model, empirical TAME competence measurements OPEN. v42 PASS within finite lens, Heyting and evidence-revision scope, broader NARS formal inference, provenance authentication and general theory OPEN. Existing bounded GATE-09 unchanged; no new release certification. No modification to fixed evaluator, authorization, operational policy, scheduler, secrets or external services. Next research queue v43–v45 retains all prior residuals.
