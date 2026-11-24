# L12 v72 — strict Ed25519 and detached evidence receipts

Base main: bc10c0cee189b68ab8ac2e0c8c0eca7d3044e5f7. Maintainer-supplied L11–L111 reference is integrated incrementally without changing the established evaluator, signing roots or operational rights.

The backend is cryptography 46.0.4, not handwritten secret arithmetic. Local exploratory negative probe showed bare backend verification accepted the identity public point with an identity R and zero S. The stricter application profile requires canonical decoding, nonidentity and prime-order subgroup membership of both A and R, and S < L before native verification. Public-data subgroup arithmetic is bounded; it does not handle secret keys. Absent backend fails closed for verification. No claim of exhaustive cryptographic qualification or side-channel audit.

Detached receipt uses domain-separated bounded JCS from the previous increment. Exact scope: level L12–L111, one of GATE-01..08, commit SHA, tenant, evaluator ID. Record SHA-256 is recomputed from the supplied actual record. Trusted public key and expected scope are obtained from the caller, never from the receipt. Verification authenticates bytes/scope only; it does not validate Section 10 semantics, prove test execution, authorize scope, or promote. No GATE-09 signature permitted. Fixture key is public RFC 8032 test seed, never a production key.

Environment: Linux x86_64, CPython 3.13.5, pytest 9.0.2, cryptography 46.0.4, Node.js v22.16.0 for prior JCS oracle. Mode NATIVE (local software). RED: python -m pytest -q tests/test_ontos_v72_receipts.py, missing-module collection exit 2; log SHA-256 322ffd0cf8d5ee43d804ce7cf15a01b4289e901b584db1f408d196c2eff27576.
GREEN: python -m pytest -q tests/test_ontos_v72_receipts.py tests/test_ontos_v72_jcs.py tests/test_ontos_v72_merkle.py, 49 passed in 0.32s, exit 0; log SHA-256 c3158c112abad2aaab5d84c33c0144251992f2acb045331c08f443da2d8c7bc1. Compileall isolated subset exit 0.

Test IDs: test_rfc8032_vector_and_native_signing; test_reject_small_order_noncanonical_and_negative_zero (5 cases); test_receipt_binds_record_and_expected_scope; test_receipt_tampering_fails_closed (6 cases); test_scope_and_input_validation. Fixtures deterministic. Production blob 1854ada8924eb09f8bcf2efedce8ee852677df90; tests 2fc2f8c9c5eefeab01e4e5f5045c0bfa3983aa85.

Full build/regression NOT RUN due to unavailable direct repository clone (DNS); previous v72 modules executed in same local source subset. This does not establish TCB deployment, key custody, runtime isolation, anti-rollback, C2SP compatibility, PQC, or full v72/L12 acceptance. Existing bounded GATE-09 unaffected.
