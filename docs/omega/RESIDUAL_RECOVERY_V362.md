# Residual recovery v36.2

> **Current acceptance policy:** [Mandatory execution directive v3.0](EXECUTION_DIRECTIVE_V3.md) supersedes conflicting historical criteria. External audits, third-party certification and physical infrastructure reruns are not required. Accepted deterministic engineering simulations close modeled properties. Native/production claims and functional or mathematical obligations remain distinct.


Base main: `b6200c56ec0edb951a4b6dee3ed9876d3da02e56`. This release preserves the v2.3 §5 simulation acceptance policy. No new stage, paid infrastructure, or CI activation.

## BFT progress beyond the historical terminal round

The default genesis permits round numbers from 0 through 2^31-1. Existing explicitly bounded configurations can retain their old 32-round horizon. The protocol retains the current round's votes, durable lock and highest certified round transition; obsolete per-round votes need not be reissued because the durable round never decreases. Exponential timeout multiplication saturates before constructing an enormous integer. Genesis is bound to source and configuration; no automatic migration of old checkpoints is performed. The no-disk-rollback assumption remains. MAX_HEIGHT=128 remains unchanged.

`test_default_protocol_replaces_faulty_legacy_terminal_leader` drives real signed Replica/Pacemaker instances through 31 quorum-signed timeout certificates, isolates the final legacy leader, advances virtual time, and checks all honest replicas commit the same block at round 32. `test_extended_round_history_is_bounded_and_restart_non_equivocation` checks a longer schedule, persistent history bounds, stale certificate rejection and laggard catch-up. This closes the reproduced round-31 deadlock, not a theorem of unconditional liveness under all possible faults or permanent partitions. A terminal fault at the new finite wire bound is not proved recoverable.

## Streaming architecture synthesis

`omega_x_evolution.streaming_synthesis.StreamingSearch` enumerates the supported grammar by increasing size with exact integer counting and unranking. Its persisted cursor is `(size, ordinal)` and it retains one best candidate rather than a growing frontier and visited set. The former 8192-candidate lifetime quota does not apply. Each atomic step admits <=256 evaluations and <=200 million work units, reserves a conservative per-query cost, charges actual work and rejects an over-cap retrieval rather than qualifying it. Existing per-plan size/depth bounds (255/16), supported primitives, query split isolation, and the final holdout seal remain. A finite grammar is not arbitrary primitive invention.

Tests execute 8200 actual candidate evaluations across checkpoint reopen; verify 175 distinct size-three trees, equivalence of different step schedules, quota rejection and finalization isolation. The test corpus and seed-independent enumeration are defined in `tests/test_omega_streaming_synthesis.py`. This is a distinct API; older Search checkpoints are not silently converted.

## Dependency recovery and identity regression

Official CI artifacts for Jiter, Instructor and HTTPX2/httpcore2 were downloaded read-only and checked against their published artifact SHA-256. Jiter 0.18.0 is selected to satisfy Instructor 1.18.0's bound. Radon 6.0.1 was reconstructed from 18 byte-verified blobs of its official tag and built with its own setup.py. Truststore 0.10.1 runtime source was restored from pip's vendor copy, reversing only the vendor import rewrite and checking every byte against the official tag (including LICENSE); its local wheel uses explicit setuptools metadata. No fake SDK or replacement implementation is installed. Exact hashes and test commands are in the verification record. The environment is an experimental offline overlay, not a fully resolved installation: `pip check` still reports missing or incompatible transitive dependencies; Google GenAI's overlay version is outside the project's existing constraint. No constraints have been weakened.

The five inherited identity/CI assertions were migrated to the actual derivative distribution, existing legacy entry points, local source installation instructions, and archived workflow paths. An explicit negative assertion rejects active YAML workflows, preserving the no-paid-CI policy. No test was removed. Existing test markers still exclude two secret-backed/live tests from the offline run. Any platform-tool skips are reported by pytest. The test suite is not an assertion of external service availability.

## Acceptance boundaries

- Reproduced legacy BFT terminal deadlock: PASS (deterministic signed execution). General liveness remains unproved; finite wire and height limits are explicit.
- Streaming synthesis beyond 8192 evaluations: PASS (actual search and replay). Arbitrary novel primitives and unrestricted theorem proving are not established.
- Infrastructure simulation properties accepted in v36.1 remain PASS; no independent physical rerun is required by the project directive.
- Native Lean/Isabelle language and loader compatibility claims and actual large pretrained model format/tokenizer/update/generalization claims remain unverified. They are not prerequisites to the already-accepted modeled properties.
- GATE-09 includes functional and dependency obligations beyond those already accepted. No unconditional PASS is inferred from a green offline suite or a simulation of only a different property.

## Executed results

1556 collected without collection errors; final offline regression exit 0: 1547 passed, 7 existing rustfmt skips, 2 live/secret-backed tests deselected. Core 344 passed and native hardening 38 passed. Five targeted identity/CI tests updated, with no active workflow. Build and compileall passed. [Raw verification record](verification-v362.txt). GATE-09 is not a full PASS.
