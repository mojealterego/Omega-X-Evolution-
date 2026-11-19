# Acceptance gates and residual backlog — v20

A bounded implementation is not the same as complete production validation. No task below is silently converted to a pass. This register supersedes outstanding-status summaries in earlier development snapshots while retaining their historical evidence.

| Previously open item | State at v20 | Evidence / next acceptance condition |
|---|---|---|
| v19 multi-domain discovery | Implemented; local | Four dimension-aware synthetic domains, custom data, isolated train/validation/test, reproducible report |
| v20 research runtime | Implemented; local | Seven-domain E2E, authenticated checkpoints, idempotent graph publication and replay, bounded device/work policy |
| v9 outer population checkpoint | Implemented and tested | Durable alternate runner matches the original full report on regression fixture, old source bytes unchanged |
| v7/v13 larger formal proof scope | Extended; bounded | QF_BV proof for an individual u16 program pair over 2^32 inputs; arbitrary programs and compiler equivalence still open |
| Accelerator training | Implemented; CPU proven | Actual isolated Torch CPU training, verified against NumPy. CUDA/MPS/Ascend targets require physical hardware for acceptance |
| Qualcomm Hexagon HTP | Adapter implemented; simulation only | Static ONNX exporter and strict QNN provider configuration. Install compatible ONNX/ORT QNN/QAIRT, run real device and numerical tests; not an APK |
| Semantic GraphRAG | Extended; local | Actual corpus LSA retrieval, provenance; optional loopback HTTP quote-selector protocol tested on fake server, not actual LLM. Pretrained semantic embeddings and generated answer quality open |
| Packaging | Wheel built and smoke-tested | Actual wheel and isolated-target installation. Full dependency installation and MkDocs site still open |
| Physical GPU/NPU and multi-host cluster | Open — infrastructure | No real accelerator or independent cluster available; existing CPU, loopback TLS and simulated routing results are not proof |
| Upstream full pytest | Open — dependencies | 72 collection errors remain; attempted pip install failed in available index. Do not skip or stub these failures to make a green run |
| External AlphaEvolve/DGM comparison | Open | No equivalent external implementation, shared experimental budget or reproducible external workloads run |
| Universal arbitrary program synthesis, unbounded theorem proving, large-model training, general scientific discovery | Research open | Defined limited IR/MLP/dataset bounds; no claims beyond verified scope |

All twenty stages contain local executable implementations in the agreed bounded scope. Remaining gates above must not be marked production-proven without appropriate evidence. No credentials, private key, test database, active GitHub workflow or paid provider execution is included. The maintainer has defined v21 (Stage 3 performance regression gate); see [v21 evidence and scope](EVOLUTION_V21.md). v22 adds durable asynchronous island actors, actual local process transport and a 256-island logical simulation; Ray package availability and external multi-host deployment remain open. v23 implements bounded adaptive phenotype geometry; further source requirements are registered in [the extended maintainer roadmap](MAINTAINER_ROADMAP.md). See [v22](EVOLUTION_V22.md).

V24–v26 implement classical tensor-train mutation routing, bounded associative trajectory transfer and candidate-specific binary64 safety obligations. See [v24–v26](EVOLUTION_V24_V26.md). No generalized speed/quality advantage, physical Ray, live LLM policy or arbitrary theorem proving is claimed. Pending v27–v36 remain in the maintainer roadmap.
