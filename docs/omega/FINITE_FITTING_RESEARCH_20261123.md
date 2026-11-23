# OMEGA-X research — exact finite Fitting sanity checks (2026-11-23)

**Status:** OPTIONAL RESEARCH; NOT a new evolution/RSA/RSI release gate. No
claim of a universal algebraic proof or certified theorem checking.

## Primary source

Sora Miyashita, *A Fitting criterion for quasi-Gorenstein local rings*,
arXiv:2608.03766v2 (2026-10-27), https://arxiv.org/abs/2608.03766.

For a Noetherian local ring admitting a canonical module, Theorem 1 states

\[ R\text{ quasi-Gorenstein}\quad\Longleftrightarrow\quad
   \operatorname{Fitt}_1^R(\omega_R)\cong \omega_R. \]

The isomorphism sign matters: this is an isomorphism of **R-modules**, not
necessarily literal equality of two chosen ideals. Under Cohen–Macaulayness,
this also characterizes the Gorenstein property. The proof invokes
Hilbert–Burch, endomorphisms of canonical ideals, Serre's (S2),
Auslander–Buchsbaum, and the unmixed quotient. Neither checking an example
nor its finite presentation proves this general theorem.

## Bounded computational interpretation

The module `omega_x_evolution.finite_fitting` constructs exclusively

\[R_{p,d}=\mathbb F_p[x_1,\dots,x_d]/(x_ix_j:1\le i,j\le d)\]

for primes `p` in `{2,3,5,7,11}` and `1 <= d <= 4`. This is a finite,
zero-dimensional, local, Cohen–Macaulay algebra with square-zero maximal
ideal. Its socle has dimension `d`. For this family, the canonical module is
exactly the `F_p`-dual of `R`, with generators dual to `x_i`.

The program builds the relation matrix of the canonical module from the
explicit algebra action, **independently validates** its kernel dimension over
`F_p`, computes all `(d-1)`-minors using exact ring operations, and takes
the exact `F_p`-span of the resulting ideal including products by a ring basis.
For `d=2,p=2`, an additional exhaustive test enumerates all `2^6=64` elements
of `R^2` and verifies that the relation span equals the entire kernel.

| `d` | Dimension of `ω_R` over `F_p` | Dimension of `Fitt_1(ω_R)` | Independent known Gorenstein criterion |
| --- | ---: | ---: | --- |
| 1 | 2 | 2 | yes (`dim socle=1`) |
| 2 | 3 | 2 | no (`dim socle=2`) |
| 3 | 4 | 0 | no (`dim socle=3`) |
| 4 | 5 | 0 | no (`dim socle=4`) |

For `d=1`, both modules are demonstrably free of rank one. For `d>=2`,
different cardinalities/dimensions rule out any isomorphism. This is an
**exact, narrow family of consistency tests**, not an algorithm to recognize
quasi-Gorenstein rings in general.

## Intended architecture and limitations

- No changes to evolution candidate promotion, `proof_kernel`, `runtime`,
  `main`, or historical GATE-09 decisions.
- No assumption that the finitely many examples imply Theorem 1 universally.
- No formal Lean/Coq proof; no Gröbner basis engine; no treatment of general
  Noetherian or positive-dimensional rings.
- The finite-field arithmetic is not constant-time or suitable for
  cryptographic use. Numeric operations are limited to small exact models.
- The tool is an optional **falsification/model-checking auxiliary** that can
  detect mistakes in proposed algebraic identities before trying to develop a
  genuine formal proof.

## Commands

```bash
PYTHONPATH=. python -m pytest -q tests/test_finite_fitting.py
PYTHONPATH=. python -m pytest --cov=omega_x_evolution.finite_fitting --cov-branch --cov-report=term-missing -q tests/test_finite_fitting.py
python -m compileall -q omega_x_evolution/finite_fitting.py tests/test_finite_fitting.py
```

See `FINITE_FITTING_EVIDENCE_20261123.json` for executable test identifiers,
SHA-256, seed policy (deterministic exhaustive model, no RNG), and results.
