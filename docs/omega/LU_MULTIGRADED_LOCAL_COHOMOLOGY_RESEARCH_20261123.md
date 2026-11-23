# OMEGA-X — bounded multigraded local cohomology research model (arXiv:2609.11219v4)

**Classification:** OPTIONAL_RESEARCH, not a mandatory Roadmap item. **Release authorization:** NOT_GRANTED.

## Source and scope

Dancheng Lu, *Multigraded Local Cohomology Categories: Homological Structure and Functorial Sections*, arXiv:2609.11219v4, 27 October 2026, 34 pages (user-supplied PDF).

The source studies the essential images of

`Phi_i^t(M) = H^i_m(M(-1))`, where `S = k[x_1,...,x_n]`, `m=(x_1,...,x_n)`,
`P_t=[0,t]`, `0 <= i < n`, and `U_{n-i}(t)={a in P_t : |supp(a)| >= n-i}`.

Theorem 4.1 identifies the **non-top** image category with representations supported on `U_{n-i}(t)`, a Serre subcategory of the finite-box representation category. Proposition 4.4 gives its global dimension (for a nonzero image), and Proposition 5.7 gives exact integer formulas for Bass numbers of specific projective and injective indecomposables. Proposition 5.3 derives attached primes from **given minimal projective-cover multiplicities**. Corollary 4.8 provides a canonical support-rank filtration.

The top-degree image `H_n(t)` is described separately by second cosyzygies; it is extension-closed, **not abelian** for nonzero `t`. Neither the module API nor its tests accept `i=n`. The paper proves existence of certain functorial sections; this research model does **not** construct those sections.

## Implemented bounded contracts

- `FiniteBox(bounds)`: 1–8 variables; at most 4096 vertices, nonnegative bounded multidegrees.
- `upper_vertices(i)` and `is_non_top_image(i, dimensions)`: image eligibility of a **valid** finite-box representation from support alone; no computation of local cohomology itself.
- `global_dimension(i)`: exact formula; returns `None` for a zero image category, not an invented negative dimension.
- `support_filtration(i, dimensions)`: support levels for the filtration; does not construct/validate nontrivial linear maps.
- `attached_primes_from_projective_cover(i, multiplicities)`: exact coordinate prime sets from *caller-supplied, verified* cover multiplicities; never derives cover multiplicities from a dimension vector.
- `projective_bass_numbers(a)` and `injective_bass_numbers(i, a)`: integer binomial formulas; no floating-point approximations.
- Strict validation: reject negative, boolean, out-of-box, oversized, wrong-degree, and otherwise malformed inputs.

Inputs are ordinary Python data, not executable expressions. There are no network accesses, code execution, filesystem writes or automatic RSI promotion in this module.

## Verification and limits

`PYTHONPATH=. python -m pytest -q tests/test_finite_box_local_cohomology.py tests/test_finite_fitting.py`

The finite-box test suite includes 300 seeded independent checks of the global-dimension formula against exhaustive enumeration, crosschecks for the Bass formulas, deterministic support filtration, edge cases and resource limits. The previous independently developed Fitting-ideal module is included only for **focused local regression**. Both modules use only exact finite arithmetic.

**Not claimed:** independent verification of Lu's categorical equivalence, existence/full faithfulness of functorial sections, any theorem about arbitrary Noetherian rings, the full OMEGA-X test suite, hardware acceleration, a Lean/Coq proof, or production integration. No Roadmap/GATE-09 status should change based on this model alone.

The analogy between a multigraded poset and an OMEGA-X state DAG is useful for researching support filtration and provenance; it does **not** make general agent reasoning graphs equivalent to the source's category of multigraded `S`-modules.
