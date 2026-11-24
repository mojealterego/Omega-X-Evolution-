# L12 v72 — HMAC and native PQ profiles

Base main: bb955ceea8aa99846096b4918900874ab0afa57d. Actual local CPython 3.13.5, pytest 9.0.2, OpenSSL 3.5.5 (default provider), Linux. NATIVE local software verification. No third-party services or simulation of cryptographic outputs.

Sources: RFC 4231 https://www.rfc-editor.org/info/rfc4231/ ; OpenSSL 3.5 key profiles https://docs.openssl.org/3.5/man7/EVP_PKEY-ML-DSA/ , https://docs.openssl.org/3.5/man7/EVP_PKEY-SLH-DSA/ , https://docs.openssl.org/3.5/man7/EVP_PKEY-ML-KEM/ and https://docs.openssl.org/3.5/man1/openssl-pkeyutl/ . No external source code imported.

HMAC-SHA256 uses stdlib native primitives and constant-time comparison, 32-byte key and tag, test/runtime domain separation. Domain separation is not key custody: deployment must independently provision disjoint keys and trusted role selection. PQ signature input has domain and algorithm label; exact raw key lengths and SPKI DER OIDs bind algorithm. Public verifier requires operator-pinned absolute OpenSSL executable path, explicit default provider, sanitized environment, private temporary directory, no shell, bounded input and timeout. No candidate-provided executable permitted by caller contract. Nonzero backend result rejects signature; missing executable/timeout BLOCKED. No production root changes.

Native test roundtrip signs and verifies ML-DSA-65 and SLH-DSA-SHA2-128s; rejects message/signature changes and truncated signatures. ML-KEM-768 performs real encapsulation/decapsulation in tests; the library exposes public key encoding and ciphertext shape admission only, not secret lifecycle or KEM authentication. KEM cannot be used as signature. Tests use newly generated ephemeral keys and randomness (repeatable assertions, not fixed ciphertext or official KAT vectors). A missing native profile produces explicit pytest skip, never qualification.

RED: python -m pytest -q tests in isolated subset, missing module, exit 2; log SHA-256 336413950fc0031467c06e1979eec0b294466aa023ea24a28d69209c7730f407.
GREEN: same command after implementation/refactor: 8 passed in 0.54s, exit 0, no skips; SHA-256 fe0bc1dbd26fba55350e40a62414d48cf9b29e10dca5dc6faca90ea283e3ddcc. python -m compileall -q omega_x_evolution tests exit 0.
Test IDs: test_hmac_context_and_test_key_separation; test_hmac_bounds (3); test_native_signature_profile (2); test_kem_profile_real_roundtrip_and_role_separation; test_invalid_profiles_and_key_shapes.
Production Git blob d29697f4661abdc2f380f945f6387e1363e5d2d7; test blob e6ce9f35e5cab91c11a56fb260574a5779b6807b.

Full repo regression NOT RUN: GitHub direct clone DNS unavailable. No official PQ known-answer certification, FIPS module qualification, native KEM production adapter, checkpoint note compatibility or integrated promotion acceptance. Historical GATE-09 unaffected.
