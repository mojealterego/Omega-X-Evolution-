# Acceptance gates and residual backlog — v20

> **Current acceptance policy:** [Mandatory execution directive v3.0](EXECUTION_DIRECTIVE_V3.md) supersedes conflicting historical criteria. External audits, third-party certification and physical infrastructure reruns are not required. Accepted deterministic engineering simulations close modeled properties. Native/production claims and functional or mathematical obligations remain distinct.


A bounded implementation is not the same as complete production validation. No task below is silently converted to a pass. This register supersedes outstanding-status summaries in earlier development snapshots while retaining their historical evidence.

| Previously open item | State at v20 | Evidence / next acceptance condition |
|---|---|---|
| v19 multi-domain discovery | Implemented; local | Four dimension-aware synthetic domains, custom data, isolated train/validation/test, reproducible report |
| v20 research runtime | Implemented; local | Seven-domain E2E, authenticated checkpoints, idempotent graph publication and replay, bounded device/work policy |
| v9 outer population checkpoint | Implemented and tested | Durable alternate runner matches the original full report on regression fixture, old source bytes unchanged |
| v7/v13 larger formal proof scope | Extended; bounded | QF_BV proof for an individual u16 program pair over 2^32 inputs; arbitrary programs and compiler equivalence still open |
| Accelerator training | Implemented; CPU proven | Actual isolated Torch CPU training, verified against NumPy. CUDA/MPS/Ascend modeled numerical/resource contracts accepted via v36.1; native hardware attestation separate |
| Qualcomm Hexagon HTP | Adapter implemented; simulation only | Static ONNX exporter and strict QNN provider configuration. Modeled numerical/resource contracts accepted; actual exporter/provider compatibility distinct; no physical device prerequisite |
| Semantic GraphRAG | Extended; local | Actual corpus LSA retrieval, provenance; optional loopback HTTP quote-selector protocol tested on fake server, not actual LLM. Pretrained semantic embeddings and generated answer quality open |
| Packaging | Wheel built and smoke-tested | Actual wheel and isolated-target installation. Full dependency installation and MkDocs site still open |
| Physical GPU/NPU and multi-host cluster | Closed for v36.1 modeled properties | Physical accelerator/cluster availability is not a gate; production evidence separate |
| Upstream full pytest | Open — dependencies | Historical 72 errors; v36.2 offline overlay collected 1556 with 1547 passing. Full dependency resolution remains distinct. Do not skip or stub failures. |
| External AlphaEvolve/DGM comparison | Open | No equivalent external implementation, shared experimental budget or reproducible external workloads run |
| Universal arbitrary program synthesis, unbounded theorem proving, large-model training, general scientific discovery | Research open | Defined limited IR/MLP/dataset bounds; no claims beyond verified scope |

All twenty stages contain local executable implementations in the agreed bounded scope. Remaining gates above must not be marked production-proven without appropriate evidence. No credentials, private key, test database, active GitHub workflow or paid provider execution is included. The maintainer has defined v21 (Stage 3 performance regression gate); see [v21 evidence and scope](EVOLUTION_V21.md). v22 adds durable asynchronous island actors, actual local process transport and a 256-island logical simulation; Ray package availability and external multi-host deployment remain open. v23 implements bounded adaptive phenotype geometry; further source requirements are registered in [the extended maintainer roadmap](MAINTAINER_ROADMAP.md). See [v22](EVOLUTION_V22.md).

V24–v26 implement classical tensor-train mutation routing, bounded associative trajectory transfer and candidate-specific binary64 safety obligations. See [v24–v26](EVOLUTION_V24_V26.md). No generalized speed/quality advantage, physical Ray, live LLM policy or arbitrary theorem proving is claimed. Pending v30–v36 remain in the maintainer roadmap.

V27–v29 extend the system with bounded QUBO selection, typed retrieval architecture search and authenticated independent peers; physical QPU, external federated infrastructure, arbitrary architecture synthesis and consensus remain open. See [v27–v29](EVOLUTION_V27_V29.md).

V30–v32 implement reversible optional-block switches, constructive u16 certificate checking and one-shot signed quorum partitioning with durable execution records. See [v30–v32](EVOLUTION_V30_V32.md). Lean/Isabelle installation and actual kernel verification remain open; one-shot quorum safety is not a live Byzantine consensus protocol. Pending v33–v36.

V33–v35 implement bounded grammar-generated modular conjectures and finite algebra enumeration, rank-1/2 LoRA on the frozen contextual mutation router, and local Linux process orchestration with charged durable reservations. See [v33–v35](EVOLUTION_V33_V35.md). General axiomatic discovery, LLM weight adaptation, external resource allocation and multi-host orchestration are not accepted. v36 green computing remains open.

