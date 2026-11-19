# OMEGA-X Evolution — v16–v18

Development snapshot 0.18.0.dev1. Existing evolution, checkpoint, discovery and training implementation files are unchanged. These are bounded research modules, not a production scheduler or a general autonomous laboratory.

## v16 — heterogeneous inference orchestration

`compute.Router` routes inference of the existing validated v15 MLP Model to CPU (NumPy) or optional operator-installed PyTorch backends: CUDA, Apple MPS, Ascend NPU (`torch_npu`). `probe(enable_torch=True, enable_npu=True)` explicitly opts into those runtimes; a missing runtime or unavailable device is absent from the inventory. The default never imports Torch. A device entry carries a memory admission cap and a physical/simulation flag; trusted test doubles are not reported as physical. Caps are at most 64 MiB on probed backends and accelerator caps are additionally limited by the device's reported free/estimated memory at discovery. CPU capacity is a policy cap, not physical system RAM. This is a small MLP inference scheduler; no training offload, tensor partitioning, Qualcomm Hexagon/QNN, ROCm-specific tests, remote accelerator workers or hard OS memory enforcement.

The router uses a lock, one active lease per device and a total admission budget based on a conservative tensor workspace proxy (four times binary64 parameter and activation bytes). Leases release on success and failure. No queue wait: contention triggers explicit fallback or rejection. Device preferences are an allowlist in order, so `prefer=('gpu',)` is strict. Every successful output is checked against the existing NumPy CPU reference (`rtol=1e-5`, `atol=1e-7`, exact shape and finite outputs), including accelerator output. This intentionally incurs CPU recomputation and is not a speedup claim. Failing devices are recorded, never silently accepted. CUDA uses float64, MPS and NPU use float32; differences within tolerance are permitted and may affect close experiment rankings. The memory estimate is not a driver allocator reservation; stale free memory, allocator overhead, failed kernels and other processes can still cause OOM or delay. There is no hard timeout on native kernel calls. Use trusted runtimes and devices only. Initialize Torch in a separate process from fork-based workers, or before using an independently managed spawn-based worker pool; don't fork after initializing accelerator/OpenMP state. Local regression reproduced a hang with in-process Torch initialization followed by old fork tests; isolating the Torch contract test fixed the suite.

```sh
python -m omega_x_evolution.compute --demo
python -m omega_x_evolution.compute --torch --npu --demo
```

[Local evidence](compute-benchmark-v16.json): 48 real CPU inference samples; matching reference. A separate real PyTorch CPU tensor test passed. No GPU/NPU device was available. Simulated accelerator tests exercise routing, mismatched outputs, failure, fallback and strict preference without claiming hardware execution. Concurrency test verifies lease contention and release.

## v17 — durable graph retrieval memory

`graph_memory.GraphMemory(path,key,tenant)` stores typed experiment/result/artifact/hypothesis/evidence nodes and produced/derived/supports/refutes/uses edges in SQLite with foreign keys, FULL synchronous commits, transaction isolation and five-second database lock timeout. Content-addressed IDs bind namespace plus canonical JSON. HMAC-SHA256 authenticates namespace binding, nodes and directed relations, with a key of 32–4096 bytes. Different namespaces may use different keys. Wrong-key, forged retained record and cross-namespace edge operations are rejected. Atomic `record_experiment` writes plan, result and relation in one transaction. Duplicate content is idempotent. Each namespace is capped at 4096 nodes, 16384 edges, 16 MiB of body text, 128 KiB per body and 4096 characters per node text. Retrieval uses deterministic lexical term coverage and bounded bidirectional graph expansion (max three hops, max 32 citations), returning full record payload, exact node IDs, paths and relation directions. This is a GraphRAG retrieval substrate; no embedding model, knowledge extraction from arbitrary prose, LLM synthesis, remote tenant identity/authentication, encryption at rest or distributed consensus. HMAC authenticates retained content, not completeness or freshness; whole-database rollback/deletion is not detected. Store key and database separately under OS permissions; tenant name is operator-controlled, not a credential. Retrieved text/payload is data, never executed as instructions.

```sh
# Create a private key in a protected directory first:
python -c 'import os; fd=os.open("memory.key",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(fd,os.urandom(32)); os.close(fd)'
python -m omega_x_evolution.experiments --task smooth --db memory.db --key-file memory.key --tenant research
python -m omega_x_evolution.graph_memory --db memory.db --key-file memory.key --tenant research --query plan
```

The integration report shows persisted plan and result recovered by a new GraphMemory object, with path and produced relation. Tests cover tampering, key binding, atomic rollback, idempotency, isolation and storage bounds.

## v18 — automated experiment construction

`experiments.design` builds a typed reproducible Plan from a three-way Split and operator resource constraints: symbolic search, pure neural MLP and hybrid certified symbolic/residual MLP. It admits additional candidate families only if combined epoch × training rows × parameter count fits the work cap. Plan integrity binds train and validation sets, never final test labels; execution reconstructs and compares the plan to enforce limits. The symbolic attempt budget is shared, not repeated for each family. Existing v12 search sees training labels for ranking and validates the selected symbolic expression once; v7 certified optimization remains mandatory. Neural weights are trained using train only, with real v15 CPU backpropagation. Validation selects candidate with lowest finite RMSE, with parameter count and stable priority tie breaks. Exactly one selected candidate is evaluated on test; result reports candidate validation evaluations, not primitive arithmetic operations or number of reference passes. Test access is after selection. `Router` verifies the neural predictions and records the executed backend. Optional memory persists the plan and result atomically, including dataset digest, selected model's JSON weights and provenance. No external data acquisition, executable plan, arbitrary code, automatic deployment, statistical significance, or LLM-generated plans. v17 retrieval is a separate inspectable evidence interface; it does not influence candidate selection. The plan's work bound is a proxy, not wall-clock/compute equivalence. Runtime/BLAS differences may affect reproduction. All current tasks inherit the two-variable bounded domain and existing Z3/NumPy requirements.

```sh
python -m omega_x_evolution.experiments --task smooth --epochs 400 --budget 128 --plan-only
python -m omega_x_evolution.experiments --task smooth --epochs 400 --budget 128
python -m omega_x_evolution.experiments --dataset observations.json --epochs 100 --work-cap 1000000
```

Custom JSON uses the v14 `train`, `validation`, `test` observation split. [End-to-end evidence](experiment-benchmark-v18.json): 96/48/48 synthetic observations, 128 symbolic attempts, two actual neural trainings (400 epochs), 14,208,000 training work units, symbolic validation RMSE 0.112663, neural 0.092455, hybrid 0.066435, selected hybrid test RMSE 0.048467. This is the existing smooth fixture from v14, reused to verify integration, not a novel or previously unseen scientific benchmark. Graph result retrieval returns a path from plan to result after reopening. Tests change test labels without changing plan or selected policy and reject manipulated or over-budget plans.

## Gate and remaining work

See [verification-v18.txt](verification-v18.txt). v16–v18 have bounded local implementations. Physical accelerator tests, training offload, hard device isolation, full semantic/LLM GraphRAG and general experiment planning remain open. v19–v20 continue the accepted roadmap. No active GitHub Actions or paid inference.
