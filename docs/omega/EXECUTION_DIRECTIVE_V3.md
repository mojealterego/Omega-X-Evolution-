# Mandatory execution directive v3.0 — engineering acceptance

Effective 2026-11-20, maintainer instruction supersedes conflicting acceptance language in all earlier documents. Branch main only. No new roadmap stages or additional gates.

- External audit, third-party approvals and external certification are **not required**. Internal architecture, code, security and completeness verification remain mandatory. Cryptographic/runtime certificates that are functional requirements are unaffected.
- Physical independent infrastructure is not an acceptance prerequisite. For infrastructure-dependent properties (accelerators, large-scale training resources, cloud/Kubernetes, clusters, BFT transport and replication, services and production environments), deterministic engineering simulation of production code is an accepted substitute. Record model, seed, scenario schedule, invariants, limitations, commands, outcomes, source SHA and artifact checksums. Passed modeled properties are closed, not pending hardware reruns. Native or production performance/deployment claims remain separate.
- Functional, architectural and security requirements remain intact. Simulation cannot substitute for a mathematical theorem outside the modeled finite domain or actual implementation/API compatibility. No sorry/admit/unjustified axioms, fabricated dependencies or test results. Resolve dependencies using preserved runtimes and pinned missing sources.
- Do not reopen passed criteria without regression, defect or invalidated evidence. Do not add research ambitions or physical attestations to the present release as mandatory gates.
- GATE-01 requirements; GATE-02 architecture; GATE-03 implementation; GATE-04 deterministic verification; GATE-05 integration/E2E; GATE-06 security; GATE-07 reliability/recovery; GATE-08 evidence/documentation; GATE-09 final engineering acceptance. Each may use NATIVE, DETERMINISTIC-SIMULATION or HYBRID where appropriate. Record PASS only on evidence, otherwise FAIL/BLOCKED, or justified NOT_APPLICABLE for an individual criterion. GATE-09 PASS requires all applicable preceding gates and mandatory functional obligations accepted.
- Previously accepted modeled properties in SIMULATION_ACCEPTANCE_V361.md and subsequent records retain their PASS. Historical physical-only blockers and external certification requirements are superseded, not silently converted into native/production claims. Upstream dependency compatibility, native formal proof obligations and actual algorithmic defects remain subject to verification. General unbounded mathematical claims cannot be inferred from finite tests.

Execution order: REQUIREMENTS → IMPLEMENT → BUILD → TEST → FIX → RETEST → VERIFY → EVIDENCE → CLOSE → NEXT. Preserve historical evidence. This directive changes acceptance policy, not test outcomes.

Current gate state: GATE-09 not yet PASS at base 5dd9ea7daa80cab85d734c928a7564a1f7a91892. This policy commit is not an implementation or execution claim.


**Current maintainer release decision: GATE-09 — PASS (bounded release acceptance).** See [GATE-09 maintainer decision](GATE09_MAINTAINER_ACCEPTANCE.md). This is an explicit authorization to proceed, not an unconditional engineering PASS or a new test result. Historical technical residuals remain recorded; passed properties are not reopened.
