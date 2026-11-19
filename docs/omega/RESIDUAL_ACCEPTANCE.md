# Residual acceptance — v35.3 corrective release

Base main `23248aeeddc4721d4e62533546c0274ebe269a5a`; no new roadmap stage; v36 remains open.

| Gate | Evidence | Residual state |
|---|---|---|
| Lean/Isabelle | Generated closed extensional word equality; optional actual kernel invocation, reject missing tool or failing proof; native Z3 and constructive checker retained | BLOCKED: no installed external assistants; Isabelle generated theory not compiler-verified |
| Large LLM | Safetensors header/shard map validation, SHA-256, fail-closed memory admission, actual microbatch gradient equivalence and existing tiny decoder training | BLOCKED: pretrained weights, Transformers, sufficient memory and CUDA unavailable; no large-model training claim |
| BFT liveness | Autonomous certified timeout rounds, persisted certificates, catch-up by replay, signed RPC. 24 single-validator outage/order cases and minority partition scenario | PASS for tested finite schedules; general partial-synchrony liveness proof and multi-host faults OPEN |
| Architecture synthesis | Corpus-derived latent SVD bases, typed recursive search, persistent frontier and work budget, validation promotion and held-out evaluation; identical interrupted/uninterrupted report | PASS for bounded grammar; arbitrary primitive invention and unbounded synthesis OPEN |
| Physical infrastructure | Existing Kubernetes HTTPS contract and JAX CPU numerical reference; no added hardware execution | BLOCKED: no authorized physical GPU/TPU/QPU/cluster |
| Full upstream collection | Lazy public exports and pure text parsing; 911 tests collected, 36 errors (previously 401/72); selected offline suite 103 passed | BLOCKED: six missing external SDK dependencies; full suite not passed |

## Consensus assumptions and limits

Each active validator may run the pacemaker independently. Timeout certificates require n-f distinct valid signatures for the same round and membership. They authorize round advancement, not acceptance of a block. The driver rotates leaders, doubles round deadlines up to a ceiling, retries the same persisted proposal, and replays verified commits for lagging peers. Existing explicit local `Replica.advance()` remains available for backwards-compatible manual tests; it is not an RPC operation. Durable state and signing keys are trusted. The 24 schedules use the production Replica and Pacemaker with deterministic delivery and one unavailable peer, not an exhaustive Byzantine model checker. The real RPC test uses HTTPS/HTTP authentication according to the existing transport policy and loopback peers. Progress assumes a reachable honest quorum, sufficiently long common round, bounded message/processing delays after stabilization, and remaining round/height budget; no unconditional liveness claim. Source-bound BFT genesis changes require a matching version, not silent checkpoint migration.

## Architecture and LLM limits

The search expands score trees over seven leaves (including four corpus-derived latent projections), bounded depth/size, up to 8192 evaluations, bounded frontier and work. The final test seals the search; repeated finalize returns persisted results. It is not an unrestricted architecture generator. Memory admission is a conservative estimate, not an allocator or proof of fit. The local model loader accepts safetensors only, trusted local directory, no remote model code; actual inference/training with large pretrained weights remains to be verified. Microbatch gradients match the full-batch reference within numeric tolerance. No paid provider calls or execution of arbitrary generated host code.

## Upstream and dependencies

Public lazy exports preserve imported foundation API names; offline pure text extraction is moved without changing semantics. No missing SDK is replaced by a stub. Missing: anthropic, openai, backoff, hydra-core, instructor, google-genai. `pip download --retries 0 --timeout 5 --no-deps ...` failed: no matching distribution for anthropic in available index. Full collection exit 2. Physical acceptance requires a real authorized environment; deterministic simulations establish only their declared invariants. See [verification-residual.txt](verification-residual.txt) for exact commands and evidence.
