# Native Lean bootstrap and formal acceptance v36.3

Base main: `a88da57aec2b1bfc832f0b9c48d0515c1096b7f7`. No new roadmap stage, no paid CI or service calls. This patch resolves the unavailable-native-Lean blocker for the verified additive fragment, without treating that fragment as universal proof search.

## Provenance and acquisition

Maintainer repositories inspected read-only: `mojealterego/mathlib4` (v4.36.0-rc2), `batteries` (v4.36.0-rc2), `mathematics_in_lean` (v4.34.0), `NavierStokesAndEuler` (v4.34.0-rc2), `iris-lean`. No existing CI artifacts were available in those forks; none includes an installed Lean compiler. No cross-repository changes were made. The supplied `lean4-4.36.0.zip` includes upstream stage0 generated C; ZIP comment is the release commit `611c117bfaf7b7ae1cfcf246ce6fba31e8f509e9`, SHA-256 `824b0e63474848a1b5e86c80c7375b81d7d8a362e0fe426eb685324f5a733838`. Six source blobs were independently compared to the official GitHub release tag. Lean upstream CI artifact 14231935097 is 1,545,061,276 bytes, above the 536,870,912-byte connector limit. No binary was downloaded from it.

The actual native stage0 executable and shared libraries were compiled offline (2583 generated C module files compiled; `cmake --build ... --target lean -j4`, exit 0). Compiler: Clang 17.0, x86_64 Linux, CMake `STAGE=0`, `USE_GITHASH=OFF`, `USE_MIMALLOC=OFF`, `USE_LAKE=OFF`; local generated `stdlib.make` flags changed from `-O3 -DNDEBUG` to `-O0 -DNDEBUG` for time-bounded bootstrap. System GMP 6.3, OpenSSL 3.5.7, libuv runtime 1.50.0 with locally installed Node libuv headers 1.49.2 and a local pkg-config shim; no arbitrary source of a solver or upstream C++/Lean source modifications. This is a development bootstrap compiler, **not** a full official release distribution. The exact command/configuration and outcomes are in [verification](verification-v363.txt).

Native compiler version: `Lean (version 4.36.0-pre, x86_64-unknown-linux-gnu, Release)`. `lean --deps` calculated the transitive dependency DAG of the proof imports. 50 required modules were compiled from actual upstream `.lean` files, using `-j 1 -DwarningAsError=true -Dinterpreter.prefer_native=false -o ...`, with real imports and no synthetic modules. Packaged only that dependency closure and its `.olean`/IR companions. A separate attempt at all Init + BVDecide dependencies timed out at 242 compiled `.olean` files of 953 discovered; no full Std/CaDiCaL success is claimed.

The selected lemmas in `omega_x_evolution/lean_native.py` are adapted from Lean's Apache-2.0 `Init.Data.Nat.Lemmas`, `Init.Data.BitVec.Bootstrap`, and `Init.Data.BitVec.Lemmas`, with original attribution and upstream redistribution license in the runtime archive. References: [Nat lemmas](https://github.com/leanprover/lean4/blob/v4.36.0/src/Init/Data/Nat/Lemmas.lean), [BitVec bootstrap](https://github.com/leanprover/lean4/blob/v4.36.0/src/Init/Data/BitVec/Bootstrap.lean), [BitVec lemmas](https://github.com/leanprover/lean4/blob/v4.36.0/src/Init/Data/BitVec/Lemmas.lean).

## Native proof contract

`higher_order.check_lean` and `proof_kernel.check_lean` use the common real Lean subprocess adapter. Validated bounded IR is emitted into a fixed theorem, never arbitrary candidate-provided proof code. `core-addsub` uses actual upstream `BitVec.add` and `BitVec.sub` from `Init.Data.BitVec.BasicAux`, proves modular arithmetic helper lemmas and attempts definitional equality or the specified simplification rules. Both function arguments range over `BitVec 16`. The proof checks add/sub cancellation, zero/identity rules, subtraction of an operand from itself, and actual constant folding. A missing/unavailable proof is never accepted. Other operators or unresolved additive theorems use the existing full `Std.Tactic.BVDecide` route; this bundle cannot execute that route. The original simulation source parser only allows the exact new hardened envelope or the precise historic one, not arbitrary commands. `-t 0` kernel import checking, `-DwarningAsError=true`, UTF-8 source, source SHA-256, `debug.skipKernelTC false` on the full route, and one shared timeout budget are enforced. The `core-addsub` route does not use `native_decide`, unaudited proof axioms, or a fake SAT solver. Native reports include backend strategy and version. Report `verify` reconstructs the source and rechecks the required proof.

## Retained offline capability

Runtime: [OMEGA-Lean-Core-4.36.0-pre-linux-x86_64.tar.zst](https://drive.google.com/file/d/1xlGWKpg5raeu6PX2pgHEZlVJ-uTEPTkl/view), 77,927,207 bytes, SHA-256 `cb7d38b181e67443957bc657ad81bb27364dbfeb711706f329580b02247b5664`. [Detached checksum](https://drive.google.com/file/d/17WTZpml_ZbsCuXl8zoT6dWwtuJ4qltG6/view). Contains 261 hashed files plus manifest, 50 Lean modules, independent wrapper and original license. Dynamic system dependencies are documented in LDD.txt; not Android compatible. No external service needed for the supported proofs.

After downloading both artifacts from the existing private backup folder:

```sh
sha256sum -c OMEGA-Lean-Core-4.36.0-pre-linux-x86_64.tar.zst.sha256
tar --zstd -xf OMEGA-Lean-Core-4.36.0-pre-linux-x86_64.tar.zst
(cd omega-lean-core-4.36.0-pre && sha256sum -c SHA256SUMS)
export PATH="$(pwd)/omega-lean-core-4.36.0-pre/bin:$PATH"
lean --version
# Run from OMEGA-X repository (the wrapper supplies its own LEAN_PATH):
python scripts/verify_native_lean.py
OMEGA_LEAN_CORE_NATIVE=1 python -m pytest -q tests/test_omega_native_lean.py
```

Acceptance: four positive native whole-domain functional equations and one false equation rejected; optional native proof requirement checked via the production `higher_order.prove` and `verify` APIs. Explicitly requested native mode fails when the compiler is absent. The runtime was tested in an independent directory without the earlier LEAN_PATH. See raw verification for exact results.

## Remaining gate

PASS — native Lean kernel proof of tested core-addsub equations, generation/report contract, fail-closed behavior and portable local runtime. PASS — original v36.1 deterministic infrastructure contracts remain accepted. BLOCKED — full native `Std.Tactic.BVDecide` / all IR operators and Isabelle runtime (no Isabelle repo found in maintainer search), large pretrained-weight loader and training, general consensus liveness proof and novel primitive synthesis. GATE-09 does not become unconditional PASS. Upstream dependency metadata and live-service limitations from v36.2 remain. No repeated full upstream regression asserted in this version.
