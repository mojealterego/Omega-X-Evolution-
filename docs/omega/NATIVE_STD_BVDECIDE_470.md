# v31 corrective continuation — native Std/BVDecide

Base main: `f109656055e3144f9d2aa3a8a8a109552492bfda`. Lean upstream source pin: `611c117bfaf7b7ae1cfcf246ce6fba31e8f509e9`. Existing v31 obligation, not a new roadmap stage. No paid CI, new branches, or full Lean distribution download.

## Build and provenance

Environment: Linux x86_64 6.18.57, Python 3.13.5, Lean 4.36.0-pre, CaDiCaL 3.1.0, Isabelle-exported native lrat_isa. Reused verified runtime, stage0 checkpoint, LRAT tools and prior 342-module delta. Compiled 128 additional modules with source Git blob verification. Zero failed module compilations; aggregate run nonzero because elaborator dependency closure is incomplete. 172 blocked and 168 missing source modules at the completed build scan. Eight of the missing source blobs subsequently recovered and verified; next scan can discover further transitive imports. 650 upstream source files and 470 compiled delta modules preserved. No claim that elaborator is compiled.

Command from extracted delta root:

    python3 resume_build.py --runtime ../omega-lean-bitvec-4.36.0-pre --cache ../omega-lean-stage0-cache --solver ../omega-lrat-native-3.1.0/bin --jobs 4 --threads 1 --timeout 900 Std.Tactic.BVDecide Lean.Elab.Tactic.BVDecide Std.Tactic.BVDecide.LRAT.Checker

Targets: Std.Tactic.BVDecide PASS; Std.Tactic.BVDecide.LRAT.Parser PASS; Std.Tactic.BVDecide.LRAT.Checker PASS; Lean.Elab.Tactic.BVDecide BLOCKED.

## Native proof evidence

TEST-BV-470-01: CheckerSmoke.lean (exit 0), text/binary LRAT accepted, satisfiable CNF, incomplete hints, invalid clause ID and empty proof rejected. Soundness theorem uses native_decide. TEST-BV-470-02: run-reflect.sh (exit 0). Lean-generated native AIG/CNF for six u16 identities (add commutativity, add/sub inverse, multiplication by 2, xor cancellation, and/or commutativity) and one satisfiable negative case. CaDiCaL produced text and binary LRAT, lrat_isa independently verified binary LRAT for each identity; SAT negative exit 10. Lean reflection accepted valid certs, rejected invalid text and each certificate replayed against the wrong satisfiable formula. Six compiled theorems BVLogicalExpr.Unsat through Reflect.unsat_of_verifyBVExpr_eq_true; printed axioms show propext, Classical.choice, Quot.sound and compiler-backed native_decide axiom (no sorryAx). This is compiled reflection with trusted compiler, not a kernel-only reduction or full elaborator tactic proof. No general proof of arbitrary programs, full Isabelle theory build or full upstream regression claim.

Test sources and execution logs: [tests/lean/bvdecide](../../tests/lean/bvdecide/). Run in a writable isolated directory with absolute LEAN, LEAN_PATH (merged delta/oleans), CADICAL, LRAT_CHECKER paths. Execute `bash run-reflect.sh`. For CheckerSmoke replay, generate contradiction.cnf with DIMACS clauses 1 and -1, then run CaDiCaL with --seed=0 --plain --lrat --no-binary to false.lrat and --binary to true.lrat (exit 20); run `"$LEAN" -t 0 -DwarningAsError=true -Dinterpreter.prefer_native=false --run CheckerSmoke.lean`. Exact fixtures and command logs preserved in delta.

SHA-256:
- ReflectSmoke.lean: 6e86f784a0579c6b86a89414b45607ab222218cbb09770dd501e236fcb446d49
- run-reflect.sh: 175c811b297e073418e877e60082b79e31be080c3f9645278e4da1a4cd7d09e0
- generate-theorems.py: 0de543ff623d54b33cbd1930522ad5e4df48ee1cb8a21a370a609f1b2d2d4f7f
- reflect-final.log: 92d9b9f4170ebfbba8fbaf68e7166e47aa55df51f026ca0584b9ac53ddcc36c6
- CheckerSmoke.lean: a3b36c1911b29bd75f7b92cbf685b228bfdfe49bc6a420248974dee702f05d5c
- checker-smoke.log: d14577a150ca4cf7db2c78f06981f8d8110fd60271d607d3f989a702b5f6d885

## Preserved checkpoint

OMEGA-Lean-BVDecide-DELTA-470.tar.zst — 109588790 bytes, SHA-256 78ca516438455beb1316df2f9a3fdbdad486f5845de68eacc606aee8d983a5fd. Drive split due to upload limit: [part00](https://drive.google.com/file/d/1ZyOepb4sjm5-1z3DSPkCdnhL9XI5n1YR/view), [part01](https://drive.google.com/file/d/1oowqS1jxxqSL8uuDyLw6H_ikA3em38e1/view), [parts SHA256](https://drive.google.com/file/d/1PtX3PKK_uMCjCgkQdgPWL5V11CyfAUEO/view), [archive SHA256](https://drive.google.com/file/d/1_277JB25AFSQhqZnaXmyJCgIIWS8USUx/view). Local parts concatenation verified against archive checksum. Download both parts, verify parts SHA256, concatenate in numerical order, verify full SHA256, extract and verify inner SHA256SUMS; reuse three baseline packages identified in CHECKPOINT.json. All build logs and proof artifacts included. Upload success confirmed by connector; remote bytes not independently rehashed in this record.

GATE-09 remains BLOCKED; no new stage. Native Std proof pipeline closes the tested scoped property, not full elaborator integration. Continue pinned source recovery exclusively for actual unresolved imports. Native Isabelle theory build, other previously registered residual gates, and full upstream test suite remain unaccepted.
