# OMEGA-X — integrated Ω-Max audit, stage 27 (2026-11-28)

Base main 27874199b51fbf257a669054f7058e897b5c5907, tree 7179a15a7155c081742f4bc7f419e1447465cf4c. Authoritative roadmap is ONTOS_OMEGA_INFINITY_ROADMAP.md per MAINTAINER_ROADMAP.md; docs/ROADMAP.md absent. Historical bounded maintainer GATE-09 authorization remains unchanged. This audit reviews the available native slice; upstream tree contains 245 Python test files and 166 Python modules in omega_x_evolution, not all locally available. Direct git clone/ls-remote failed DNS; no claim of full upstream execution. 94 baseline Python source/test/compatibility blobs verified against remote tree; 31 prior local test files plus one new. No external audit or physical rerun required for properties already accepted by engineering simulation.

Findings F27-01: legacy checkpoint MAC authenticates content, not freshness or a unique run. F27-02: direct memory engine invocation trusts the adapter's retained source fence; if both source DBs and adapter are restored together, a separate latest source fence is necessary. Correction: optional FencedCheckpointStore, with 32-byte independently provisioned run ID, per-run derived HMAC key, exact CheckpointPin (run ID, generation, MAC). Load requires exact externally retained pin, clears write authority on failure, and rejects older snapshots, same-generation divergent histories, and wrong run ID. Existing CAS retained; new pin advanced only after successful save/initialize. run_fenced_memory requires exact MemoryProposal, exact FencedCheckpointStore, and independently retained source Fence matching adapter before invoking the actual engine and existing source guard. No changes to legacy checkpoint API or wire formats; new run required to use the new MAC domain. This is opt-in, not mandatory protection on all existing engine entry points. Caller must retain newest pins/fences separately, trusted monotonic clock and source custody; same run ID must not be provisioned twice. No automated durable pin store or atomic pin persistence; crash between database commit and external pin persistence can deny resume. No auto-trust recovery; fail closed. Complete rollback including all external pins is outside guarantee. Experience revocation remains scoped to the experience journal; direct historical DGM state and prior exported views remain historical artifacts, not fresh experience recommendations. Existing production release authorization unchanged.

## Audit gate matrix

Scoped properties / entire project:
- GATE-01: PASS for identified stage27 corrective requirements; BLOCKED for complete requirement/source closure.
- GATE-02: PASS for reviewed opt-in boundary and separation; BLOCKED for complete upstream architecture.
- GATE-03: PASS for two new modules (implementation and tests); BLOCKED for remaining roadmap obligations.
- GATE-04: PASS native 494 distinct tests in available slice; BLOCKED full upstream.
- GATE-05: PASS for exercised actual memory/DGM/experience/checkpoint/revocation chain; BLOCKED full integrated production scope.
- GATE-06: PASS for tested run-scoped MAC, exact retained pins, source fence, rollback, CAS; BLOCKED for mandatory enforcement at all entry points, durable independent pin custody and full security review.
- GATE-07: PASS for tested stale writer, failed save, deterministic restart, source rollback rejection; BLOCKED automatic external pin recovery and untested system-wide reliability.
- GATE-08: PASS for tested source/test hashes, logs, reproduction and scope; BLOCKED missing original L12 source bytes.
- GATE-09: scoped corrective work TESTED; entire current L12 BLOCKED; historical bounded release acceptance unchanged. No operational release.

Remaining: original 33-file L12 archive not recovered per previous audits; full 91% guarded ONTOS objective remains FAIL per prior campaign, not retested here; complete upstream regression, mandatory independent pin integration with durable custody and recovery, closed-loop cross-plan learning, complete cryptographic erasure and operational deployment remain open. The historical bounded GATE-09 PASS is not retracted or extended.

## Native test evidence

Source blob 6238d403968acce5be6d6953137daa82b9a88bb1; tests 1bc2da00914bfd5377c2fa91e4ee9c9025fa0cdf. CPython 3.13.5 Linux x86_64, native SQLite and cryptography, OPENBLAS_NUM_THREADS=1. Test IDs pytest node IDs. Commands python -m pytest -q:
- tests/test_fenced_checkpoint.py: RED missing module exit 2 SHA256 5f9607bb389f61812d158f2dfe5ede9e7102e0b3aa400f8eb53bcaece2e7fa91; initial 12 passed .60s; integration RED 2 failed missing endpoint SHA256 ca5c728747abd5e891f45f317d2b743c531c26ad1a8794af18527e27afff5c8c; final 14 passed 2.68s SHA256 5a7ecffa1d3cfff2c0cbf98f7b5890748ce157f70f3b155be375388e559f83c5. Real engine deterministic resume; old snapshot, divergent same-generation fork, invalid run scope, failed-load save denial, stale CAS and pin stability; integrated actual DGM round, experience training, engine checkpoint, source revoke and both source DB rollback relative to latest independent source fence.
- tests/test_engine_experience.py: 12 passed 25.94s SHA256 07d91c7da7176062cd511b7857a00a02881b30b68a22a0dc82488882288f9aed.
- tests/test_engine_dgm.py tests/test_engine_memory.py: 31 passed 27.41s SHA256 ccd91a6615d8eb1dc4711641cf5496ddbf0a39684f69e505c3e85c6bf0ec5819.
- tests/test_omega_checkpoint.py tests/test_omega_coevolution.py tests/test_omega_workers.py: 42 passed 7.73s SHA256 341f6c096680ffacaa59440e84dab4bb7960c44d9f28befdb495b4ad97ec7dfc.
- tests/test_ontos_otce.py tests/test_ontos_otce_migration.py: 32 passed 19.80s SHA256 d764a1efd7d82adbcf9e358c51c54b83ad48986e0c82f03695db6cbf7720c9f4.
- tests/test_ontos_sealed_otce.py tests/test_ontos_reversible_ops.py tests/test_ontos_hyperrag.py tests/test_ontos_memory_evolution.py: 65 passed 6.26s SHA256 0c2ae22a93f80b1c9836b4af835d6dccb91151bc21c6e150df30f8f4d441c581.
- tests excluding all separately named groups: 275 passed 23.08s SHA256 806c443d6f2cb78f29345846be033e8a973c2004fe70881b4ad939d2a90dae31.
- tests/test_ontos_living_journal.py: 8 passed 19.51s SHA256 5cd6427e80d44980df09fc42ef7b89783b349b8db4de010ba797c67027060e46.
- tests/test_ontos_v75_managed_gate.py tests/test_ontos_v75_journal_gate.py: 9 passed 24.10s SHA256 9ab7bcb64c8864cbcb536f12a2cc3dd644e0993a3504da0fc304242c4748f603.
- tests/test_ontos_managed_quorum.py: 6 passed 23.44s SHA256 a78906eb5e733da392c6305a1e229c4cf9f9a0927c0d48858972db29e187aa66.
All ten final complementary runs exit 0, 494 distinct tests (480 prior +14), compileall exit 0. Streaming execution unsupported; normal synchronous commands completed. No full upstream or unconditional project completion claim.
