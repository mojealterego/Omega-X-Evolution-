# L12 — managed quorum integration

Base main 094f4b47d0b9d7dc4645678773c224b57f6a05f0. ManagedQuorumEpochJournal composes the existing ManagedJournal, OQS v1, the original quorum event reducer, existing state digest, native Ed25519 and Merkle verification. No change to existing verifier, evaluator, key provisioning or legacy journal. The adapter reconstructs validated QuorumEpochPin and checks that its last challenge matches the full ordered history. Capacity is fail-closed, never pruning old nonces. Append/rotate/review/compact use the generation fence and SQLite durable intent. Remote witness revocation is not established by local fencing. Fresh epoch-zero genesis only; migrating a legacy journal requires separate full-history replay and quiescence. An exact independently retained fence remains necessary to detect joint rollback; read without it explicitly trusts protected anchor recovery.

## Native integration evidence

CPython 3.13.5, cryptography 46.0.4, pytest 9.0.2, Linux 6.18.57 x86_64. Deterministic fixture private keys are test-only. Native SQLite stores and actual Ed25519 signatures, no replacement verifier. The local source files were reconstructed from GitHub API and verified against the following base blobs:
- epoch journal core 3410f146d47cb3a8c0ed008e75fa58819a8966a0
- managed journal 69ad7abaf41c653ae2e31111c86945f0fe8147ae
- codec 98d64c213bbceecf94f5812555abdfbc7fb6feda
- checkpoint b36f544fe0f4935e31ddd5980b0e3d0fa227c788
- JCS 1b61af871b78740203cb2418b0a7ca8d1bd06884
- Merkle 4aa346d41fd27e654b1df1e5fd01df88d269407f
- quorum c27c798ac179ef7ec5eb3de4b9b9d83936ad241c
- quorum journal f3157dc05baa3e0c21e84ed130af43fb7bfe06b2
- rotation eba8205a2c6592687c69bd86feab86d1ab0c77a9
- receipts 1854ada8924eb09f8bcf2efedce8ee852677df90
- witness c75f1fc7e349d6491ab0c03f2959fcc6219499e7
- review anchor 1132fa0cce79402369aa8876190ee53ff49dffd4

RED: python -m pytest -q tests/test_ontos_managed_quorum.py; exit 2 (module missing); SHA-256 5bef537f5c291bc3e9f8e4f0fd9964887b866703211ca1441918c6170d6862e4.
GREEN first invocation: python -m pytest -vv tests/test_ontos_managed_quorum.py; 5 explicit PASS node results, sixth interrupted by execution timeout (200 seconds); not a completed suite; log SHA-256 dc3d4c74133392d94ba26cf0c31c8c19bb87a2eba451efb751dc1d395ad4fe39. The five passed nodes: test_actual_quorum_rotation_rollover_reopen_and_replay; test_review_after_rollover_retired_key_exclusion[3-REJECTED]; test_review_after_rollover_retired_key_exclusion[8-COMMITTED]; test_actual_state_codec_digest_and_history_capacity; test_prepared_actual_quorum_write_recovers.
GREEN separate remaining node: python -m pytest -vv tests/test_ontos_managed_quorum.py::test_tampered_compacted_bootstrap_rejected; 1 passed in 10.08s, exit 0, log SHA-256 559208d2a075fce213199b1bab3c3afd7cd395c94ba708827e502cf203ce7b2f.
Codec regression: python -m pytest -q tests/test_ontos_quorum_state_codec.py; 26 passed in 0.21s. python -m compileall -q omega_x_evolution tests exit 0 for isolated source set.
Tested new implementation blob 05a9f7966c91da82187210e7727f2baa6156507f, tests 8ca5258ff335ea60edc4a3fb5b167dedc143ce10.
All six new test cases have explicit PASS results across separate runs. Not a complete repository test run. Significant runtime overhead during repeated cryptographic replay; no throughput or latency acceptance claimed.

## Remaining gates

Managed quorum storage/replay integration is IMPLEMENTED / TESTED (NATIVE). Tests include actual joint epoch rotation, stale-fence rejection, old epoch and historical nonce replay rejection after rollover, retired evaluator rejection, valid review leaf persistence, capacity, prepared write recovery and altered anchor bootstrap rejection. The v75 audit_l12 reducer still needs a managed-fence trust input and atomic release admission integration. Full repository regression, migration, remote revocation, independent production custody and overall L12 acceptance remain OPEN/BLOCKED. No deployment claim.
