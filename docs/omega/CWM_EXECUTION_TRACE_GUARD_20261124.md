# OMEGA-X — CWM Execution Trace Guard (research integration, 2026-11-24)

Repository: `mojealterego/Omega-X-Evolution-`, branch: `main` only.  
Base HEAD inspected before implementation: `93c2cec2ec3490b3dbbefb42149920cca08b9b0c`.

## Research source

Meta FAIR CodeGen Team, **CWM: An Open-Weights LLM for Research on Code Generation with World Models**, arXiv:2510.02387v1 (2025), especially Figure 3 and §2.2: observed interpreter states as supervision for predicted action–observation sequences. User-supplied PDF SHA-256: `661116b39758fbbe43cb4cb15266b6e8f8aab9779d26ab4f96ffe7631858de8a`.

Associated sources for later independent work: **Xing USP** (arXiv:2610.34343v1); **R³Mem** (Findings ACL 2025); **Titans** (NeurIPS 2025). USP already has `usp_contract.py` in the repository. R³Mem and Titans require real neural architectures/training; this patch does **not** simulate those pretrained models.

## Production-facing scope

New `omega_x_evolution/code_world_trace.py`:

- Uses existing, strictly validated `polyglot.Program` (unsigned 16-bit, pure binary expression AST with maximum 63 nodes and depth 8). Revalidates a potentially mutated frozen object using `_validated_tree`.
- Independently calculates each node's output in deterministic **postorder** (`path=''` root, `L/R` children) and compares the complete result against the production `polyglot.evaluate` semantic oracle.
- Produces a canonical schema `omega-cwm-u16-trace-v1` with input coordinates, SHA-256 digest over the exact IR tree, ordered steps and final output.
- Validates untrusted model-predicted traces; exact per-step comparison detects incorrect operations, values, order, omissions, missing inputs and program substitution. Malformed and over-budget traces fail closed.
- Returns `TRACE_MATCH_FINITE`, `TRACE_MISMATCH`, or `TRACE_INVALID`; never grants release authority.
- Supports failure-inclusive batch scoring (maximum 128 cases), and opt-in CLI inspection. No user-supplied code is evaluated, executed, imported or interpreted. No shell/network/process invocation in the module itself.

Command (after placing module in repo):

```bash
python -m omega_x_evolution.code_world_trace \
  --program '["mul",["add",["x"],["lit",3]],["y"]]' --x 5 --y 7

python -m omega_x_evolution.code_world_trace \
  --program '["mul",["add",["x"],["lit",3]],["y"]]' --x 5 --y 7 \
  --prediction-file /path/to/untrusted-model-trace.json
```

The inspection command returns a finite verified trace. Validation exits zero **only** for an exact match, exit 2 for mismatched or structurally invalid predictions; invalid input flags/files use argparse's nonzero exit.

## Safety and claims

This module runs **only** a pure restricted expression tree. A `TRACE_MATCH_FINITE` proves that one provided prediction agrees with this finite interpreter on one `(x,y)` input. It does NOT prove correctness for all possible inputs, observational equivalence of arbitrary programs, external Python execution traces, memory safety of external tools, model alignment, or mutation-release eligibility. It is neither Meta CWM, nor a model, nor a Python sandbox. It is not a formal proof kernel and does not supersede `proof_kernel.py`/`bitproof.py`.

The installed 32B CWM weights are not included; the Meta paper identifies its checkpoints as subject to a noncommercial research license. No claim of running model weights, training, GPU inference, or reproducing Meta's SWE-bench result is made.

## Local verification and evidence class

Procedure: `RED` failing import test; `GREEN`; deliberately introduced failing nested-IR-depth test; fix; re-run.

```bash
PYTHONPATH=. python -m pytest -q tests/test_code_world_trace.py \
  --cov=omega_x_evolution.code_world_trace --cov-branch --cov-report=term-missing
python -m compileall -q omega_x_evolution/code_world_trace.py tests/test_code_world_trace.py
```

The local testbed used a minimal, pinned extraction of the **current GitHub `polyglot.py` contract** to avoid pulling the full repository into an offline container. Results: **60 passed**, **97% branch-aware coverage**; 600 randomized differential cases (`seed=20261124`) versus a separate evaluator, 128 concurrent independent traces, CLI subprocess tests, malformed/forged JSON and program-binding tests. Counts in pytest reflect parametrization; there are fewer Python test function definitions. The GitHub production file was inspected separately through the GitHub connector; this does *not* amount to running the entire repository against actual upstream dependencies.

Evidence: `docs/omega/CWM_EXECUTION_TRACE_EVIDENCE_20261124.json`, local RED/GREEN logs, exact SHA-256 of all patch paths; ZIP manifest. Testbed-only shim is **not committed** to `main`.

Integration boundary: a future provider may emit the same schema, and the adapter can compare predicted vs actual trace as a **non-authorizing** evaluation metric. A `TRACE_MATCH_FINITE` may improve ranking but must not bypass separate formal, safety, budget, human approval or release gates. Model-predicted responses remain untrusted data.

Status: IMPLEMENTED and LOCAL_TESTED for the finite trace evaluator; FULL_REPOSITORY_REGRESSION=NOT_RUN; REAL_CWM_PROVIDER=NOT_CONNECTED; NATIVE_E2E=NOT_RUN; DEPLOYMENT=NOT_DONE. No modification of GATE-09 or Roadmap acceptance states.
