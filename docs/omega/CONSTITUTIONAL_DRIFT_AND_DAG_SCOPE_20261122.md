# OMEGA-X Evolution — finite constitutional drift probe + bounded DAG regression

**Date:** 2026-11-22. **Target:** `main`.
**Base:** `57704ae3c24ed2ea0d2d46316721116b1f1b2322`.
**Scope:** optional research strengthening, not a new mandatory Roadmap commitment.

## Audit versus the user's eight proposals

| Proposal | Inspected existing implementation | Engineering decision |
|---|---|---|
| Async/Await and step_life_cycle | `omega_x_evolution/engine.py` (`run`, `_run`) and `cluster.py` (`run_cluster`) are already `async`; no `step_life_cycle` or specified `main.py` was found in the inspected OMEGA-X codebase | Do not fabricate a parallel life-cycle runner. Existing cluster uses `asyncio.wait(FIRST_COMPLETED)`, bounded in-flight jobs and checkpoint CAS. Full MCP/Titans integration requires actual adapters. |
| Constitutional Shield and preference drift | `rsi_ir_guard.py` has pinned policy SHA-256, non-escalation, narrow modular-u16 equivalence | Add `constitutional_drift.py`: bounded external constitution, drift calculation, critical-case refusal, source/approval caveats. |
| DAG / GoT stress | `graph_memory.py`: 4096 nodes, 16384 edges, authenticated snapshot and `retrieve(hops<=3)` | Add 7 deterministic traversal stress cases for 0/1/2/3 hops, dense overlaps and cyclic references. Tests exercise a byte-for-byte extracted `GraphMemory.expand` method in local staging, NOT full production GraphMemory/database. |
| Prometheus/JSONL | `ontos_observability.py` and `cluster_green.py` already implement bounded exports | No duplicate exporters or invented wall power estimates. |
| Grover/quantum-neuromorphic tree search | `quantum.py` is already bounded research | Grover `O(sqrt N)` is a quantum oracle-query result, not a claim of faster classical DAG traversal; no hardware claim. |
| TDA and JEPA | No verified proof of preventing collapse at 10M tokens from supplied claim | Defer to measured representation-quality comparisons and memory/compute budgets. |
| Lean/Coq | `proof_kernel.py`, `lean_native.py` already provide limited kernel-compatible contracts | Don't substitute finite theorem proofs for global value alignment; leave current trusted checker unchanged. |
| FHE / tokenomics | Prior encryption/resource accounting modules | FHE alone does not stop prompt injection, unauthorized tool access or exfiltration; no autonomous monetary transfers or arbitrary infrastructure expansion. |

## Finite constitutional contract

`ConstitutionalCase`: strict ASCII identifier, finite set of named allowable actions, one operator-approved reference action, optional `protected` flag. `ConstitutionalSpec`: 1–128 cases, maximum permitted deviation count ONLY among nonprotected cases; duplicate IDs forbidden; deterministic canonical SHA-256 digest.

`assess_drift()` requires the externally supplied trusted spec digest and complete caller-provided observations. Unapproved actions, missing/extra IDs and protected deviations are rejected. Noncritical deviations have an operator-defined exact finite limit. An observed ratio of mismatches is a descriptive finite metric — **not the Hamming distance to human values** and not proof of CEV. A forged or inaccurate observation can still claim the approved label, so every accepted result is marked `CALLER_SUPPLIED_UNATTESTED`.

`review_rsi_with_drift()` composes the existing `review_candidate()` with these tests. It never returns release authorization; a passing candidate is only `CANDIDATE_FOR_HUMAN_REVIEW` based on the submitted finite sample. Candidate code cannot change the trusted external digests without mismatch detection; however, this function does not itself attest that the digests came from secure external storage. No arbitrary code execution, hardware communication, crypto key storage or DPO training is added.

## Test evidence and limitations

- **RED:** `PYTHONPATH=. python -m pytest -q tests/test_constitutional_drift.py` → exit 2, missing import for `omega_x_evolution.constitutional_drift`.
- **GREEN:** `PYTHONPATH=. python -m pytest -q tests/test_constitutional_drift.py tests/test_rsi_ir_guard.py` → **56 passed**, exit 0. Python 3.13.5, pytest 9.0.2, Linux x86_64.
- **Coverage:** `python -m pytest -q --cov=omega_x_evolution.constitutional_drift --cov-branch --cov-report=term-missing ...` → **98%** for this module (71 statements, 1 missed; branch coverage included in report).
- **Isolated DAG stress:** `PYTHONPATH=. python -m pytest -q tests/test_graph_memory_dag_bounded.py` → **7 passed** against a staging-only method extracted verbatim from the current `graph_memory.py` (`GraphMemory.expand` lines 176–187). NOT a full regression of native GraphMemory, SQLite or GoT. Production integration remains **OPEN**.
- **Compile:** `python -m compileall -q omega_x_evolution/constitutional_drift.py tests/test_constitutional_drift.py tests/test_graph_memory_dag_bounded.py` → exit 0.
- Baseline SHA checks: `rsi_ir_guard.py` blob `02c0330b1a8603760e26373f845bed0e107f175c`, `polyglot.py` `53289dcf148ad7159af67ae2e997eeae0a41ca85`, `proof_kernel.py` `18a121abd8b2a5e665ef232653f31e827236ba9e` match main GitHub blobs before local tests.
- Test IDs: `test_const_001` through `test_const_013` (18 parameter-expanded instances); `test_graph_001` through `004` (7 parameter-expanded instances); 38 existing RSI guard tests.

## Acceptance

- GATE-01/02: bounded behavioral contract and composition identified, locally reviewed.
- GATE-03/04: source implemented, local tests PASS for narrow constitutional probes and extracted DAG traversal.
- GATE-05: with the actual existing RSI guard PASS on imported source; actual `GraphMemory` database integration **NOT TESTED**.
- GATE-06: fail closed on tampering, privileges, action domain and all protected-case drift within test model; provenance of observed model decisions **UNATTESTED**.
- GATE-07: no stateful durability or recovery added; NOT APPLICABLE to this pure function.
- GATE-08: SHA-256 and RED/GREEN logs supplied.
- GATE-09: **OPEN** for new full-system functionality; historical bounded GATE-09 unchanged.

Follow-up must instrument a separately trusted evaluator to generate observations from real model behavior, secure the external constitution anchor, and run full CI/GraphMemory tests and active runtime integration. Never reclassify model-supplied claims as verified observations.
