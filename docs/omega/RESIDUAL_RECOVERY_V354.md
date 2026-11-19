# Residual recovery — v35.4

Base main: `960b9f50404b2fa4e8047db2bc0a47fe0ab7c563`. No new stage. Source-bound checkpoints must not be silently migrated. Acceptance is restricted to the verified domain.

| Requirement | Result | Evidence / limitation |
|---|---|---|
| Lean/Isabelle | BLOCKED | Native Z3 UNSAT on closed u16 modular identity; generated Lean/Isabelle sources; both external kernel invocations unavailable, no kernel proof accepted. |
| Real large LLM | BLOCKED | Existing small decoder CPU tests and microbatch gradient equivalence rerun; no large pretrained weights, Transformers/CUDA or sufficient memory. No large-model training claimed. |
| BFT | PASS (finite modeled scope); OPEN (general theorem) | Pacemaker keeps polling for verified catch-up after round exhaustion; production replicas and driver exercised under withholding, forged voter, duplicate timeout signatures, transient partition, all four faulty-validator positions. No progress claimed during loss of quorum. |
| Synthesis | PASS (bounded scope); OPEN (unrestricted) | Combine two independently developed non-leaf trees by add/mul/max, persist previous nonleaf and bound frontier, work and complexity. Actual evaluation confirmed, restart 127+129 equals uninterrupted 256. No general novelty or infinite search claim. |
| Physical infrastructure | PASS (previous modeled contracts rerun); BLOCKED (physical) | Existing simulated Kubernetes and local CPU, process and transport tests; no new physical accelerator/cluster runs. |
| Upstream | FAIL (full collection) | Baseline 911 collected/36 errors; final 1336/12. No test files removed or suppressed for collection, no dummy SDK replacements. |

## Changes

- `pacemaker.py`: even after the final local round, poll for signed commits until the caller's tick/stop limit. The height limit remains terminal. This is not unbounded consensus liveness.
- `architecture_search.py`: bounded compositional recombination uses previous nonleaf, persists it, queues admissible composite plans, and retains validation and held-out separation.
- `shinka`: lazy selected-provider imports, lazy SDK construction and diff parsing, still fail explicitly on actual missing dependency. Headless routing and offline extraction do not require the cloud SDKs. Public compatibility accessors remain available.

## Evidence

See `verification-residual-v354.txt`. Full OMEGA suite: 320 passed. Native hardening: 38 passed. Ten new regression/simulation tests are included in the 320. Collection: 1336 collected, 12 errors. Earlier targeted upstream: 188 passed/3 failed (missing unidiff and google.genai); after headless change, targeted suite 17 passed/1 failed (headless E2E cannot parse diff without unidiff). No full upstream pass.

Simulation assumptions: n=4, f=1, authenticated identities, trusted durable state, virtual monotonic clock, deterministic ordering and fault schedule, eventually restored honest quorum. During partition no commit; after restoration equal committed block among honest replicas. No guarantee under permanent partition, arbitrary scheduler, exceeded fault bound, or exhausted global budget. Scope is not a general partial-synchrony theorem. No live provider or paid infrastructure operation authorized or undertaken.

The remaining collection errors involve anthropic, openai, backoff, hydra-core, instructor, google-genai. Missing unidiff also affects runtime tests. Real pip download could not obtain packages from the available index. No physical validation substituted for actual measured hardware; deterministic tests accepted only for modeled properties. v36 remains open.