**v35.1 formal-safety closure (requirements 1–4):** mandatory pre-empirical proof gate, independent rational endpoint checker, general bounded CTL/K modal engine, immutable audit binding and append-only certified rule snapshots in canonical core and cluster. See [acceptance](FORMAL_SAFETY_CLOSURE.md). The bounded expression language is the accepted domain; arbitrary executable host code, full semantic functional correctness and unrestricted axiom discovery are not proved. No new roadmap stage. Other review items remain open.

**v35.2 corrective extension:** [existing requirements 5–12](REMAINING_REQUIREMENTS_CLOSURE.md) now have expanded executable, locally tested contracts and explicitly recorded limitations. Physical QPU, pretrained LLM/CUDA, Lean/Isabelle, external Kubernetes provisioning, full production BFT liveness and general scientific novelty remain unverified. No v36 work.

**v35.3:** [residual acceptance](RESIDUAL_ACCEPTANCE.md) supersedes the prior dependency count: 36 collection errors, 911 collected; 310 OMEGA tests and 38 native hardening tests pass, plus 103 selected upstream tests. Certified pacemaker fault scenarios pass, but universal liveness, external proof assistants, large pretrained-model training and physical infrastructure are still open. No v36 work.

**v35.4:** [Residual recovery and acceptance evidence](RESIDUAL_RECOVERY_V354.md): 320 OMEGA tests pass, 38 hardening tests pass; 1336 collected with 12 upstream collection errors. Bounded BFT recovery and composite architecture synthesis extended. External proof kernels, large pretrained training, general liveness, unrestricted synthesis and physical infrastructure remain open. v36 remains open.

**v35.5:** [Terminal-round recovery and dependency verification](RESIDUAL_RECOVERY_V355.md): 322 OMEGA and 38 native hardening tests pass; 36 selected upstream tests pass; 1463 collected with 4 errors in an experimental offline overlay. Certified BFT terminal-round retry and durable monotonic synthesis quotas implemented. Lean/Isabelle, general BFT liveness, unrestricted synthesis, large pretrained LLM and physical validation remain open. v36 remains open.

**v36.0:** [Green Computing and certified round synchronization](EVOLUTION_V36.md): 331 OMEGA tests, 38 isolated hardening tests, two integer SMT obligations and 199296 actual leader-rotation cases passed. Green Computing accepted in the documented estimated-energy scope; no measured electricity or production claim. BFT authenticated round catch-up added. Full collection: 1472 tests, 4 errors. GATE-09 remains BLOCKED for the remaining mandatory requirements; earlier open-v36 statements are historical.

**v36.1 — deterministic engineering acceptance:** [modeled contracts, evidence and residual gates](SIMULATION_ACCEPTANCE_V361.md). OMEGA v2.3 §5: successful deterministic simulation closes the corresponding engineering property without a mandatory physical rerun. Native and production claims are separate. Earlier infrastructure-only blocker statements are superseded; no mathematical, compatibility or dependency failure is concealed.

**v36.2:** [Extended round recovery, streaming synthesis and upstream recovery](RESIDUAL_RECOVERY_V362.md). Historical round-31 deadlock reproduced and fixed in signed deterministic execution. Streaming search crosses 8192 evaluations with a durable cursor; retained grammar limits are explicit. Upstream dependency recovery and remaining acceptance conditions are recorded separately.

**v36.3:** [Native Lean bootstrap and proof acceptance](NATIVE_LEAN_V363.md). Actual offline Lean 4.36.0-pre compiler built from upstream sources, 50-module portable proof runtime; extensional equations over BitVec 16 × BitVec 16 verified natively for tested additive cases, false equality rejected, shared proof adapter and replay. Full Std/CaDiCaL and Isabelle remain open. GATE-09 remains partially blocked.

**v36.4:** [Native BitVec expansion and source inventory](NATIVE_BITVEC_V364.md). Kernel-checked lemma route spans all six u16 IR operators; 376 core tests passed on independent packaged runtime. 173-module upstream BitVec.Lemmas closure built; portable runtime and build cache preserved. Full BVDecide, Isabelle and other residual obligations remain open.

**v36.4 corrective v31 LRAT continuation:** [native LRAT certificate and replay](NATIVE_LRAT_V365.md). CaDiCaL 3.1.0 and native Isabelle-exported lrat_isa independently check the generated CNF proof; exact IR binding, stored certificate replay without solver, externally required promotion policy and malformed-certificate rejection are tested. 52 focused tests passed (33 LRAT, 19 portable IR), plus two recovered native Lean smoke proofs. Full Std/BVDecide and native Isabelle theory build are not yet accepted; GATE-09 is not closed.

**v36.4 corrective v31 Std/BVDecide continuation:** [native Std/BVDecide evidence](NATIVE_STD_BVDECIDE_470.md). 128 additional upstream modules compiled successfully, with full `Std.Tactic.BVDecide`, parser and checker; 470 delta modules preserved. Six actual u16 reflection theorems and independent native binary LRAT checks passed for the tested identities. Full `Lean.Elab.Tactic.BVDecide` and native Isabelle theory build remain open; GATE-09 NOT closed.


