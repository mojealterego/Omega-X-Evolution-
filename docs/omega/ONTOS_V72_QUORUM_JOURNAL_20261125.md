# L12 v72/v75 — authenticated quorum epoch journal and transactional GATE-09

Base main `a49e1535f8a68ff051335137782408a19adb8a95`. Scope: native Linux SQLite/Ed25519 plus deterministic synthetic L12 source fixtures (HYBRID). No external infrastructure or independent audit required for these modeled properties. No actual source campaign, production authority, or deployment claimed.

## Architecture and acceptance boundaries

`ontos_epoch_journal_core.Journal` is a bounded authenticated append-only SQLite journal (256 events, 32768 bytes/event). It uses an operator-owned private directory, exclusive initialization, DELETE journal mode, FULL synchronization, `BEGIN IMMEDIATE` compare-and-swap and hash-linked cursors that commit both authenticated payload and successor state. Every read/update replays from the independently pinned bootstrap and must contain the retained external floor. Corrupt/oversized events, divergent or restored state and unsafe file types fail closed. Caller controls deterministic replay code and an immutable bootstrap. Concurrent untrusted access to the private directory, simultaneous rollback of all trust domains, and resource/performance guarantees beyond the bounded local model are excluded.

`ontos_v72_quorum_journal.QuorumEpochJournal` reuses the native v72 quorum and rotation verifiers. It serializes canonical bounded certificates, preserves retired identities and all used challenges, replays each transition and verifies old/new quorum handoff. Its review event binds the exact canonical eight-gate v75 leaf, evaluator roster extracted from the leaf, latest-leaf inclusion proof and current-epoch certificate. Authority/retired/log/active-witness keys cannot serve as review evaluators. Public fixture keys are not operational authorities. Maximum review leaf 8192 bytes, total serialized event still subject to 32768-byte limit.

`audit_l12` supports explicit operator-selected `JournalQuorumAnchorTrust(journal, expected, challenge)`. After all eight mandatory gates authenticate and PASS, GATE-09 in this mode is PASS only after local authenticated CAS commit. The result contains `anchor_cursor` (sequence and hex digest) to retain independently before acting; stale/exhausted or unavailable storage is BLOCKED, malformed evidence/integrity failure is FAIL. Existing single-witness and fixed-quorum modes retain behavior and result shape. No automatic release. The operator must quiesce previous epoch services, serialize authority approvals and independently retain the returned cursor. Global old-service revocation and independent external cursor custody are not implemented by this journal. Rollback detection is relative to the retained external floor, not hardware tamper resistance. No compaction after budget exhaustion.

## Evidence

Environment: CPython 3.13.5; Linux 6.18.57 x86_64 glibc 2.41; SQLite 3.46.1; cryptography 46.0.4; pytest 9.0.2. Full git clone unavailable (`git ls-remote` exit 128 DNS). Exact source files reconstructed from pinned GitHub blobs and checked with `git hash-object`:

| Existing dependency | Git blob SHA |
|---|---|
| ontos_v72_jcs.py | 1b61af871b78740203cb2418b0a7ca8d1bd06884 |
| ontos_v72_receipts.py | 1854ada8924eb09f8bcf2efedce8ee852677df90 |
| ontos_v72_checkpoint_note.py | b36f544fe0f4935e31ddd5980b0e3d0fa227c788 |
| ontos_v72_merkle.py | 4aa346d41fd27e654b1df1e5fd01df88d269407f |
| ontos_v72_witness.py | c75f1fc7e349d6491ab0c03f2959fcc6219499e7 |
| ontos_v72_quorum.py | c27c798ac179ef7ec5eb3de4b9b9d83936ad241c |
| ontos_v72_quorum_rotation.py | eba8205a2c6592687c69bd86feab86d1ab0c77a9 |
| ontos_v75_anchor.py | 1132fa0cce79402369aa8876190ee53ff49dffd4 |
| ontos_v72_evidence.py | 3baf6dc6f55d71ac8dfa22ca8066608105c19e36 |
| ontos_v74_campaign.py | 7c5fbed84bff9b1fc7851c187ac362c4c39c2a32 |
| ontos_v75_manifest.py | 2cda8a91a6d16e6d883bd36dace0be9feb7b169d |
| ontos_v49_manifest.py | 11515442fa9adb3ff42f50595d79fcb8da400756 |
| base ontos_v75_acceptance.py | 0e07d9c1426532efe053b24c12df97417ce388bb |

Local package marker was empty in this isolated reconstruction; upstream package initializer and full tree were not exercised. New code/test blob hashes in `QUORUM_JOURNAL_BLOBS_20261125.txt`. Test IDs (including parametrizations), exact final output and result in `QUORUM_JOURNAL_TESTS_20261125.log`; SHA256 sums of all captured logs in `QUORUM_JOURNAL_SHA256_20261125.txt`.

Commands and actual outcomes:
- `python -m pytest -q tests/test_ontos_epoch_journal_core.py` RED missing module exit 2; initial GREEN 13 PASS exit 0 (1.31 s).
- `python -m pytest -q tests` intermediate 16 PASS exit 0 (13.45 s); quorum adapter was implemented then integration-tested (not claimed as RED-first).
- `python -m pytest -q tests/test_ontos_v75_journal_gate.py` RED missing JournalQuorumAnchorTrust exit 2; GREEN 3 PASS exit 0 (6.54 s).
- `python -m pytest -vv tests` final 24 PASS, zero skipped, exit 0 (25.73 s); 15 journal core, 5 real quorum journal, 4 full reducer integration cases. Fixed fixture keys/nonces, seed 7412 for actual paired report calculations. Crash boundary child process exits 23 before/after SQLite commit, not a physical power-cut test.
- `python -m compileall -q omega_x_evolution tests` exit 0.

The full reducer executes real v49 ZIP parsing, v72 evidence verification, v74 report recomputation (1800 synthetic records), actual SQLite witnesses and journal, Ed25519 and Merkle checks. Tests include stale cursor, concurrent acceptance (one PASS/one BLOCKED), missing mandatory gate, single-witness downgrade, bad inclusion proof, restored database, missing storage, previously used challenge, old epoch, actual forbidden evaluator in the leaf, 256-event resource cap, file security and tampered database. PASS refers to these executed properties only, not all L12 requirements. Existing full repository regression and production deployment are NOT RUN. Original v49 source bytes remain 0/33 according to the prior reviewed register; no replacement by fixture bytes. Historical bounded GATE-09 unchanged.
