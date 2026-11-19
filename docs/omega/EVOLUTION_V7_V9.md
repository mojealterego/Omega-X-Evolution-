# OMEGA-X Evolution — v7–v9

Development snapshot 0.9.0.dev1. The bounded numeric expression engine and the checkpoint contract are unchanged. The new modules are explicit, offline research paths; no automatic deployment or external API calls.

## v7 — formal verification

`omega_x_evolution.formal` proves nine families of IEEE-754 binary64 identities by checking the negation of each in Z3 (UNSAT means no counterexample for finite operands). SMT equality distinguishes signed zero. The fixed rules are positive sign, double negative, multiply/divide by ±1, repeated absolute value, absolute value of a negative, and identical min/max. Every rule preserves finite values and magnitude (the engine enforces |value| ≤ 10^12). The operands that are removed are either valid constants or deterministic duplicate subexpressions. Under the existing pure, ordered, fail-fast interpreter, removing these preserves the first arithmetic/domain failure: the original first occurrence remains and no other failing operand is reordered. These semantic arguments and the compiler/interpreter correspondence are part of the trusted base, not independently machine-verified Python semantics.

An independent term normalizer checks that source and target have the same form using only those rules. A separate structural checker reconstructs the first-occurrence postorder DAG with bit-exact constants and checks every instruction and static operation count. This establishes the bounded rewrite contract, not equivalence of arbitrary expressions or machine code. `verified_optimize` fails closed if a rule is unproved, the IR differs, or the solver fails. The solver runs in a child process with a 35 s outer timeout, fixed queries and a 3 s per-query timeout. A system `libz3` shared library is required for certified optimization, but not for existing offline v4–v6 modes. On Debian/Ubuntu install `libz3-4`; on other systems configure the normal system library loader. The v9 team's simplify operator explicitly uses the certified path. No implicit changes to existing v6 behavior.

```sh
python -m omega_x_evolution.formal --rules
python -m omega_x_evolution.formal -- '-(-(x*1))/1'
```

Evidence: [rules](formal-rules-v7.json) and [example certificate](formal-certificate-v7.json). The certificate is an inspectable result, not a signature or a portable proof object; rerun the checker against the source. Z3 and the independent normal-form checker are trusted. No verification of arbitrary workflow Python or unrestricted LLM output is claimed.

## v8 — knowledge distillation

`omega_x_evolution.knowledge` generates a teacher distribution over five existing operators by applying each once to a bounded parent expression and scoring against the fixed training Cascade. The labels use softmax temperature 0.08. The student is a categorical conditional probability model: role (fast/deep) × structural complexity (two bins), four rows with Laplace smoothing. It learns by aggregating teacher soft labels; inference chooses one operator. It is not neural-weight distillation or an LLM fine-tune. Canonical JSON carries benchmark, operator ordering, seed provenance, probabilities and training-record digest. Loading validates shape, ranges, schema and digests' syntax (no authenticity claim). Train and validation seeds are disjoint; neither training nor teacher labels access the engine's heldout dataset. Validation measures the teacher's best single-proposal score versus student's chosen proposal on separate seeds; both use the same proposal seed per record. Validation choices are scored from the teacher's precomputed per-operator table. Logical student calls are one per record vs five for the teacher, excluding training and validation setup; not a measured speedup. The ratio operator is task-specific, so results do not generalize to arbitrary programs.

```sh
python -m omega_x_evolution.knowledge --records-per-seed 12
```

Evidence: [distillation benchmark](distillation-benchmark-v8.json). The fitted model can be read using `Student.from_json`; `student.proposal()` is compatible with the original engine's Proposal contract. Use the returned model only after validating on your own untouched tasks. Model output is never executed as unrestricted code.

## v9 — multilevel coevolution

Three levels: (1) expression artifacts and adaptive genomes within the existing Pareto island engine; (2) distinct bounded fast/deep operator workflows per team, selected on training outcomes and recombined by role; (3) multiple team demes with deterministic ring migration of elites, crossover and mutation. A distilled student seeds each deme. Candidate teams use the unmodified inner evaluator, and certified optimization when simplify is selected. The outer population shares a cache of training fitness; deme elites and migration use only training observations. A single selected challenger is compared with the original simulated proposer on untouched validation seeds using the existing v5 fixed promotion function. Failure leaves the baseline policy unchanged. No automatic promotion to deployed code. The outer search enforces a bound on candidate evaluations (100,000 including teacher labels), upper limit on inner synthetic credits, and finite demes/rounds/population. Operator application count per inner proposal remains bounded by the v5 workflow limit. Outer search is replayable from configuration but does not currently persist its own resumable checkpoint. Inner checkpoint format remains untouched; custom team proposals are not supported by existing offline checkpoint mode. No physical multi-host outer scheduler or indefinite self-modification.

```sh
python -m omega_x_evolution.multilevel --rounds 3 --demes 3 --population 4 --generations 2
```

Evidence: [team benchmark](multilevel-benchmark-v9.json). This single simulation uses separate train/validation seeds and the fixed numerical objective, not statistically representative comparisons against external systems. The next release v10 concerns controlled recursive promotion, v11 comparable benchmarks, and v12 scientific discovery.

## Verification

`python -m pytest -q tests/test_omega*.py` and `python scripts/verify_hardening.py`. See [verification record](verification-v9.txt). No GitHub Actions enabled. No production deployment or paid inference performed.