**v36.4 v3.0 corrective continuation:** [native checkpoint increment 470→488](NATIVE_STD_BVDECIDE_488.md): 66 pinned source files and 18 successfully compiled modules added, verified reconstruction and native replay. GATE-09 still not PASS; external infrastructure and certification are no longer prerequisites under v3.0.


**v36.4 native checkpoint increment 488→500:** [build and replay evidence](NATIVE_STD_BVDECIDE_500.md). 92 additional pinned sources, 12 new compiled modules, 500 total; verified reconstruction and six native proof/checker replays. Full elaborator remains open; no physical/hardware or external audit prerequisite.


**v32 corrective — leader-independent precommit recovery:** [native fault/restart and authenticated RPC evidence](BFT_PRECOMMIT_RECOVERY.md). Reproduced unpublished-quorum deadlock fixed, including terminal round, durable receipt after certified round change, signature/scope rejection and actual local RPC. 38 targeted tests passed. This is a distinct recovery property, not unconditional liveness; GATE-09 remains open for residual mandatory obligations.


**v34 corrective — failure-atomic adapter retention:** [implementation, TDD evidence and accepted formal scope](PLASTICITY_ATOMIC_RECOVERY.md). Active adapter now survives failure during reference inference; four focused training, microbatch and distributed numerical tests PASS. Previously verified native CaDiCaL + Isabelle-exported LRAT properties and Lean u16 proofs are explicitly PASS; do not reopen them or repeat the bootstrap. Full theory/elaborator compatibility is distinct and not asserted. GATE-09 is not unconditionally accepted.


**Current maintainer release decision: GATE-09 — PASS (bounded release acceptance).** See [GATE-09 maintainer decision](GATE09_MAINTAINER_ACCEPTANCE.md). This is an explicit authorization to proceed, not an unconditional engineering PASS or a new test result. Historical technical residuals remain recorded; passed properties are not reopened.


**Post-acceptance v35 security maintenance:** [cloud effective security-context hardening](CLOUD_SECURITY_CONTEXT.md) — 5 reproduced override defects corrected; 11 native targeted and 3 virtual-cluster tests PASS. Retains the [maintainer release decision](GATE09_MAINTAINER_ACCEPTANCE.md). No new roadmap stage.


**v28 — corpus-weighted graph architecture synthesis:** [implementation, native TDD and promotion evidence](ARCHITECTURE_EVOLUTION_V28.md). PASS for the extended bounded 8-leaf/3-unary/3-binary grammar, normalized BM25, degree-normalized multi-source diffusion, independent split promotion, restart and plan-boundary hardening. 29 targeted tests PASS. Arbitrary new primitive invention remains an open research objective.


**v33 — conditional rational-function identity discovery:** [exact proof, non-pole witnesses, verified publication and native regressions](RATIONAL_AXIOMS_V33.md). PASS for bounded rational identities on explicit common nonzero domains; seed 42 generated 64 conjectures, 48 proved and 16 refuted, independently replayed. 14 targeted tests PASS. Unrestricted axiomatic discovery remains a research objective.


**v34 — native Llama-subset local checkpoint adaptation:** [strict admission, CPU reference and real training evidence](NATIVE_LLAMA_PLASTICITY_V34.md). PASS for the bounded native CPU backend, exact Safetensors admission, logits/parity reference, 1,045,824 frozen weights plus 4,032 LoRA parameters, durable campaign recovery and rollback. 17 targeted tests PASS. External billion-parameter pretrained checkpoint and full upstream Transformers compatibility remain unverified.

**v27 — aggregated Ocean read accounting:** [corrective evidence](OCEAN_OCCURRENCES_V27.md). PASS for contract-simulated multiplicity and read-budget enforcement (11 focused tests); native SDK and fresh full regression remain open.


**v24 — feedback boundary correction:** [focused TDD evidence](ANNEALED_FEEDBACK_V24.md). Reject invalid action, reward and association weight; preserve action 6 sentinel. 34 focused tests passed against production module with extracted production AST validator; full cluster regression and actual LLM integration remain open. No change to GATE-09 release decision.


**RSI L5+ supplemental input:** [source register](RSI_L5_SOURCE_REGISTER.md). **v25 corrective:** [transfer boundary TDD](V25_MEMORY_BOUNDS.md). 78 focused tests passed, 8-record transfer and 64-record capacity unchanged; global Ray memory and full regression remain open. Existing GATE-09 scope unchanged.


**v27 — exact classical QUBO swap delta:** [evidence](V27_QUBO_DELTA.md). 36 new targeted tests and 11 existing Ocean contract tests PASS; exact seeded reference parity and reduced pair work. Native Ocean SDK and full regression remain open. Existing GATE-09 scope unchanged.
