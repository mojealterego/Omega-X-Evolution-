# L12 — quorum state structural codec (OQS v1)

Base main 7847d0990c1c6545ad54f3782937eb35a6133e05. New bounded binary record, not yet wired into the existing journal or v75 reducer. No changes to the fixed evaluator, authorization, or operational keys.

## Format and invariants

Big endian: magic OQS + version byte 1; environment byte (0 simulation, 1 operational); two unsigned name lengths; ASCII origin and signer name (1–255 each); uint32 epoch (<2^31); uint64 tree size (<2^63); log key, Merkle root, authority key and four sorted witness keys (32 bytes each); uint8 retired count (0–128), sorted retired keys; uint32 challenge count (1–32000), ordered distinct 32-byte challenges. Last challenge is derived from the final history entry, and checkpoint origin from the common origin. Maximum serialized size is 1,028,854 bytes, below 1 MiB. Extra bytes, bad lengths, unknown versions, role overlap, duplicate history, noncanonical key order and invalid empty roots fail closed. No truncation, no pickle, no dynamic execution.

Architectural decision: binary framing rather than JSON for bounded storage and exact 63-bit sizes. The 32,000-challenge cap includes the bootstrap nonce. An adapter must fail closed before exhausting it; no pruning or silent nonce reuse is allowed. The codec validates structural key roles, not prime-order points, signatures, consistency proofs, or authenticity. Before any journal integration the adapter must reconstruct the existing typed QuorumEpochPin and validate the exact existing state digest against a retained fence. Legacy witness revocation and physical custody remain out of scope of this component.

## Native verification, isolated component only

CPython 3.13.5, pytest 9.0.2, Linux 6.18.57 x86_64. Test IDs are pytest node IDs. Deterministic seed 20261126 (1024 mutated records). Synthetic 32-byte key fields are structural fixtures, not evidence of Ed25519 verification.
- RED: python -m pytest -q tests/test_ontos_quorum_state_codec.py: exit 2, missing module; SHA-256 49d8fb8850cea1ee9c1a5f1a2d9eddfea4f8451282eaa56c296c249b5cfe3f46.
- Initial GREEN: 23 passed in 0.17s. Additional tests exposed an incorrect expected byte count in the test (not a codec defect); 25 passed, 1 failed; SHA-256 033840792f0fdfe847c44e85116202fdec14c392ba264f18e0f8cc7c6acedd97. Corrected expectation to the exact independent sum of field widths.
- Final GREEN: python -m pytest -vv tests/test_ontos_quorum_state_codec.py: 26 passed in 0.22s, exit 0; SHA-256 c99633e69b834927abab67ae5949ba261dedac957e92dd4f40c3e3624ce33572.
- python -m compileall -q omega_x_evolution tests: exit 0 (isolated files).
- Verified local source blob 98d64c213bbceecf94f5812555abdfbc7fb6feda; test blob d5a0bb39e8d7f5b867cc27f37af3861272b1cf86.
- git ls-remote exit 128: DNS failure in local container. Full repository regression not run. GitHub API available for source inspection and atomic main update.

Structural codec: IMPLEMENTED / TESTED (NATIVE). Quorum integration, recovery with actual quorum certificates, v75 managed gate and full L12: OPEN/BLOCKED. No claim of deployment, cryptographic acceptance, or complete Roadmap closure.
