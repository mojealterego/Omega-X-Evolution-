# v28 — corpus-weighted autonomous graph architecture synthesis

Base main: `4232c477b92544599849673e0907f63087f10f7a`. Extends the existing bounded retrieval-architecture obligation; no new roadmap stage.

## Implementation

- A normalized BM25 leaf uses authentic corpus term/document frequencies and document lengths; no target labels enter index construction. Fixed k1=1.2, b=0.75.
- A synchronous `diffuse` operator aggregates distinct adjacent-node contributions with degree-normalized weight and bounded saturation `1-product(1-share)`, retaining original score when higher. Parallel relationship types do not multiply one neighbor's contribution. Its score is a relevance heuristic, not a probability or assertion of independently corroborated facts. Repeated compositions remain bounded but can recycle correlated evidence.
- The typed grammar now has 8 leaves, 3 unary and 3 binary operations. All three search implementations share these definitions, including cursor unranking. No generated host code, shell, network or imports are accepted as a plan. JSON decoding limits depth and node count before full materialization. Retrieval revalidates the exact immutable plan type and tree, rejecting forged plans and subclasses. New operation work is charged before scoring or graph-edge aggregation.
- Search still separates train, validation, and sealed final test. Existing plan encodings remain valid. The grammar changes ordinal meaning and source-bound campaign hashes; old checkpoints are deliberately not silently migrated. Retain old revision for replay, or start a fresh campaign.

## Executed evidence — NATIVE

Environment: Linux x86_64 6.18.57, Python 3.13.5, NumPy 2.3.5, pytest 9.0.2, `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1`. Deterministic authenticated synthetic fixtures; no pretrained model or external infrastructure.

- V28-RED: `python -m pytest -q tests/test_omega_architecture_evolution.py` against base: 4 failed, 1 passed. [log](v28-evolution-red.log), SHA-256 `91ac0d45b67e3bf05c3392b0f3343f807f71837e33e77b04b3ca7a0f404a3e5d`.
- V28-GREEN: `python -m pytest -q tests/test_omega_architecture_evolution.py tests/test_omega_streaming_synthesis.py tests/test_omega_v29.py tests/test_omega_remaining_closure.py::test_synthesized_memory_new_structure_and_holdout tests/test_omega_final_gates.py::test_resumable_architecture_search_final_test_only_once tests/test_omega_terminal_recovery.py::test_synthesis_budget_can_be_extended_without_restarting tests/test_omega_residual_recovery.py::test_search_combines_two_novel_subtrees` — 29 passed, exit 0, 4.01 s. [log](v28-evolution-green.log), SHA-256 `4202efc7596dd0180a7512dd45735c6ff8212bb345b3f8492f15fcbbbe9939f7`.
- V28-BUILD: `python -m compileall -q omega_x_evolution/architecture_synthesis.py omega_x_evolution/architecture_search.py omega_x_evolution/streaming_synthesis.py tests/test_omega_architecture_evolution.py tests/test_omega_streaming_synthesis.py` — exit 0.
- Independent BM25 formula and graph scores: target .625 versus distractor .25; parallel edge added without changing scores. Streaming search automatically selected `['diffuse',['lex']]` on separate queries; validation/test MRR 1/3 versus lexical baseline 0 on the constructed four-node graph. This is a bounded demonstration, not a general retrieval benchmark. Restarted and uninterrupted searches agree; final test is sealed, forged plans and oversized input rejected, budget enforced. Existing streaming regression crosses 8192 evaluations and verifies grammar counts.

| Changed source | SHA-256 | Git blob |
|---|---|---|
| `omega_x_evolution/architecture_synthesis.py` | `556d3c82519f1a2faaf74caf1d2dc0aeedc2ceb9c68479074462e684f981a4a8` | `6f6b90297eb16794c6abbc74aab4930ff39c5352` |
| `omega_x_evolution/architecture_search.py` | `f3443a6378ca9e4a52f13abde9b7048f98f6d4a985e24635d4c08a394104c320` | `4856f4b04a957bbe00811a052620d4cba60e2420` |
| `omega_x_evolution/streaming_synthesis.py` | `c8df59901f241451c8ca1829e3dec5ecab5b0deb6c61273eceb060bdb7cf23c7` | `387821a343845d6740df875937687295fefe8be7` |
| `tests/test_omega_architecture_evolution.py` | `94dcb79e70cef7629d294c7acd15a9d4d92e1ce8c860d734234a2935517d6232` | `66d1c2948cf51583c8927c8e6f0a13c682db23fa` |
| `tests/test_omega_streaming_synthesis.py` | `baf6e9a1f1c135aef13855f3b0ea8473f6b9d695f3b057fb4cde423e9f4ae829` | `b145e51b688da968ce76d97e791f3dbcbd00b2bf` |

PASS: the implemented bounded corpus-weighted and multi-source architecture synthesis contract. No arbitrary primitive/code invention, general intelligence, full repository regression or production performance claim. GATE-09 owner acceptance remains unchanged.
