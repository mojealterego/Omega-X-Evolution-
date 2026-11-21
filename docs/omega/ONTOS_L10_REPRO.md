# OMEGA-X ONTOS Ω∞ — L10 v63–v67, Hybrid Engineering Verification

**Target repository:** `mojealterego/Omega-X-Evolution-`, branch `main` only.  
**Base commit:** `c45323d58e12e5867cfceec37a90872554725544`.

This ZIP is a reproducible **local development/test subset** (not a clone of the entire upstream repository). Its new files extend the prior v63–v66 code with:

- Native libz3-backed i4 IR equivalence, time-bounded Z3 QF_BV symbolic noninterference/Caps/static-shell proofs and signed Q16.16 arithmetic-shift checks.
- Four-obligation Ed25519 authorization across IR proof, HyperLTL-style noninterference, all bounded interleavings, and HiGHS LP harm bound.
- Go 1.23 separate-process native Unix socket gateway, cross-language signed attestation, replay/tenant/nonce defense, durable signed state + signed companion anchor, and `go test -race` green after a real RED race.
- Actual SystemVerilog static shell and Q16.16 accelerator sources; independent native C and clang WebAssembly execution of arithmetic; **no RTL simulator, FPGA ICAP programming or CIRCT LEC claim**.
- An explicit negative test **XFAIL** documenting that rollback of *both* co-located signed state+anchor files is not prevented without an independently protected monotonic trust anchor.

**Acceptance:** `PASS` for **finite tested modeled properties**, `BLOCKED` for full L10 / native Rust+Zenoh+WASI / physically attested FPGA / source Suite D / production assurance. The historical, separately scoped GATE-09 is not modified. See `docs/omega/ONTOS_L10_V63_V67_CLOSEOUT.md` and `docs/omega/ONTOS_L10_V63_V67_GATES.json`.

## Replay, offline

```bash
python -m scripts.verify_ontos_l10
# Exit 0 only if all specified local Python+Go checks passed; prints full-system BLOCKED.
python -m scripts.verify_ontos_l10 --require-full
# Exit 2: intentionally refuses to approve unverified full L10.
```

Environment verified: Linux x86_64, Python 3.13.5, pytest 9.0.2, NumPy 2.3.5, SciPy 1.17.0, cryptography 46.0.4, Go 1.23.2, native libz3.so.4, GCC 14.2, clang 17 and Node.js 22. No external API access or credentials required by the test harness. Actual Go signing keys are generated in test fixtures only and are not part of this ZIP.

For per-file SHA-256 and exact test commands, consult the machine-readable gate and archive SHA-256 checksum. This package is for reproduction and technical audit, not deploy.
