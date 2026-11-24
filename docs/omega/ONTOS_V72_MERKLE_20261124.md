# L12 v72 — Merkle proof primitives and L11–L111 specification intake

Base main: 06db734670c0baf47976514ea508dc0762fb4acd. Source material: maintainer-supplied L11–L111 architecture and code, historical base 5e24375d6e77835e7752f6ef4d489d38b4850b23. The historical base is provenance, not a checkout or replacement instruction.

## Integration and evidence

- Reuses the existing namespace omega_x_evolution; does not replace README, package metadata, existing licensing or the evaluator.
- Implements SHA-256 domain separation, root calculation, inclusion and append-only consistency proofs from RFC 6962 in a bounded native Python module.
- Corrects the supplied reference's vacuous empty-root acceptance and rejects malformed hash lengths, booleans in integer fields, arbitrary iterators, excess proof nodes and oversized generation input.
- Proof verification does not authenticate the root; first_size=0 to a nonempty tree is a vacuous consistency claim, not attestation.
- Limits: 4096 prehashed leaves for generation, 1 MiB leaf input, 2^63−1 maximum verification tree size, 64 proof nodes. Only finite software behavior is tested.
- Verification mode NATIVE (actual local CPython/hashlib software, not hardware qualification). No promotion or runtime trust change.

Environment: Python 3.13.5, pytest 9.0.2, Linux container. Command: python -m pytest -q tests/test_ontos_v72_merkle.py. RED: missing module, collection exit 2 (one error). GREEN: 11 passed in 0.08s, exit 0. python -m compileall -q omega_x_evolution tests: exit 0 for isolated source subset. Full repository clone failed DNS; full regression not run.

Production Git blob: 4aa346d41fd27e654b1df1e5fd01df88d269407f.
Test Git blob: a96ca6e9dd0f929b78039f2c966c3f28ee0c747f.
RED log SHA-256: 13614cd1ea14bab23d8717fd07ef5bcd0814840730acae0aed2684a902fca43d.
GREEN log SHA-256: 80cc2ecf12ffc8469e01131917b32ec0682eac22f6e92080be3e6d3a005b8aa8.

Test IDs: test_rfc6962_domain_separation_and_empty; test_all_prefixes_and_leaves_through_32 (528 valid inclusion and 560 valid consistency cases, negative mutations and independent raw-item root oracle); test_invalid_size_rejected (6 parameters); test_empty_checkpoint_must_have_empty_root; test_invalid_hashes_and_proof_budget; test_untrusted_iterators_not_invoked. No RNG needed.

## Specification intake — remaining work, not acceptance

| Scope | Integration decision / defects to resolve |
|---|---|
| L11 v68–v71 energy/Pareto and FeRAM | Existing v68–v71 modules retained; extend only after differential audit; missing system components and PSU remain UNKNOWN; no physical claims. |
| L12 v72 | Merkle primitive TESTED; JCS, authenticated signed receipts, schema validation, HMAC/PQC profiles, integration OPEN. Do not rely on pure-Python secret scalar arithmetic for production signing; enforce exact signature scope and schema. |
| L12 v73 | OPEN. AST denylist is not isolation; callback holdout in the same interpreter leaks inputs/seeds; need process/capability boundaries, attempt budgets and negative tests. |
| L12 v74 | OPEN. Frozen protocol, complete campaigns, paired inference and multiple-testing correction; no fabricated metrics. |
| L12 v75 and v81–v87 | OPEN; preserve all requirements. Hash-shaped strings alone are not authenticated gate evidence. |
| L13–L111 | PROPOSED_NON_BINDING; 99 levels / 396 packages, no automatic promotion. Map validator must include cross edges in cycle detection, transitive prerequisites and authenticated scope approval. |
| L13 Rust/Zenoh/WASI | Proposal only; unsigned leases, globally trusted signers, ambiguous delimiter signing and raw-frame publication require repair; verify exact dependency versions/MSRV before native acceptance. |
| L14 external anchor | Proposal only. File signature does not prevent rollback of the witness itself. Model requires separately trusted monotonic state, atomic CAS and explicit failure semantics. |
| L16 AB/BA | Proposal only; preserve Stage 3b correctness; reject nonfinite/unpaired data and use preregistered paired design. |
| L20 journal/CAS | Proposal only; validate digest and path, lock writers, bound frame allocation, distinguish corruption from interrupted append. |
| L57 hardware simulation | Proposal only; existing RAMXEED model retained; distinguish datasheet bounds from assumptions. |
| Documentation catalog | Proposal only; validate metadata before writes, deny traversal/symlinks, do not redistribute restricted sources. |

Historical bounded GATE-09 maintainer decision unchanged. This increment does not close the full v72 stage, L12 or L11, nor authorize L13–L111. 
