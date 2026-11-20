# v34 corrective: failure-atomic adapter retention evaluation

Base main: `17699e8bc3e8e6962c0394d09424f9a0e04fb038`. No branch creation or external infrastructure. The existing v34 obligation, not a new stage.

## Defect and fix
During `Session.fit`, a temporary switch to the initial adapter for retention measurement could erase the active adapter if that measurement raised before optimizer construction. Restore the previous validated snapshot in a `finally` block; preserve the original error, unchanged frozen weights and training authorization. The regression injects an exception at the actual reference inference boundary, while running the real CPU decoder for prior inference. It verifies exact active adapter restoration and unchanged frozen base digest. Existing checkpoints bind source bytes; campaigns created before this change are not silently migrated.

## Executed evidence
Linux x86_64; Python 3.13.5; Torch 2.10.0+cpu; seed 42, one CPU thread. Base source blob `773261fa60f74e884fa00c70d307bb43f622d4f5` matched main. New source SHA-256 `f024f8277c784fa7612f2001f67ff5845d336a223907da3b07a8d0e0ed0f5e37`; test SHA-256 `679b653da23e57277800f387a66a6adbb2658eff62cde2b50377456d75052f57`.

- PLASTICITY-ATOMIC-RED: `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 python -m pytest -q tests/test_omega_plasticity_atomic.py` — exit 1, real state mismatch. Log [RED](plasticity-atomic-red.log), SHA-256 `1e0c00d162b4d4f0c45058b98b8f074cf2924717495a612ee9c5b9356df65f8d`.
- PLASTICITY-ATOMIC-GREEN: `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 python -m pytest -q tests/test_omega_plasticity_atomic.py tests/test_omega_final_gates.py::test_microbatch_gradient_matches_full_batch tests/test_omega_remaining_closure.py::test_transformer_plasticity_real_training_and_recovery tests/test_omega_simulation_acceptance.py::test_distributed_gradient_reference_and_optimizer` — exit 0, 4 passed in 8.16s. Log [GREEN](plasticity-atomic-green.log), SHA-256 `9be3c2ac986fdbebd292553afa95f250e50af9740f08b5460672f03b1307eac0`.
- PLASTICITY-ATOMIC-BUILD: `python -m compileall -q omega_x_evolution tests/test_omega_plasticity_atomic.py` — exit 0.

PASS: failure-atomic reference evaluation, actual small decoder training/recovery, microbatch and modeled gradient collective regressions. No full new upstream run, pretrained large-model execution or unconditional GATE-09 PASS claimed.

## No reopening previously verified formal properties
The maintainer requested no further repeated Lean/Isabelle toolchain bootstrap. Reuse existing [native Lean evidence](NATIVE_BITVEC_V364.md), [native CaDiCaL + Isabelle-exported LRAT certificate checking](NATIVE_LRAT_V365.md), and [Std/BVDecide replay](NATIVE_STD_BVDECIDE_500.md).

| Formal property | Engineering acceptance |
|---|---|
| CaDiCaL 3.1.0 + native Isabelle-exported lrat_isa certificate verification, exact IR binding, fail-closed promotion and solver-free replay | PASS (NATIVE; prior LRAT-GREEN evidence retained) |
| Lean native proof of tested u16 operator identities | PASS (NATIVE; prior proof evidence retained) |
| Generated Isabelle/Lean theorem source contract | PASS (DETERMINISTIC-SIMULATION; prior v36.1 evidence retained) |
| Full Lean elaborator and full Isabelle theory build | Not verified; distinguish from the accepted proof/certificate properties, not a reason to retest those properties. |

This record is not an assertion that a full Isabelle/HOL installation ran, nor an unconditional GATE-09 result. No functional requirement is removed. Continue distinct unresolved application work rather than recompile passed proof modules.
