# ONTOS L11 v68 — SI units and conditional Landauer accounting

**Date:** 2026-11-21. **Target:** `main`. **Acceptance mode:** NATIVE Python + deterministic local numerical tests (not external calorimetry).

## Scope

`omega_x_evolution/ontos_v68_units.py` is a real, importable, pure Python implementation of the bounded v68 contract. It deliberately distinguishes:

1. Information measured in **bits** and **nats** (`1 bit = ln(2) nats`).
2. Declared **irreversibly erased bits**, which are not FLOPs or the v53 estimated work units.
3. The conditional thermodynamic lower bound `E_Landauer >= k_B * T * ln(2) * erased_bits`, with exact SI `k_B=1.380649e-23 J/K`, `T>0 K`.
4. Caller-supplied **core** and **wall-plug** energy scenarios in joules, not measurements.
5. Per-operation energy only with positive operation count and known wall energy; wall power remains **UNKNOWN** without a time series.

`ThermodynamicEpisode` validates bounded inputs and never invents erasures. `EnergyAggregate` sums episodes, propagates missing values, enforces count and energy bounds, and rejects invalid/mutated records on use. Unknown physical measurements are not converted to zero or to a fabricated PASS. No mutation, resource scheduling, hardware I/O, or release authorization is introduced. This is compatible by construction with `ontos_v53_accounting.py` (unit estimates) and `ontos_v57_causal_metrics.py` (information in bits); the models are **not** silently merged.

## Tests and evidence

- `V68-RED-01` / `V68-RED-02`: local RED initially reproduced the missing module and a genuine `OverflowError` for an enormous input integer during `math.isfinite`; fixed with bounded input comparison before conversion.
- `V68-GREEN`: `PYTHONPATH=. python -m pytest -q --strict-markers tests/test_ontos_v68_units.py` → **43 passed in 0.08s**, exit 0; run in isolated file-level workspace, Linux x86_64, Python 3.13.5, pytest 9.0.2. Test IDs are the `test_v68_*` names plus pytest parameter IDs.
- `V68-COMPILE`: `python -m compileall -q omega_x_evolution/ontos_v68_units.py tests/test_ontos_v68_units.py` → exit 0.
- Seed 68 randomized monotonicity/scale checks; boundary cases include NaN/Inf/bools, huge integers, T=0 K, missing erasures, missing wall joules, zero operations, and core energy exceeding wall energy.
- Production source SHA-256: `d0cf95ba99c75176f1ed886569b6d72b1110133854eefaf82c374737cc843f1f`.
- Test file SHA-256: `74a0148d565d9cf7d9faa0abfd3d32b018e84bdaffd1831813b51f14f25b8bb7`.
- This is a focused regression, **not** a freshly run full repository test suite, a hardware energy benchmark, or production verification.

## Gate decision

**v68 finite SI model: PASS** for native implementation and focused tests. **L11 v68–v71 / v83 / v85 as a whole: OPEN**, with v69 six-substrate wall-power models, v70 endurance distributions, v71 Pareto/sensitivity comparison, v83 physical-boundary accounting and v85 event-driven energy accounting awaiting independent work. Real calorimetry, ADC/DAC, cooling and wearout are not inferred from this model.

Historical release-scoped GATE-09 remains unchanged; this is **not** a full ONTOS L11 GATE-09.
