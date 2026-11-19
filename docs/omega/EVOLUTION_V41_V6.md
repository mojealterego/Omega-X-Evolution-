# OMEGA-X Evolution v4.1–v6

Release family: `0.6.0.dev1`. The three milestones have concrete bounded interfaces and local acceptance tests. This is not a declaration of arbitrary code evolution, general formal equivalence, real multi-host deployment or scientific discovery beyond the numerical surrogate.

## v4.1 — durable distributed evaluator

`omega_x_evolution.distributed` supplies an SQLite-backed, content-addressed job queue, transactionally exclusive claims, expiring ownership with opaque fencing tokens, renewal, bounded retry and idempotent completion. Job identities include the evaluator contract. Workers receive public points and restricted expressions only. An authenticated per-worker bearer token and verified TLS (mandatory off loopback) protect transport. The client does not follow redirects or use environment proxies. JSON messages have a 128 KiB bound. A trusted coordinator recomputes every returned evaluation; a discrepancy aborts the generation before checkpoint commit. No worker controls the archive, checkpoint key, holdout or promotion objective. Verification is correctness-first and makes no speedup claim.

On one machine (two terminals, never commit keys):

```sh
umask 077
python - <<'PY'
import json,secrets
from pathlib import Path
key=secrets.token_hex(32)
Path('worker.key').write_text(key)
Path('workers.json').write_text(json.dumps({'worker1':key}))
PY
python -m omega_x_evolution.distributed controller --db evaluation.db --keys workers.json --generations 5
# second terminal:
python -m omega_x_evolution.distributed worker --url http://127.0.0.1:8787 --name worker1 --key-file worker.key
```

For a remote host, use an operator-provisioned certificate and matching DNS/IP SAN, `controller --host 0.0.0.0 --cert server.pem --tls-key server.key`, and `worker --url https://HOST:8787 --ca trusted-ca.pem`. Replace HOST with the hostname on the certificate. Protect key files, DB directory and listener via operator access controls and firewall; distinct high-entropy worker keys are required. The worker renews its short lease before evaluation; the HTTP renewal endpoint also supports explicit extension. The SQLite queue is single-controller storage on a local filesystem, not a distributed DB. Queue expiry uses controller wall clock; sudden clock changes can delay or shorten recovery. No hostile-internet DoS guarantee. Transport authentication does not establish remote execution attestation. Jobs left after timeout may be recovered or exhausted; keep a per-experiment queue. Exhausted jobs require a new queue/run or operator recovery, not unchecked retry. TLS in tests uses ephemeral keys, not production PKI. The controller CLI supports a new offline run; Python API supports authenticated checkpoint resume:

```python
from omega_x_evolution.distributed import Queue, run_remote, serve
```

`run_remote` accepts the same `Config`, `checkpoint`, `resume` semantics as the original controller, with explicit per-job timeout. The core, checkpoint and worker implementation bytes are unchanged, preserving v4 checkpoint contract compatibility.

## v5 — bounded meta-agent evolution

`omega_x_evolution.meta` evolves an ordered sequence of allowlisted proposal operators and a bounded internal attempt count. Operators sample, refine, generate benchmark-specific ratio expressions, symmetrize, or simplify. Mutations insert, delete, replace or adjust attempts. No arbitrary Python, tool access, evaluator modification, or permission modification. The original `run` evaluates every candidate with its fixed Cascade and score. Train and validation seed sets must be unique and disjoint; selection only sees training observations. One selected challenger is evaluated against the original simulated proposer on validation seeds. Promotion requires non-regression of both fixed score and held-out quality on every seed, synthetic credit cap, and positive aggregate score gain. A rejected challenger leaves the default proposer unchanged. The result is an explicit policy artifact/experiment report; it is not automatically deployed. The inner workflow is bounded to at most 32 operator applications per proposal. Synthetic proposal credits are not monetary cost or a measured compute budget. The ratio operator encodes task-specific domain knowledge; this is not an unbiased benchmark of general agent ability.

```sh
python -m omega_x_evolution.meta --rounds 3 --population 4 --generations 3
```

See [experiment output](meta-benchmark-v5.json). Validation seeds 11 and 13 improved both fixed score and held-out quality against the original proposer, with spends 67/63 synthetic credits versus 63/63 (not a cost-reduction claim). This is one fixed configuration; no statistical significance or superiority to AlphaEvolve/DGM is claimed.

## v6 — bounded AST/IR superoptimization

`omega_x_evolution.superopt` validates the original AST before any transformation, applies a bounded fixed-point set of conservative rewrites, rejects an increased cost and emits an ordered, hash-consed DAG IR. Identities cover unary signs, multiply/divide by ±1, redundant abs/min/max, and common-subexpression elimination. It preserves operand evaluation order, exception checks and signed-zero distinctions on the documented float64 input domain. No reassociation, cancellation near zero, or arbitrary source execution. The IR rechecks numeric bounds at each instruction and rejects non-float or out-of-domain input. The v5 `simplify` operator feeds optimized source back through the unchanged original evaluation cascade. The IR is an explicit alternative interpreter, not automatically used to rate the existing AST benchmark. The optimizer's IR operation count is a static proxy, not wall-clock time. Finite test samples do not constitute formal proof.

```sh
python -m omega_x_evolution.superopt '(-(-(x*1))/1)+(x+y)*(x+y)'
```

The [example](superopt-benchmark-v6.json) reduces eight AST operations to four and then three unique IR operations. The next milestone v7 is formal verification of the rewrite and workflow contracts, followed by v8 knowledge distillation and v9 multilevel coevolution.

## Acceptance and limitations

Run `python -m pytest -q tests/test_omega*.py` and `python scripts/verify_hardening.py`. See [verification](verification-v6.txt). Local actual TLS, independent subprocess worker, simulated lease expiration, replay, fencing, concurrency, resource limits, checkpoint parity and AST equivalence tests were performed. Full upstream collection requires external dependencies; no GitHub Actions runs or remote deployment were performed. Roadmap status is bounded by the above contracts; general autonomous code changes and unrestricted operation remain outside these gates.
