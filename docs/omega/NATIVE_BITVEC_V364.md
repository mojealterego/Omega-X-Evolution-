# Native Lean BitVec expansion — v36.4

Base main: `e6c7b0679854b04963b6ede311474748ef9a61af`. Corrective extension of v31, not a new stage. No paid CI, external service or cross-repository write.

## Source intake

Six additional maintainer ZIPs were read, hashed and CRC-checked in full. The [source inventory](LEAN_SOURCE_INVENTORY_V364.json) records actual archive digests, ZIP comments (source commit identifiers, not signed attestations), toolchain versions and file counts. Total 20,755 `.lean` files and zero precompiled `.olean` files. The newly supplied `lean4-master` differs in Basic, Lemmas, BVDecide and CMake files from the previously verified release. Mathlib/Batteries specify 4.36.0-rc2; NavierStokesAndEuler and mathematics_in_lean specify older toolchains. We intentionally retain the earlier release source (`lean4-4.36.0.zip`, SHA-256 `824b0e63474848a1b5e86c80c7375b81d7d8a362e0fe426eb685324f5a733838`) and matching stage0 binaries; no incompatible sources or compiled modules are mixed. New source archives are preserved as inputs, not asserted compiled or incorporated into the project.

## Native acceptance

`lean_native.lean_bitvec_source` now emits a fixed theorem for all six permitted u16 operators against actual upstream `BitVec.Basic`, `Nat.Bitwise.Lemmas` and `Nat.Lemmas`. The new lemmas are proved by the real Lean kernel using modular arithmetic and bitwise natural-number identities, not extra axioms. It uses the old `core-addsub` fast path when successful, then `bitvec-lemmas`, then the original `bv-decide` path, sharing one timeout. The `core_only` contract remains unchanged. Source is reconstructed from validated IR, warnings are errors, and the kernel is explicitly enabled in the new proof envelope. The source hash in each report binds the exact generated theorem. Unknown/rejected/timeout/unavailable results never promote candidates. The rewrite procedure is incomplete; a failed tactic is not a mathematical counterexample. No unrestricted candidate proof text executes. The new small library requires no CaDiCaL. Full `Std.Tactic.BVDecide` remains unverified.

TDD: source-generation regression reproduced the missing extended route; eight generated-source assertions and twelve native/gate tests pass. Four prior core positive cases, new multiplication identity/zero/commutativity/distributivity and bitwise identity/cancellation cases, negative cases, source binding and mandatory Lean gate replay tested. The separate production pointwise `proof_kernel.check_lean` returned a checked `bitvec-lemmas` report for multiplication by one. Total 32 native/source tests passed initially; full regression on independent packaged runtime: 376 passed. See [execution record](verification-v364.txt).

## Runtime and reproducibility

Previously built Lean 4.36.0-pre stage0 compiler reused. Native `lean --deps` identified the 173-module transitive closure of `Init.Data.BitVec.Lemmas`. Using the pinned source and existing cache, actual `lean -j 1 -DwarningAsError=true -Dinterpreter.prefer_native=false -o ...` build completed all 173 modules, exit 0. Two additional upstream lemmas smoke tests (distributivity and mixed bitwise operations) passed with explicit bitvector literal notation. The smaller deployment runtime instead uses the 89-module dependency closure of the generated proof (no full BitVec.Lemmas dependency), checks its SHA manifest and executes separately with its own LEAN_PATH. Native platform Linux x86_64, system ABI dependencies as documented previously. Not an Android compiler or full Lean release.

- [Portable 89-module runtime](https://drive.google.com/file/d/1XsYiRzLZB_WbVPL9-FAxVNcaet5bNh12/view), 84,042,844 bytes, SHA-256 `8a0c1d462699cd5a51d9486664eb82768c5b77f3f5ce6ab6404ee373c2c3d925`; [checksum](https://drive.google.com/file/d/1FdtfGuEUBiEmVuSDPmuVJIBGuUKVm1ia/view).
- [297-module build cache](https://drive.google.com/file/d/1xdUPI5V35c_DLjzbP9qiL0QITW1S5wr7/view), 55,765,434 bytes, SHA-256 `c5e8362d308aa049b5dd09bd42577f82fd781c7c7d4832ef22b9e34a4df2d0fc`; [checksum](https://drive.google.com/file/d/128qqpFTXtYObpI-FmeDhPv-2nBLUkDCp/view). Includes complete 173-module verified BitVec.Lemmas closure plus previously compiled partial Init/Std modules. Other cache modules not accepted as full Std runtime. The cache is not a standalone compiler.

After verifying detached checksums, extract runtime and verify internal SHA256SUMS. From the project root:

```sh
export PATH="/path/to/omega-lean-bitvec-4.36.0-pre/bin:$PATH"
OMEGA_LEAN_CORE_NATIVE=1 OMEGA_LEAN_BITVEC_NATIVE=1 python -m pytest -q tests/test_omega*.py
```

For the independent upstream smoke check, extract the cache, verify its SHA256SUMS and use the actual `bin/lean-real` from the runtime, not the wrapper (wrapper fixes its own paths):

```sh
LEAN_PATH=/path/to/omega-lean-stage0-cache/oleans /path/to/omega-lean-bitvec-4.36.0-pre/bin/lean-real -t 0 -DwarningAsError=true /path/to/omega-lean-stage0-cache/Smoke.lean
```

## Residual acceptance

PASS: native kernel checks of the tested equations spanning all six operators and integration/replay; portable runtime and compiled upstream BitVec.Lemmas closure. Infrastructure-model properties previously accepted under v2.3 §5 remain accepted. OPEN: full decision procedure and Isabelle native compatibility, general BFT liveness and novel-primitive synthesis, large pretrained model loader/training, unresolved dependency metadata. GATE-09 is not unconditionally closed. No new full upstream regression in this release, no deployment claim.
