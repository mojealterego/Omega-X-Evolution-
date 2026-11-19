# Native LRAT certificate gate — v31 corrective continuation after v36.4

Base main: `6119d63b7273bd2c42a999d93d0676e5f584b3fc`. This is the existing v31 obligation, not a new roadmap stage. No paid CI or external provisioning. Native Lean lemma acceptance and previously accepted deterministic infrastructure models remain valid.

## Resumed implementation and trust boundary

The maintainer's interrupted session reported native CaDiCaL and `lrat_isa` integration. The original binaries were recovered from the saved Drive artifact and independently checked against its outer checksum and inner SHA256SUMS. `lrat.py` implements deterministic Tseitin bit blasting of validated pure u16 IR (ADD, SUB, MUL modulo 2^16, XOR, AND, OR) and a disequality assertion over all 2^32 input pairs. CaDiCaL 3.1.0 is an untrusted producer; actual `lrat_isa`, compiled from Isabelle-exported LLVM, independently checks the binary LRAT certificate. An UNSAT result alone does not promote a candidate. Verification reconstructs the CNF, binds the exact source IR and CNF separately, verifies the certificate hash, and runs the checker on the stored bytes without invoking CaDiCaL. SAT, unknown, unavailable, malformed, oversized, timeout and failed checking are non-PASS. The solver/checker have bounded time, 64 MiB file limits and a 1 GiB address-space limit; neither executes candidate source. The checker is native, not a mocked solver.

`higher_order.prove` and `optimize` accept `require_lrat=True`; `verify(report, require_lrat=True)` enforces externally specified policy rather than trusting caller-supplied policy flags. The existing default behavior is preserved for compatibility. Strict IR snapshot validation now also precedes theorem generation in `higher_order`. All proof results remain separate from native Lean tactic or full Isabelle theory verification. The trusted base includes the independently tested Python CNF encoding and trusted local executable installation; it is not a machine-checked proof of the encoder itself or a full Isabelle/HOL runtime.

## Evidence (NATIVE)

Environment: Linux x86_64 6.18.57, Python 3.13.5, pytest 9.0.2. Tools recovered from [native LRAT package](https://drive.google.com/file/d/1Bm7YgDOb8CdsX8kBDExfs7cahJGR62-z/view), SHA-256 `fb1887b3ae31cb425860079c365c49b3b674155cf4a2989b70304d5360df2f95`, and [Lean BitVec runtime](https://drive.google.com/file/d/1XsYiRzLZB_WbVPL9-FAxVNcaet5bNh12/view), SHA-256 `8a0c1d462699cd5a51d9486664eb82768c5b77f3f5ce6ab6404ee373c2c3d925`. Lean checkpoint SHA-256 `c5e8362d308aa049b5dd09bd42577f82fd781c7c7d4832ef22b9e34a4df2d0fc`. Base full source ZIP SHA-256 `0abb2e5e8b01fbd0cf062b7af43d41af6a6e5c1f4ce285d824343ccb5fcde2e6` matched detached checksum; current `polyglot.py` and previous boundary tests matched Git blobs on main.

- LRAT-RED: native test run against initial reconstructed module: 14 passed, 2 failed (no solver-free replay and `require_lrat` absent); gate policy also reproduced. Implemented stored certificate and promotion/replay policy.
- LRAT-GREEN: `PATH=/path/to/omega-lrat-native-3.1.0/bin:$PATH OMEGA_LRAT_NATIVE=1 PYTHONPATH=. python -m pytest -q tests/test_omega_lrat.py tests/test_omega_ir_boundary.py tests/test_omega_v13.py` — exit 0, **52 passed in 16.60 s**. Includes 33 LRAT tests, all six true and false word-operator cases, mixed expression, forged proof with recomputed hash, solver-free replay, source/CNF binding even for identical simplified CNF, missing checker, required policy and optimization; all 256 pairs per operator at width 4 with emitted clause evaluation; seeded nested u16 tests; existing typed IR and six actual code-generation backend regression.
- LEAN-CORE: actual recovered Lean `4.36.0-pre`, `check_lean` with 12-second deadline for `(x+y)-y=x` (core-addsub) and `x*1=x` (bitvec-lemmas), both checked. Source SHA-256 `94e9f44b1657c01f1481645c6e9d9e2654bdedd64d521d40c9896d998c7ace50`, `210e38e6de5bf056b1c3b86e574fa5f27afc397832cd02da89e5fb66b65156fb` respectively.
- BUILD-01: `python -m compileall -q omega_x_evolution tests/test_omega_lrat.py` — exit 0.
- Regression beyond this focused suite: a full native Lean-focused run reached 58 completed cases before timeout (no final summary), and a broader targeted run exceeded its time limit. Full upstream suite not reaccepted here. No skipped or timed-out test is reported as a PASS.

Tested Git blobs and SHA-256:

| File | Git blob | SHA-256 |
|---|---|---|
| `omega_x_evolution/lrat.py` | `b2ba6a3a9521dd56b85ade6665dd433709f13134` | `e5eaee2b1b02f89be8d8144fa8c44cca7797aafbe9906aeb1f61643b8d37e53f` |
| `omega_x_evolution/higher_order.py` | `736c4682f9498b96152ebf37173bfb0f6588c27a` | `96aa13f7b3723ea1a9746f846149b88f35c525cbe3f890bf06896beb0593cf3f` |
| `tests/test_omega_lrat.py` | `c61f56d709d75cebf05f5f9e4296a9f667398aa1` | `14cd68ad3190fd7e730c04014e292e83dea59c5d62ca0cf0b19d43157e232b27` |

## Residual acceptance

PASS: native proof production and independent certificate replay for tested u16 obligations and explicit promotion policy. Full `Std.Tactic.BVDecide` is not in the restored checkpoint (only a partial Normalize module); no full Isabelle theory build was performed. Direct GitHub network resolution failed; attempts to recover complete source archives from available files/Drive did not yield the original archive. The precompiled official Lean distribution could not be downloaded in the current environment. This does not invalidate earlier native Lean lemmas or the newly accepted LRAT properties. The native full Std/BVDecide integration remains to finish; no claim of unconditional GATE-09 PASS, and no movement to another roadmap stage.
