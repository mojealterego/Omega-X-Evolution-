# Native Lean BVDecide checkpoint increment — 488 → 500

Base main: `322c33ec73804b0bd83847803571d2f040c3f4b5`; upstream Lean source pin: `611c117bfaf7b7ae1cfcf246ce6fba31e8f509e9`. Existing v31 obligation, under [v3.0](EXECUTION_DIRECTIVE_V3.md). No external audit, external certification, new stage, paid CI or other branch.

## Executed results (NATIVE)

Restored the five verified archives (portable compiler, stage0 cache, native LRAT tools, 470 checkpoint and 488 increment) from Drive; reused existing binaries. Direct raw.githubusercontent.com retrieval failed DNS resolution (curl exit 6); retrieved only required pinned source blobs via GitHub connector and checked each Git blob SHA-1 locally. No dependency on YepCode. 92 new source files, 808 total, 12 new compiled modules, 500 delta modules total excluding 297 baseline modules. No compiler invocation failed in the recorded resume runs; the final aggregate run remains nonzero because 151 source modules are missing and 308 known nodes are blocked. Std.Tactic.BVDecide and Std.Tactic.BVDecide.LRAT.Checker PASS (checkpoint verification), Lean.Elab.Tactic.BVDecide BLOCKED (transitive imports).

New modules: Init.Data.String.Extra, Lean.Data.LBool, Lean.Data.OpenDecl, Lean.Data.PersistentArray, Lean.ImportingFlag, Lean.InternalExceptionId, Lean.LoadDynlib, Lean.PrivateName, Lean.Runtime, Lean.Util.MonadBacktrack, Lean.Util.Path, Lean.Util.PtrSet.

TEST-BV-500-01: resume build (Linux x86_64, native Lean 4.36.0-pre). From delta root:
```sh
python resume_build.py --runtime ../omega-lean-bitvec-4.36.0-pre --cache ../omega-lean-stage0-cache --solver ../omega-lrat-native-3.1.0/bin --jobs 5 --threads 1 --timeout 120 Lean.Elab.Tactic.BVDecide Std.Tactic.BVDecide Std.Tactic.BVDecide.LRAT.Checker
```
Per-module commands, exit codes, pinned source hashes and olean hashes retained in archive. Existing compiled markers are not overwritten. The earlier resume logs use the original run's thread/job configuration as recorded per module.

TEST-BV-500-02: `bash run-reflect.sh` in an isolated writable directory with LEAN pointing to recovered lean-real, LEAN_PATH to merged delta/oleans, CADICAL and LRAT_CHECKER to recovered native binaries. Exit 0; eight-bit widths were not substituted for u16. Native bitblast generated DIMACS for seven formulas; six independent Isabelle-exported LRAT checker runs passed; malformed certificates and wrong-formula replays rejected for all six tested identities. Log SHA-256 `92d9b9f4170ebfbba8fbaf68e7166e47aa55df51f026ca0584b9ac53ddcc36c6`. The six reflection theorems use compiler-backed native_decide axioms (explicitly reported), not kernel-only or full Isabelle theory proof.

TEST-BV-500-03: checked all 185 new increment manifest entries and reconstructed base 470 + increment 488 + increment 500 in a fresh directory, verified all 500 olean markers, 808 pinned source rows; no change to old source identities. PASS. Uploaded archive then retrieved and checked SHA-256 locally.

## Artifacts and replay

[Increment 488→500](https://drive.google.com/file/d/1l44OVExErKOhPhjY6hOVzT8Le2b9n2MH/view), 1,001,191 bytes, SHA-256 `915edd0e02cce87a4c0fba23aa92873463687fc2d80c19bbcf63f4e61c13c2de`; [detached checksum](https://drive.google.com/file/d/1L07B0EZS-spS0BqpbNXf2q9CXORKSXIv/view). Not standalone. Reconstruct and verify [470→488](NATIVE_STD_BVDECIDE_488.md) first. Extract this increment separately, verify SHA256SUMS, verify old source blob identities unchanged, copy increment files except INCREMENT.json/SHA256SUMS, allow replacement only for source-manifest.json, delta/resume-missing.json and delta/resume-result.json; verify each new olean against its marker. Preserve both earlier archives.

GATE-09 remains BLOCKED by real outstanding functional/formal obligations; no physical infrastructure or third-party audit requirement. No new full upstream suite run or native Isabelle theory build is claimed in this increment.
