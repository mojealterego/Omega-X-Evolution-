# Native Lean BVDecide checkpoint increment — 470 → 488

Base main 13aeae2fa5bd5c2b9049ef63d8dfaefd218ef327; upstream Lean source ref 611c117bfaf7b7ae1cfcf246ce6fba31e8f509e9. Acceptance follows [v3.0](EXECUTION_DIRECTIVE_V3.md). No new stage or gate. Existing preserved compiler/cache/solver archives were verified, re-used and not re-downloaded as a full distribution.

## Executed build

66 additional source files recovered from immutable upstream blobs and locally verified (Git blob SHA-1). 18 additional modules compiled with zero failed compiler invocations across the resume runs; 716 pinned sources and 488 compiled delta modules total, excluding 297 baseline cache modules. Actual transitive scan: 164 missing sources and 228 blocked nodes. Full Lean.Elab.Tactic.BVDecide target NOT complete. Std.Tactic.BVDecide and Std.Tactic.BVDecide.LRAT.Checker targets present and verified by the resume runner. No simulated proof or claim of universal correctness.

From extracted delta root:
```sh
python resume_build.py --runtime ../omega-lean-bitvec-4.36.0-pre --cache ../omega-lean-stage0-cache --solver ../omega-lrat-native-3.1.0/bin --jobs 8 --threads 1 --timeout 120 Lean.Elab.Tactic.BVDecide Std.Tactic.BVDecide Std.Tactic.BVDecide.LRAT.Checker
```

Aggregate command returns nonzero because the elaborator target remains blocked, not because a compiler task failed. Logs, exact commands, per-module source Git SHA, compiled SHA-256 and unresolved dependency list are in the increment. Direct git clone from the isolated local environment failed DNS resolution; pinned GitHub source retrieval and Drive transfer succeeded instead. No fake dependencies.

New compiled modules: Init.Data.Array.QSort, Init.Data.Array.QSort.Basic, Init.Data.Ord.String, Init.Data.Slice, Init.Data.Slice.List, Init.System.CancelToken, Init.System.Promise, Lean.Cadical.Basic, Lean.Cadical.Internal, Lean.CompactedRegion, Lean.Data.LOption, Lean.Data.Name, Lean.Data.NameTrie, Lean.Data.PersistentHashMap, Lean.Data.PersistentHashSet, Lean.Data.PrefixTree, Lean.Elab.ConfigEval.Commands, Lean.Util.ShareCommon.

## TEST-BV-488-01 — verified native replay

Existing run-reflect.sh re-executed in an isolated directory against the restored compiler and native CaDiCaL/Isabelle-exported checker. Six u16 formulas accepted, malformed and wrong-formula certificates rejected; one satisfiable negative formula. Six independent binary LRAT checker runs passed. Reflection theorem axioms explicitly include the compiler-backed native_decide axiom, not a kernel-only proof claim. No sorry/admit inserted. Replay log SHA-256 92d9b9f4170ebfbba8fbaf68e7166e47aa55df51f026ca0584b9ac53ddcc36c6; identical to prior recorded replay. Native full Isabelle theory and Lean elaborator are not established by this result.

## TEST-BV-488-02 — reconstruction

Increment (1,694,141 bytes): [archive](https://drive.google.com/file/d/1N7GXjYbwtEBVVqJBq5dg9_Kt-xB3gRpv/view), [checksum](https://drive.google.com/file/d/1v1JcYfngKEizQgCy0GtIaYoVXGrlAyRQ/view). SHA-256 5f94f506639399e0927b0ef65006c8ba3c6656f42449f4ba9565cc0118f1a28b. Remote bytes downloaded and compared with local archive, identical SHA-256. The incremental archive avoids re-uploading the 109,588,790-byte base checkpoint; it is not standalone.

Reconstruction was tested in a fresh temporary directory: verify base archive SHA-256 78ca516438455beb1316df2f9a3fdbdad486f5845de68eacc606aee8d983a5fd and increment SHA-256, extract separately, verify all 203 increment manifest entries, validate that old source blob identities are unchanged, allow replacement only of source-manifest.json, delta/resume-missing.json and delta/resume-result.json, copy all other non-metadata files without overwriting, verify each of 18 new olean hashes against its marker. Result: 488 delta modules, 716 pinned sources. Preserve the old verified archive. The increment carries INCREMENT.json and SHA256SUMS, both refer to the incremental archive layout. Do not apply it to unrelated checkpoints.

GATE-09 remains BLOCKED by actual remaining functional/formal criteria, not physical infrastructure or audit requirements. This is an increment, not a final acceptance.
