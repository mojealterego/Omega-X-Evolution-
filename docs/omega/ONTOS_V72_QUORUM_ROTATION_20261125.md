# L12 v72 — planned witness quorum handoff

Audited base main 214690ba95c190b61d8b7c84c928cfec441db2b9. Joint old/new 3-of-4 certificates over an exact same signed Merkle checkpoint, next-epoch single witness replacement, mandatory newcomer vote, offline pinned authority signature, separate challenge domains, no log/environment change, bounded retired-key exclusion. Old checkpoint consistency is checked against retained client floor. New epoch supports further authenticated appends. Existing v72 QuorumWitness/WitnessStore and Ed25519 verification are reused without modifications.

Scope: native SQLite/Ed25519 and finite fault schedules (HYBRID). The old epoch must be quiesced and authority approvals serialized. The caller must atomically persist the returned pin in an independently retained trust domain. No distributed membership consensus, automatic old-service revocation, authority/log-key rotation, durable client epoch journal or v75 anchor wiring yet. Simultaneous all-domain rollback and authority equivocation are outside this verifier. Actual L12 remains BLOCKED; historical bounded GATE-09 unchanged.

## Executed verification

Environment CPython 3.13.5, pytest 9.0.2, cryptography 46.0.4, Linux. Exact Git blobs recovered and hash-object checked:
- receipts 1854ada8924eb09f8bcf2efedce8ee852677df90
- checkpoint_note b36f544fe0f4935e31ddd5980b0e3d0fa227c788
- merkle 4aa346d41fd27e654b1df1e5fd01df88d269407f
- jcs 1b61af871b78740203cb2418b0a7ca8d1bd06884
- witness c75f1fc7e349d6491ab0c03f2959fcc6219499e7
- quorum c27c798ac179ef7ec5eb3de4b9b9d83936ad241c

New code blob eba8205a2c6592687c69bd86feab86d1ab0c77a9, final test blob 183f5e920fc10577f42d3b6687e5d7e32adf6c8b. IDs in tests/test_ontos_v72_quorum_rotation.py. Fixed keys and deterministic Merkle inputs are test fixtures, not secrets or production authorities.
- RED python -m pytest -q tests/test_ontos_v72_quorum_rotation.py exit 2 missing module, 0.19s, SHA256 a67a6f452b6d308528beee2e632d855f5fa29bf64b951d18a2a28b807829a5d0.
- GREEN same command exit 0, 13 passed in 17.19s, SHA256 45765787a4bb82639e6b275f4bbf6115d169f2c1375a525ba540168c9b6006b6.
- Final isolated subset python -m pytest -q tests exit 0, 37 passed in 19.31s, SHA256 f4c09a1086502182fd300580ed15d8b1707105fdff27b529ab6329b1ac854e57 (14 new + 23 previous archive/manifest).
- python -m compileall -q omega_x_evolution tests exit 0.
- Exhaustively checked 16 combinations of exactly 3 old and 3 new votes (12 accepted, 4 rejected for absent newcomer); both two-vote partitions rejected, malformed/forged receipts, replay, wrong floor, missing consistency proof, skipped epoch, retired key and environment escalation rejected. Native store reopen and subsequent Merkle append, old epoch certificate rejected under new pin.
- Full repo git ls-remote exit 128 DNS resolution failure; full regression and full build NOT RUN.

Reference source uploads inspected separately; see ONTOS_HARDWARE_INTAKE_20261125.md. No upstream binary or source execution.
