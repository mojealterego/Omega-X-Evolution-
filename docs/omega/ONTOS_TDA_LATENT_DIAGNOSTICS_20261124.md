# ONTOS — bounded latent topology diagnostics (2026-11-24)

**Source baseline:** `mojealterego/Omega-X-Evolution-`, `main` at `c40bb6824c24840e906e5c6de05551881111d4c0`.

## Requirement decision

The user proposed persistent homology in the hidden JEPA world model, in place of SIGReg, as a way to prevent representation collapse on sequence horizons of tens of millions of tokens. The inspected repo includes `omega_x_evolution/topology.py` for **AST phenotype geometry**, but that module computes finite conformal graph distances, not topological persistence of learned JEPA activations. Existing async orchestration and ONTOS Prometheus/JSONL observability must not be duplicated.

Deliver an **optional data-only diagnostics adapter** accepting already-computed latent vectors. It does not create, run, or train a JEPA model or modify SIGReg. It must not autonomously reject/promote a model, grant authority, or claim that collapse is prevented.

## Implemented contract

- `omega_x_evolution/ontos_tda.py`: `vietoris_rips_h01`, `diagnose_latents`, `LatentReservoir`, bounded CLI.
- Vietoris–Rips 2-skeleton: every vertex at filtration time 0, every edge at Euclidean distance, each triangle at its maximal edge distance. Sorted by `(filtration, dimension, simplex)` to preserve face order. Persistence via sparse binary boundary-column reduction over **GF(2)**. H₀ births, deaths and H₁ births/deaths are computed. Triangle boundaries suffice for H₁, not for higher dimensions.
- Input: **2–24** latent samples, each in **2–16** numerical dimensions, finite float64 and magnitude <= 1e6. Resource cap: max 2,324 simplices. All clique triangles generated, no heuristic pruning.
- `diagnose_latents` computes affine rank from centered SVD at relative threshold 1e-8 and effective rank as exponential spectral entropy. Detection outcomes: `POTENTIAL_COLLAPSE_CONSTANT`, `POTENTIAL_LOW_RANK`, `NO_COLLAPSE_SIGNAL_IN_SAMPLE`. These are **heuristic indicators**: low rank may reflect a valid task representation.
- `LatentReservoir` supports deterministic uniform reservoir sampling (up to 24 retained vectors, seeded random generator, at most 100,000,000 observations, <=4,096 vectors per ingest). Any reported H₀/H₁ invariants apply to the sampled points **only**, never to every point in the original stream. Chunk partitioning preserves seeded sampling.
- Fixed output fields `release_authorized=false`, `jepa_model_verified=false`, `long_context_guaranteed=false`; no raw embeddings in diagnostic JSON. Raw samples are locally accessible only through the explicit `sample()` method. The class is neither thread-safe nor a durable distributed stream reconciler.
- CLI reads either small direct JSON point clouds (<=128 KiB) or line-delimited row arrays as a stream (<=4 KiB/row). No network, executors or model calls.

## Commands

```bash
python -m pytest -q tests/test_ontos_tda.py
python -m coverage run --branch --source=omega_x_evolution.ontos_tda -m pytest -q tests/test_ontos_tda.py
python -m coverage report -m
python -m compileall -q omega_x_evolution/ontos_tda.py tests/test_ontos_tda.py
python -m omega_x_evolution.ontos_tda --input latents.json
python -m omega_x_evolution.ontos_tda --input latent_vectors.jsonl --format jsonl --dimensions 16 --capacity 24 --seed 42
```

## Verification and boundaries

- TDD RED: test module missing, import fails. Second RED: first CLI and object-protocol hardening tests fail. GREEN: 50 tests PASS using actual submitted module and tests in an isolated Python project structure; 96% combined statement-and-branch coverage of the new module. Independent graph-homology computation for 15 random seeds at 4 thresholds plus independent Kruskal MST checks. No external GPU/JEPA deployment, learned latent generation or full GitHub-repo regression executed.
- Implementation is a **finite exact GF(2) matrix reduction conditional on approximate float64 distances**, not a numerically exact representation of Euclidean distances or infinite-dimensional homology.
- The main `topology.py` describes AST evolution, not a JEPA model. Never claim JEPA integration without an actual JEPA runtime, real embeddings, checkpoint/replay and task-level benchmarks.
- Domain must remain opt-in advisory. It is not an independent proof of correctness, CEV safety, release eligibility or distribution-free invariance at million-token contexts.
- Production promotion and historical GATE-09 are unchanged.

## Source

GUDHI documentation, Vietoris–Rips filtered simplicial complexes, max-edge triangle filtration and persistence: https://gudhi.inria.fr/python/latest/rips_complex_user.html . The implemented Python GF(2) reducer is independently authored; it does not claim to use or benchmark GUDHI.

## Other user proposals (not implemented in this patch)

- Async/Titans/MCP: `omega_x_evolution/async_lifecycle.py` already exists; native external adapters are not verified by this patch.
- Constitutive drift / DAG stress: prior tests exist; no new full repo integration claim.
- Thermodynamic and free energy exports: prior `ontos_observability.py` retains its fixed schema; no changed telemetry schema.
- Grover-like search: oracle query-complexity results are not generic runtime/energy accelerations for a classical DAG; no quantum hardware used.
- Lean 4 / Coq: no general proof synthesis; limited existing proof kernels remain.
- FHE: confidentiality of supported encrypted computations does not neutralize prompt injection, tool exfiltration or authenticate agent intentions.
- Tokenomics: no distributed financial budget negotiation or autonomous payments implemented.
