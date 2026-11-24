# ONTOS-TDA — bounded input hardening, 2026-11-24

Scope: security/reliability corrective increment to the existing latent diagnostic, not a new stage or release authorization. Mode: NATIVE (actual CPython/NumPy implementation and local CLI); bounded stream double asserts the requested read size. No model training or external infrastructure claimed.

Base commit: `38ff7a6cb706320711dea34879c6f3c66fdb7b49`.
Original production blob: `f240ac0ea421f52278a6dd08c4baa235d8b6c194`.
Verified patched production blob: `3f127fe8f35a6eac8419c5aad490e226f9743c27`.
Verified test blob: `cf49480c9ba6d78619e49c8ad7a73a85f88c9b38`.

Defects: text iteration read arbitrary-length records before checking the size; universal newline translation undercounted CRLF wire bytes; deeply nested JSON relied on interpreter-dependent decoder recursion limits.

Contract: at most 4096 bytes per JSONL record including its terminator; each binary readline requests at most 4097 bytes and rejects overflow before decoding. LF, CRLF and final nonterminated records at the exact limit are accepted. JSON structural nesting is capped at two levels before decoding; malformed UTF-8 is rejected. No change to diagnostic mathematics or authorization fields. No claim of bounded total execution time for blocking sources or full process RSS.

Environment: CPython 3.13.5, NumPy 2.3.5, pytest 9.0.2. Local production file reconstructed byte-for-byte from GitHub; original Git blob identity checked. Repository clone unavailable in container due to DNS. Full upstream suite and package build NOT RUN.

Command on original and patched file: `python -m pytest -q --tb=short tests/test_ontos_tda_input_bounds.py`.

RED: 4 failed, 4 passed in 1.88s. Failures: deep JSON (both formats), unbounded read contract, oversize CRLF. Log SHA-256: `62996231746c4c106cf6b5150fb7e67878dbd3d2836aff00cb978006f8e62c72`.

GREEN: 8 passed in 1.79s. Log SHA-256: `f764922a3848e7fce19b6ab336904f8c1b97eb9f79e1d80bee7d6ca8f348d582`.
`python -m compileall -q omega_x_evolution tests` completed locally for the available subset; not a full repository build.

| Test ID (pytest node family) | Cases | Result |
|---|---:|---|
| test_deep_json_fails_closed | 2 | PASS |
| test_jsonl_never_requests_an_unbounded_line | 1 | PASS |
| test_jsonl_exact_byte_limit_and_final_record | 3 | PASS |
| test_jsonl_invalid_bytes_or_oversize_crlf | 2 | PASS |

Bounded input contract TESTED. Full ONTOS-TDA regression, full integration and new GATE-09 are not asserted. Existing bounded GATE-09 maintainer decision remains unchanged.
