# OMEGA-X Evolution — v10–v12

Development snapshot 0.12.0.dev1. These milestones implement bounded research mechanisms, not unrestricted autonomous self-modification or a claim of scientific breakthroughs. The original numeric engine, worker protocol and inner checkpoint bytes are unchanged.

## v10 — controlled recursive policy improvement

`omega_x_evolution.recursive.improve` runs up to eight iterations. Each iteration generates a bounded population from the incumbent (including the incumbent itself); a task-specific ratio prior is available before the first promotion. A deterministic seed schedule allocates two training and two validation seeds per round, without repeats across rounds. Selection only uses training run outcomes, including their internal holdouts; validation seed results never select the challenger. The fixed v5 promotion gate compares the challenger with the current incumbent on both fresh validation seeds and requires non-regression of fixed score and holdout quality on every seed plus positive aggregate score gain. All nine fixed formal rules must be UNSAT before starting; simplify uses the certified v7 path. A rejection retains the incumbent. The initial incumbent is the original simulated proposer. The policy artifact is not deployed and cannot alter evaluator code, tool permissions or budgets. No indefinite loop. The outer run cap is `rounds * (2 * population + 4)` and the upper bound on inner proposal attempts is 100,000. Synthetic credits are not dollars or measured compute. Across-round validation scores use different seeds and cannot establish global monotonicity.

Outer checkpoints reuse the authenticated SQLite store with a distinct schema, fixed runtime digests, Python version and experiment settings. Save occurs at the end of each round; replay restarts a partially completed round. Resume requires the exact original planned round count, config, source bytes, key and interpreter. `--stop-after` is an absolute execution target; no automatic rollback protection against deletion or whole-database replacement. Operator must control storage and key.

```sh
python -m omega_x_evolution.recursive --rounds 4 --population 5 --generations 2
# Optional round checkpoint (create a private 32-byte random key first):
python -m omega_x_evolution.recursive --rounds 4 --checkpoint outer.db --key-file private.key --stop-after 2
python -m omega_x_evolution.recursive --rounds 4 --checkpoint outer.db --key-file private.key --resume
```

The [v10 report](recursive-benchmark-v10.json) includes 54 inner runs against a cap of 56, one promotion, three rejections (including exact score ties). No repeated validation tuning or repository self-write occurs.

## v11 — comparative benchmarks

`omega_x_evolution.benchmarks.compare` evaluates three in-process search strategies on the exact same synthetic datasets and seeds under equal proposal-attempt budgets. Duplicate/invalid proposals consume attempts; unique/valid counts are separately reported. It compares fixed grammar enumeration, random sampling, and bounded elite mutation/crossover. The latter starts from a shared grammar prefix; all use the same interpreter, training objective and one final holdout evaluation. Different strategies may consume different actual compute. Raw per-run records, empirical matches, paired wins/ties/losses, missing values, and descriptive mean RMSE are reported. No claim of statistical significance, external baseline reproduction, measured speedup or superiority to AlphaEvolve, DGM or ShinkaEvolve. The synthetic functions are favorable to the chosen grammar; do not use these results as generalization evidence. Do not tune on these validation fixtures and later label them untouched tests.

```sh
python -m omega_x_evolution.benchmarks --budget 256
```

[Benchmark](comparative-benchmark-v11.json): five tasks × four seeds × three strategies = 60 runs; 256 proposals per run. Enumeration 16/20 exact, random 9/20, evolution 16/20. Evolution beats random (8 wins, 12 ties, 0 losses) but loses to enumeration on 2 pairs (18 ties). Mean RMSE enumeration 0.0283754, random 0.142749, evolution 0.0343434. No external systems measured.

## v12 — scientific discovery (bounded symbolic regression)

`omega_x_evolution.discovery` accepts a `Dataset` consisting of disjoint immutable tuples of observations `(x,y,z)`, where x,y∈[0,1] and |z|≤10^12. There are 1–512 records per split; duplicate coordinate pairs are rejected both within and between splits. A bounded grammar of arithmetic and abs generates candidates; existing Expression enforces source size, AST budget and numerical bounds. A finite budget (1–4096 proposals; at most one million training observation evaluations) controls all strategies. Ranking minimizes training RMSE, then operation count, AST size and source text. The holdout is read only after selection. A numerical match means RMSE ≤ 1e-12 on both splits, not a proof of universal equivalence, causation, discovery of a novel law, or uncertainty quantification. Data digest and deterministic rerun verify the report, not the provenance/authenticity of observations. Grammar and two-input domain are limited, and no data collection or lab automation is included.

```sh
python -m omega_x_evolution.discovery --task squares --seed 2026 --budget 128
python -m omega_x_evolution.discovery --dataset observations.json --budget 256
```

Input example (replace values with observations, not a target expression):

```json
{"train":[{"x":0.1,"y":0.2,"z":0.3},{"x":0.3,"y":0.4,"z":0.7}],"holdout":[{"x":0.5,"y":0.2,"z":0.7}]}
```

`verify_report(data, report)` runs the entire experiment again and rejects altered reports. The [example](discovery-example-v12.json) reconstructs `((x*x)+(y*y))` on 32 training/16 holdout observations; first exact fit at attempt 47, both RMSE zero.

## Verification and remaining work

See [verification-v12.txt](verification-v12.txt). The initial twelve-stage roadmap now has a bounded implementation for every stage. The full research goal remains open: independently sourced problems, external comparisons under equal compute, richer scientific domains, actual neural distillation, live multi-host deployment and broader formal guarantees. No production readiness or AGI claim. CI remains inactive.
