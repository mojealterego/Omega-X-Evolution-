# OMEGA-X Evolution — v13–v15

Development snapshot 0.15.0.dev1. Three new opt-in research paths; v4–v12 core and checkpoint source bytes are unchanged. The expanded roadmap is registered in README. The name "universal" is a long-term objective, not a claim of arbitrary-language parsing or general program synthesis.

## v13 — typed polyglot evolution

`omega_x_evolution.polyglot` evolves immutable expression trees with two unsigned 16-bit inputs and modular arithmetic. Six binary operators (add, subtract, multiply, xor, and, or) and constant/variable terminals; 63 nodes, depth 8, 4096 attempts, 500,000 training point evaluations maximum. Every duplicate or invalid proposal consumes an attempt. A target-independent grammar and compositional expansion alternate with seeded elite mutations. Selection minimizes bit Hamming distance on training, then maximizes exact matches, then minimizes nodes. Holdout is evaluated after selection only. The fixed interpreter is the reference; generated sources target Python, C, C++, JavaScript, Go, Java. C/C++/Go use 32-bit unsigned intermediate semantics, Java 32-bit modular integer semantics and JS exact arithmetic for intermediate products and masking. Inputs must be u16. No arbitrary candidate source, FFI, user compiler flags, calls, loops, file/network operations or language parsing. This is not a sandbox for user-written programs. Verification explicitly compiles/runs only code generated from validated IR, in per-backend temporary directories with bounded timeouts and restricted inherited environment. Toolchains must be trusted. A missing compiler is recorded as unavailable, never pass. Actual backend tests are finite differential tests, not formal compiler proofs. 

```sh
python -m omega_x_evolution.polyglot --seed 42 --budget 1024 --verify
python -m omega_x_evolution.polyglot --dataset observations.json --budget 1024
```

Input JSON: `{"train":[[1,2,3]],"holdout":[[3,4,7]]}` where rows are `[x,y,expected]`. Split and coordinate uniqueness enforced. Report includes tree, all emitted sources and data digest. The [v13 example](polyglot-benchmark-v13.json) reconstructs `xor(add(x,y),y)` on 32 train + 32 heldout samples, with zero bit errors and all six installed backends passing. Target function is not passed to the search. No claim of universal equivalence; source-generation subset only. 

## v14 — neuro-symbolic model

`omega_x_evolution.neuro_symbolic` fits a restricted symbolic equation via v12, verifies its simplification with the v7 formal gate, then fits a two-hidden-layer MLP to residual errors using actual full-batch gradient descent with momentum. The fitting data has train/validation/test splits with no repeated coordinates. Symbolic search and weight fitting use train only; validation chooses the better of the original symbolic function and hybrid. A final test set reports both results after selection; no tuning on its outcomes. A failure of the proof gate aborts hybrid mode. The native solver proofs apply to the symbolic rewrites only, not neural generalization. An invalid test-domain evaluation is reported as null, never a pass. NumPy and a system Z3 library are required. Model weights are exported as bounded numeric JSON, not pickle or executable source; shape/finite-value checked on load. The weight digest is not a signature. 

```sh
python -m omega_x_evolution.neuro_symbolic --seed 42 --budget 128 --epochs 400
python -m omega_x_evolution.neuro_symbolic --dataset observations.json --epochs 200
```

Custom JSON uses three arrays `train`, `validation`, `test` of objects with `x`, `y`, `z` as in v12. Inputs x,y in [0,1], finite targets with |z|<=1e12. 1–512 rows per split. The [v14 report](hybrid-benchmark-v14.json) is a synthetic smooth function with 96/48/48 samples and 337 residual parameters. Test RMSE fell from 0.1260163 to 0.0484670. Validation selected the hybrid; no statistical generalization claim. To reconstruct predictions use `Model.from_json(json.dumps(report['model']))`, `predict(model, rows)` and `symbolic_predictions(report['expression'], rows)`; combine only if `report['selected'] == 'hybrid'`.

## v15 — real architecture and training algorithm evolution

`omega_x_evolution.neural` trains feed-forward MLPs with one to three hidden layers and widths 4,8,16,32. Mutations change width, depth, tanh/ReLU activation, SGD/momentum and learning rate. All candidates train on identical data and fixed seed, with equal epoch count; train-only scale, bounded initialization, gradient clipping and finite loss validation. Selection minimizes validation RMSE, then parameter count, with deterministic tie breaks. Test labels never select architectures. The fixed baseline is a four-unit tanh MLP with SGD; it is included in the population. There is no arbitrary training-code generation or neural graph editing beyond this typed search space. Budget is enforced conservatively by an upper bound on epochs × records × parameters per training and across the search; this is a work proxy, not FLOPs or time. Training executes on CPU using NumPy; no GPU/NPU claims. Reproducibility is established on the local NumPy/BLAS runtime, not bitwise across hardware. An additional cost constraint or fixed parameter budget is future work; this experiment compares quality under equal per-candidate epochs, not equal compute or model size. 

```sh
python -m omega_x_evolution.neural --seed 42 --task xor --rounds 3 --population 4 --epochs 180
```

The [v15 report](nas-benchmark-v15.json) trains nine unique candidates out of a bound of twelve. Selected architecture: widths 4/8, tanh, momentum, learning rate .08; 61 parameters vs 17 in baseline. On the fixed synthetic XOR-style dataset: validation RMSE 0.243888 vs 0.377303, test RMSE 0.191320 vs 0.356143. This is a regression of a binary target, not accuracy or a large-scale NAS benchmark. The actual final trained weights are exported; `Model.from_json` reconstructs them without training. No neural architecture deployment, external benchmark, GPU or large-scale training. 

## Verification and remaining boundaries

See [verification-v15.txt](verification-v15.txt). No paid inference, CI activation, physical multi-host cluster or production deployment. v13–v15 have functioning bounded implementations; general program translation, neural-symbolic reasoning beyond numeric models, arbitrary neural topologies and large-scale NAS remain open. Next stages v16–v20 are on the approved roadmap in README.
