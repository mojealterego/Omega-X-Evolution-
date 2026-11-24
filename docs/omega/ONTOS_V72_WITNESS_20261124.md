# v72 durable witness and key custody

Base main: cee522922d7fcff23703cffa7047f4b19f2d27f4. Production module uses actual SQLite (journal DELETE, synchronous FULL, explicit initialization, atomic revision CAS, no auto-create on reopen), the existing strict Ed25519 verifier, C2SP and RFC6962 consistency proof. Each read is signed by a distinct witness key and bound to externally pinned environment, origin, key name, log/witness public keys, revision, exact note SHA-256 and fresh 32-byte client challenge. The client may independently retain a minimum revision and a previously verified receipt, checking consistency to reject lower revision, equal-revision forks and higher-revision divergent histories even after witness storage restoration. Never grant promotion. State and signer must be administered outside the log/candidate trust boundary; storing all state under one attacker-writable directory is not independence. All trusted ancestors of configured directory must be operator-controlled. No claim of protection when all trust domains or witness signer are compromised, external transport/OS service isolation, power-loss device guarantees, HSM certification, key rotation or actual production deployment.

Operator key provisioning: CSPRNG Ed25519, encrypted PKCS8, private directory, 0600 regular files, no symlink/no overwrite, fsync, bounded load, password and independently pinned public key validation. Explicit environment binds simulation versus operational receipts; an operator must independently approve fresh operational keys and provide isolated custody. Setting environment alone does not certify a key or authorize production. Linux/POSIX profile. Tests use public fixed seeds only for protocol; encrypted key provisioning uses native randomness.

Environment CPython 3.13.5, SQLite 3.46.1, cryptography 46.0.4, pytest 9.0.2, Linux. Dependency Git blobs exactly matched: merkle 4aa346d41fd27e654b1df1e5fd01df88d269407f; checkpoint note b36f544fe0f4935e31ddd5980b0e3d0fa227c788; receipts 1854ada8924eb09f8bcf2efedce8ee852677df90; JCS 1b61af871b78740203cb2418b0a7ca8d1bd06884. Source blob c75f1fc7e349d6491ab0c03f2959fcc6219499e7; test blob 9d1a1f99ed5fc45195008de94ef04f881d0e082e.
RED: missing module exit 2 SHA256 d6cd1406061a238178286127ea1b993dd8f3da81ddad472f776a7c7fed10cc8e. RED2 minimum revision unsupported, exit 1 (1 failed, 9 passed) SHA256 29a738cd4b8712dc1f0fbd8e93f2ee858a98e48db7be1a80b6d033755fa7b299. RED3 missing transition verifier exit 1 (1 failed, 10 passed) SHA256 659ae34e478c0534822f34f81c8a7719bf6ef2eda5c13b35022c971a755c8996. GREEN python -m pytest -q tests (isolated exact-blob subset): 11 passed in 3.38s, exit 0; SHA256 6216a50217e94bf5b2e381086c0882c4576b08799f38f79e7a08bd131ec92cfd. python -m compileall -q omega_x_evolution tests exit 0.
Test IDs: test_persisted_monotonicity_and_log_rollback; test_fork_bad_proof_and_signer_rejected; test_atomic_compare_and_swap; test_freshness_and_independent_trust; test_missing_and_reinitialization_fail_closed; test_uncommitted_process_crash; test_committed_process_crash_before_reply; test_encrypted_operator_key_lifecycle; test_client_floor_detects_witness_snapshot_rollback; test_tampered_database_note_and_permissions_fail_closed; test_client_pin_detects_same_revision_fork_after_witness_restore.
Fault schedule: kill before commit exit 91, kill after committed advance before reply exit 92, reopen, competing CAS, restore earlier database snapshot then fork at equal/higher revision. Separate retained client pin rejects divergence. The process crash precommit test injects SQL in the trusted store process, not a candidate capability. No real physical power cut asserted.

Actual v74 integration probe: read existing signed reference checkpoint from Git blob 13f1bf93f3209291b71142fa0699923badbf168b, pin its log key, verify signed note tree size 1802 root ee2167b0df32c77b6cb21654bae59833f7981e81dc07b813e40eccc813b5c2ac, provision a fresh encrypted witness key in TemporaryDirectory, initialize with that trusted note, reload key and store, verify fresh challenge-bound receipt revision 0. Log SHA256 5a30485688cb7ff96e193a988bd8f35117a971ad10072a228533884bb453cf4f. Temporary key and store discarded; not an independent live witness or new production attestation. Existing reference JSON SHA256 unchanged bbff6f68a67b06a7af5262f7c265f2ce6036c9fca41e406502f8020d0b9abdc6.

Full regression: git ls-remote to repository failed DNS exit 128; connector tree returned 914 entries nontruncated, binary codeload archive not transferred. No paid external runner started. No full repo PASS, historical GATE-09 unchanged.

## Extended exact-blob regression

At main 94ecb3752669cfbf7272522d94aab2e2fe29dda5, reconstructed the following exact Git blobs into an isolated test directory (minimal empty package initializer only for this subset, not part of repository changes). No repository-wide pytest configuration/conftest or unrelated packages were run.

| File | Git blob SHA-1 |
|---|---|
| omega_x_evolution/ontos_v72_checkpoint_chain.py | c197c1353d529997616ad73422506629935d0133 |
| omega_x_evolution/ontos_v72_checkpoint_note.py | b36f544fe0f4935e31ddd5980b0e3d0fa227c788 |
| omega_x_evolution/ontos_v72_jcs.py | 1b61af871b78740203cb2418b0a7ca8d1bd06884 |
| omega_x_evolution/ontos_v72_merkle.py | 4aa346d41fd27e654b1df1e5fd01df88d269407f |
| omega_x_evolution/ontos_v72_receipts.py | 1854ada8924eb09f8bcf2efedce8ee852677df90 |
| omega_x_evolution/ontos_v72_witness.py | c75f1fc7e349d6491ab0c03f2959fcc6219499e7 |
| tests/test_ontos_v72_checkpoint_chain.py | 83e69f83b25ae07740217fb6bffb8b8c969ba5f3 |
| tests/test_ontos_v72_checkpoint_note.py | d507dfadd4ced5f828a35be540ed6ed75652cc64 |
| tests/test_ontos_v72_jcs.py | 2c8ea12e38d1d7dc8cbcce6c353cf8ed777558c7 |
| tests/test_ontos_v72_merkle.py | a96ca6e9dd0f929b78039f2c966c3f28ee0c747f |
| tests/test_ontos_v72_receipts.py | 2fc2f8c9c5eefeab01e4e5f5045c0bfa3983aa85 |
| tests/test_ontos_v72_witness.py | 9d1a1f99ed5fc45195008de94ef04f881d0e082e |

Command: python -m pytest -q tests. Exit 0. Actual output:

```
........................................................................ [ 80%]
.................                                                        [100%]
89 passed in 4.43s
```

Log SHA-256 b70c73913d2266513f0808dc9aa010eeda7c42e4d2281a0b5a045e83de65a136. 11 new + 78 pre-existing tests, 0 skips; includes independent Node ECMAScript differential oracle, RFC8032 test vector, finite Merkle proof cases and native SQLite process-crash recovery. This is a verified dependency-slice regression, not full repository regression. No deployment or external runner cost incurred.
