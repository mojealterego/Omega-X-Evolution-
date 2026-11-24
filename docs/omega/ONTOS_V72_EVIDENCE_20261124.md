# L12 v72 — Section 10 evidence admission

Base main: b04fa9ec47bf88bb65488a74266ad100ab30965a. Implements the supplied nine-section contract in the current package using stdlib field/semantic validation and existing v72 JCS/Ed25519. No replacement of project licensing, evaluator, policies or package configuration.

Admission rejects missing/extra fields, invalid package phase, SHA, UTC timestamps, incorrect data types and nonfinite metrics. PASS requires exit code zero; DEPLOYED is not itself a verification mode sufficient for PASS. Simulation/hybrid must declare limitations; claimed restart test requires replay digest; latency p95 cannot exceed p99. Approval reference presence is checked, not treated as authority.

ArtifactBundle holds actual source, log, provenance and optional replay bytes, each at most 16 MiB; digests recomputed and compared to the record, exact scope level/commit/tenant bound to the signed receipt and externally pinned signer. Authenticating a record does not certify the truth of log contents, execution, key custody or permissions. All outcomes (even authenticated PASS) explicitly return release_authorized=false. Test fixtures are synthetic and not project release evidence.

Environment: Linux x86_64, CPython 3.13.5, pytest 9.0.2, cryptography 46.0.4 and Node.js v22.16.0. NATIVE local software verification. RED: python -m pytest -q tests/test_ontos_v72_evidence.py, missing-module collection exit 2, log SHA-256 3f1f67ed667ae66ea6b1cf2507914a77e015ce37fc7f5c23e2eb509c08725196.
GREEN: python -m pytest -q tests/test_ontos_v72_evidence.py tests/test_ontos_v72_receipts.py tests/test_ontos_v72_jcs.py tests/test_ontos_v72_merkle.py; 88 passed in 0.42s, exit 0, log SHA-256 6193ef41f69ab427b3caa901aa51a452600702ae9f6cf46ba8423ac3cc390789. Compileall isolated subset exit 0.

Test IDs: test_valid_record_authenticates_but_does_not_promote; test_every_section_required (9); test_invalid_fields_and_semantics (20); test_actual_artifacts_must_match (4); test_signed_record_cannot_disagree_with_receipt_scope (3); test_invalid_signed_record_and_nonpass_authentication; test_artifact_bounds_and_optional_replay. Deterministic fixtures, seed field 72. Production blob 3baf6dc6f55d71ac8dfa22ca8066608105c19e36; tests 20eadd4b4ffdd418c959cecccfd2f9f33f061177.

Full repo build/regression NOT RUN, direct clone DNS unavailable. No complete Draft 2020-12 JSON Schema artifact yet; validator implements the nine-section admission contract, with stricter semantic conditions. HMAC/PQC, authenticated checkpoint and live integration remain OPEN. Existing bounded GATE-09 unaffected.
