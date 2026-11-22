# OMEGA-X — finite reward hacking guard (2026-11-22)

## Evidence and limits

Academic input: Skalse, Howe, Krasheninnikov, Krueger, *Defining and Characterizing Reward Hacking*, arXiv:2209.13085v2 (2025-03-05), Definition 1, Sections 5–6. This source shows why unhackability depends on the policy set and environment and why universal safety cannot be inferred from a finite test.

The new module omega_x_evolution/reward_order.py compares every unordered pair of 2–128 operator-supplied policies. A strict inversion is a pair ranked in opposite directions by proxy score and reference score. Equality is allowed by the paper's mathematical definition. The module uses decimal strings without float rounding, an externally anchored SHA-256 of the reference table, a capped list of witnesses, and explicit rejection of missing, extra, malformed and non-finite input. Constant rewards are reported INCONCLUSIVE rather than accepted as useful evidence.

The scores and reference benchmark are caller supplied; no independent scoring, signer verification, nor deployment are performed here. Every output has human_values_alignment_proved=false, reference_attested=false, release_authorized=false. This is a narrow research guard and does not replace existing RSI, constitutional drift, formal equivalence, or Stage 3 performance checks. It is not yet wired to a mandatory acceptance gate.

## Other submitted PDFs

| Source | Actual content | Suitable use | Status |
|---|---|---|---|
| E2-eval.PDF | train/validation/test, cross-validation, bootstrap, confidence intervals | unbiased Stage 3/RSI evaluation | reference only |
| W1.PDF | foundations of learning and generalization | bounded optimization claims | reference only |
| W2.PDF | confusion matrix, classification error, ROC and validation | safety evaluation by error type | reference only |
| W3.PDF | decision trees, splitting and pruning | interpretable router baseline | reference only |
| W4.PDF | historical neural network theory | background, not proof of current performance | background |
| W5.PDF | feature selection, PCA/SVD, discretization | MAP-Elites descriptor ablations | reference only |
| W6.PDF | Boolean reducts, rules, prime implicants | minimal counterexamples and policy constraints | reference only |
| W7.PDF | PAC learning and VC dimension | stated sample-size and generalization assumptions | reference only |
| W9.PDF | clustering, distance metrics, grouping | phenotypic diversity checks | reference only |
| 2209.13085v2.PDF | formal reward hacking conditions | implemented bounded pairwise check | local tested |

## Actual verification

- RED: unittest import failed with ModuleNotFoundError before code was written.
- GREEN: 17/17 unittest tests PASS on a locally isolated source tree.
- coverage.py: 100% statement coverage of this one new 72-statement module, NOT of the repository.
- compileall: PASS locally.
- Production integration, complete repository regression, external reward attestation and hardware deployment: NOT TESTED.
- Maintainer GATE-09 remains historically unchanged; no new global GATE-09 PASS.
