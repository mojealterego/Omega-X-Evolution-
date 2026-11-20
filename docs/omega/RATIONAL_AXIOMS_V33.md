# v33 — autonomous conditional rational identity discovery

Base main `68e04ca2b0aaa4c751341f79015d0b6bc72028ba`. Extends existing exact polynomial and modular theorem generation. No new roadmap stage.

## Contract and proof

Generate a bounded grammar of nonconstant quotients of polynomials with exact rational coefficients in three variables. The proposal signatures are only heuristics for selecting candidates; they are not evidence. Check `a/b = c/d` on the common domain `b != 0 and d != 0`. A degree-determining product grid establishes whether `a*d-c*b` is zero as a polynomial; independently expand and multiply sparse exact coefficient maps before accepting a proof. A grid for `b*d` supplies a nonempty-domain witness. A pole is never an admissible counterexample. If the cross product differs only at a sampled pole, the larger determining grid of `(a*d-c*b)*b*d` locates a valid counterexample, or yields UNKNOWN if the configured bound exceeds 4096 points. Empty domains never yield PASS. Degree-bound correctness follows from the repeated univariate root bound over Q/R. This is mathematical identity checking on the admitted grammar, not empirical observation or a general proof assistant.

Strict AST and exact type snapshots, bounded decoding, exact Fraction coordinates, explicit domain report, source binding and replay. Reports with modified proof digest, domain witness or denominator are rejected. Publication is one authenticated tenant-local SQLite transaction via GraphMemory, with deterministic node IDs and idempotent replay. The existing `omega-x-axioms --rational` CLI selects the new engine; old modes retain their defaults and behavior. Quotient identities are stored as scoped evidence, not as axioms valid outside their domains.

## Executed evidence (NATIVE)

Linux x86_64 6.18.57; Python 3.13.5; pytest 9.0.2. Commands run with `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1` for regression.

- V33-RED `python -m pytest -q tests/test_omega_rational_axioms.py`: exit 1, 6 feature tests fail before implementation. [log](v33-rational-red.log) SHA-256 `9ff5928973ada6bb42c2d227d5628d76122b0bd68d8015e5e2a7b139558597be`.
- V33-GREEN `python -m pytest -q tests/test_omega_rational_axioms.py tests/test_omega_v35.py::test_axioms_discovery_and_replay tests/test_omega_v35.py::test_counterexample_and_unknown tests/test_omega_v35.py::test_finite_algebra_exhaustive tests/test_omega_v35.py::test_orchestration_real_execution_and_idempotent tests/test_omega_remaining_closure.py::test_infinite_domain_theorem_synthesis_and_forgery tests/test_omega_remaining_closure.py::test_inverse_square_scientific_discovery`: 14 passed in 2.47s, exit 0. [log](v33-rational-green.log) SHA-256 `4cf36511e9cebed430f74b6b774de0f935e026ea060b968b269695329ac5c06c`.
- V33-BUILD `python -m compileall -q omega_x_evolution/rational_axioms.py omega_x_evolution/axioms.py tests/test_omega_rational_axioms.py`: exit 0.
- V33-DISCOVER: seed 42, 64 proposals, 264 candidate quotients, 48 independently accepted identities, 16 refuted, 0 unknown or invalid-domain in this run. [complete report](v33-rational-discovery.json) SHA-256 `99167b61dea1a82b09e6147b246598ccea9cdcbbd8177ffbab4f423039d74dd3`. `verify_discovery` returned true. Includes conditional identities such as `2/y=(z+z)/(y*z)` only where both denominators are nonzero. Tests cover zero denominators, non-pole witnesses, exact fractional input, multiple variables, forged ASTs, degree cap, report tampering and atomic/idempotent graph publication. Seed/budget boundary tests pass.

| Source | SHA-256 | Git blob |
|---|---|---|
| `omega_x_evolution/rational_axioms.py` | `0d8cfc05b81223bbd7e40b5b8f08f4daa1a25038f9b57de0e84d00867cc81324` | `65243e31d639d3539b79e98230879f35b4571ece` |
| `omega_x_evolution/axioms.py` | `3dd7a9f85c4bc0360f259a854ba909fbc884d0f5d6af57103293f3431c922c62` | `7ca4aa14e2a7dec178376851568fcd715b4bd327` |
| `tests/test_omega_rational_axioms.py` | `77fa872e3ac43d5595b5ed22fc7d890ee983a30debb0eca59416b740e60ee98d` | `cc68c0368904f1033f61210aaea8584bcced576d` |

PASS in the bounded common-domain rational identity grammar. Unrestricted axiomatic discovery, arbitrary nested division and general scientific discovery remain research goals. Full repository regression not run. GATE-09 owner decision stays closed.
