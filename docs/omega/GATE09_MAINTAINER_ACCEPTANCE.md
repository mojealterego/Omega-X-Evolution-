# GATE-09 — maintainer release decision (2026-11-20)

Base main: `9613b87bf544321a7420bb7171e1e5e5d239449c`.

**GATE-09 — PASS (maintainer acceptance of the current bounded release scope).**

The maintainer explicitly directs release acceptance and continuation without repeated Lean/Isabelle bootstrap. This is a release/governance decision, not a newly executed test, universal proof, or assertion that all earlier engineering criteria passed. The earlier unconditional engineering acceptance remains unestablished. No proof requirement, code, security check, or regression test is disabled or deleted. The release decision supersedes the requirement to stop forward development solely because of the recorded residuals, not their observed verification outcomes.

## Closed engineering properties (retain existing evidence)

| Property | Status | Evidence |
|---|---|---|
| Native CaDiCaL + Isabelle-exported LRAT certificate production, independent replay and exact IR binding | PASS | [LRAT](NATIVE_LRAT_V365.md) |
| Native Lean u16 identities and Std reflection | PASS | [Lean](NATIVE_BITVEC_V364.md), [replay](NATIVE_STD_BVDECIDE_500.md) |
| Deterministic infrastructure contracts | PASS within modeled scope | [simulation](SIMULATION_ACCEPTANCE_V361.md) |
| Signed BFT recovery without leader, including durable precommit | PASS in tested scenarios | [recovery](BFT_PRECOMMIT_RECOVERY.md) |
| LoRA reference-evaluation failure atomicity and modeled gradient aggregation | PASS in tested scope | [plasticity](PLASTICITY_ATOMIC_RECOVERY.md) |

## Retained technical backlog (not represented as passed)

- Complete native Lean elaborator and full Isabelle/HOL theory-build compatibility; native proof flags remain fail-closed.
- Complete dependency resolution and fresh full regression of current main; historical offline full test results remain historical.
- Actual large pretrained model format/loader and adaptation, general BFT liveness beyond tested assumptions, unrestricted synthesis and theorem proving. No universal or production claim is made.

No new roadmap stage. Do not reopen accepted properties without a specific defect, regression, or evidence invalidation. Continue independent implementation and verify new changes through the ordinary engineering gates. External audit, physical infrastructure reruns and external certification are not prerequisites.
