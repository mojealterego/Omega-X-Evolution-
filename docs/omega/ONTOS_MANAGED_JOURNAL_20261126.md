# L12 — fenced segmented journal, independent anchor and non-destructive rollover

Base main e2a7aee6aa5240480a765e8d052bd52b783553b5. Three scoped mechanisms in ontos_managed_journal.py reuse the exact production Journal core blob 3410f146d47cb3a8c0ed008e75fa58819a8966a0.

1. Fence binds segment generation, cursor and lineage; append/compact CAS refuses stale clients. flock serializes cooperating local processes. All writers must use the gateway. This is not remote service revocation or autonomous distributed consensus.
2. Separate protected anchor directory/database holds durable intent and committed floor. Recovery completes a prepared write after a process interruption before or after the segment commit. Restored segment or unprepared append fails closed. Restored anchor detection requires exact independently retained fence. Same-host directories are not independent physical failure domains; production custody remains open.
3. Non-destructive compaction (segment rollover): archive old segment and seal, initialize successor with canonical complete state, reset local sequence, increment generation and hash-link lineage. No history deletion. Active replay bound 256 events; max generation 1024, state encoding 1 MiB. Sealed segments can be individually replayed. Storage is not reclaimed. Recovery of an exact empty orphan successor is tested; arbitrary damaged orphan recovery and rollover interrupted during initial segment creation are not proven.

## Native local verification
CPython 3.13.5, SQLite 3.46.1, pytest 9.0.2, Linux 6.18.57 x86_64. Isolated exact base core and new files; byte-state test contract, not quorum cryptography in this layer.
- RED pytest -q tests/test_ontos_managed_journal.py: missing module, exit 2 (0.10s), log SHA256 83ba6b57f9145f078bbb5a438e0acad23c527d1ea69ce21da2ab69faf1761f38.
- GREEN same command: 12 passed (0.23s), exit 0; log SHA256 565ade205a987af445e884d655d9c669f93f009dce77f5ad13b9baafe7bec268.
- Final pytest -vv tests: 17 passed (3.58s), exit 0; log SHA256 70fd3bdd91775c2eaf1a3fb18ff1869e22baf56d283fa078c348b9bd2aa8396a.
- Fresh rerun python -m pytest -q tests: 17 passed (3.61s), exit 0.
- python -m compileall -q omega_x_evolution tests: exit 0.
- Implementation Git blob 2cbbbb3846138b7b93d96a8a422ddc80b1b5dc6a; tests 5cedb5d818e22b79bd30a6a782c194302936f434.
- git ls-remote exit 128: Could not resolve host github.com. Full repo regression not run.

Test cases: stale append/rollover, restored journal, compaction preservation and reopen, concurrent CAS, rejected event, prepared intent recovery before/after commit (exception and actual child exit 23), orphan rollover, unprepared append, restored anchor, empty compaction, separate directories, full 256-event segment, sealed archive tampering, multiple generations. Model excludes bypass by privileged writers, coordinated rollback of all trusted domains and physical power loss. No operational deployment or actual L12 source reproduction.

## Remaining integration
ManagedJournal is a generic storage layer, not yet wired into QuorumEpochJournal or audit_l12. Its segment generation is distinct from cryptographic membership epoch. Membership rotation must explicitly invalidate old capabilities through the gateway; remotely running legacy witnesses remain outside scope. Typed complete quorum state codec, preserving all retired keys and nonce history, and managed GATE-09 integration remain OPEN. Full L12 remains BLOCKED.

## Orphan rollover fencing regression
Base 7e449c6432b9a1df3bb57a6ea50475efcbb85141. Previously a new segment could be created before the anchor activation, then an append to the old generation would change the expected bootstrap and permanently block the retry. Append now returns ROLLOVER_PENDING while a successor path exists (including a dangling symlink); compact validates the exact empty successor and activates it. Malformed or inaccessible successor remains fail-closed.
- RED python -m pytest -q tests/test_ontos_managed_journal.py -k orphan_rollover_fences_old_generation: exit 1 (COMMITTED instead of ROLLOVER_PENDING), log SHA256 c77736426cba537d5916cd0b8aac377e215c3c7aca05547a24ed0f6e537cfb84.
- GREEN same command: 1 passed, 17 deselected, 0.06s.
- Full isolated subset python -m pytest -q tests: 18 passed, 3.73s; log SHA256 30a154406671ac96cf17978d954a72ec319f4d42d65eb72c873e2de4fe8ed317.
- Compileall exit 0. New implementation blob 69ad7abaf41c653ae2e31111c86945f0fe8147ae; tests a1ea345267cf2e673d5530c6eb01a8d6c4b65ada.
