# OMEGA-X — bounded coevolution (increment 2)

This opt-in package extends, rather than replaces, ShinkaEvolve HARDENED. The supplied 40-page architecture is preserved in `docs/omega/architecture-source.pdf`. Its reference controller uses simulated LLM mutations, seeded baseline metrics and a hard-coded audit key; the new implementation does not reproduce those weaknesses.

## Run locally

```sh
python -m shinka.omega --seed 5 --generations 5 --islands 3 --workers 3 > result.json
python -m pytest -q tests/test_omega_coevolution.py
python scripts/verify_hardening.py
```

Installed entry point: `shinka_omega`. The JSON report includes SFT (`prompt`, `completion`) and DPO (`prompt`, `chosen`, `rejected`) data. Review data quality before training. No model weights are automatically changed.

External inference is opt-in: pass `--fast-model MODEL --deep-model MODEL --allow-paid-api` with configured Shinka providers. The adapter calls existing `AsyncLLMClient.query`; it rejects headless mode and tool-bearing responses. **Credits are synthetic proposal units, not a hard monetary cap.** Provider retry behavior and reported costs cannot guarantee a billing limit. No live requests were performed in verification.

## Specification mapping

| PDF section | Implemented increment | Remaining scope |
|---|---|---|
| 2.1 / 5.5 | Asynchronous planning and ordered commits; bounded mutable selection genome | Agent code/tools, general workflows, independent meta-fitness and promotion experiments |
| 2.2 / 5.1 | In-memory genealogy, AST descriptors, local Pareto fronts, selection and ring migration | Persistent distributed archive, cross-host communication and checkpoints |
| 5.2 | Exact whole-expression SEARCH/REPLACE contract, strict AST interpreter | General source edit/file tools and OS sandbox |
| 3.1 / 5.3 | Per-run random HMAC key, source-file integrity check, session-bound single-use result authentication | External trusted signing service, attested immutable execution, actual tool-call canaries |
| 3.2 / 5.3 | Four stages: validation, smoke, required symmetry/weak balance properties, fixed numerical objective; evolving boundary-case pool | Real cluster workloads and external benchmarks |
| 3.3 / 5.4 | Thompson/UCB + tier and credit cost, bounded proposal count, SFT/DPO export | Distributed cost accounting; actual fine-tuning and validated weight promotion |

## Deliberate security and experimental decisions

- Candidates are **arithmetic expressions**, never `eval`/`exec` or unrestricted Python. No imports, attributes, object access, loops, comprehensions or exponentiation; node/depth/value limits. Their domain is two normalized resource ratios in [0,1]. The unmodified Shinka execution path is outside this restriction and still requires an OS sandbox.
- Parent selection weights and sigmoid parameters mutate; the promotion objective is fixed and the safety gate is mandatory. Do not compare candidates under their own mutable reward weights. This is restricted meta-parameter evolution, not autonomous rewriting of the trusted agent.
- The immutable benchmark is a regularized ratio surrogate (epsilon 0.01), not a Borg cluster or proof of scheduling throughput. All seed and candidate metrics are evaluated, including a holdout quality check. `performance` is a deterministic AST operation-count proxy, not measured wall time. Synthetic proposals sample bounded expression templates; they are not LLM output or open-ended algorithm discovery.
- HMAC receipts authenticate results within this process and detect in-run modifications of its source file. They are not remote attestation, OS isolation, or evidence of actual external tool execution. The private signing key is not passed to candidate expressions. A trusted-code compromise is out of scope.
- One deterministic run is not evidence of superiority over DGM/AlphaEvolve. Holdout is reported after selection, not a formal proof. `safety=1` means passing this restricted evaluator's gates only.
- Existing Shinka code remains supported. No default mode, provider, repo, permissions, or existing public runner were changed.

## Increment 3 — persistent evolution and recovery

`CheckpointStore` stores one authenticated generation snapshot in a local SQLite database. A generation includes RNG state, ordered genealogy (from which Pareto cells and child counts are reconstructed), adversarial challenge pool, model routing statistics, budget consumption, trial history and stagnation state. Every generation is committed atomically with `synchronous=FULL`; compare-and-swap on generation and prior MAC blocks stale writers. A crashed uncommitted generation is replayed in offline mode. Resume uses the absolute generation target, not an additional generation count.

```sh
# Generate and safeguard a separate 32-byte key; do not commit or upload it.
python -c 'import os,secrets; fd=os.open("omega.key",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(fd,secrets.token_bytes(32)); os.close(fd)'
python -m shinka.omega --seed 5 --generations 2 --checkpoint omega.db --checkpoint-key-file omega.key
python -m shinka.omega --seed 5 --generations 5 --resume --checkpoint omega.db --checkpoint-key-file omega.key
python -m pytest -q tests/test_omega_checkpoint.py tests/test_omega_coevolution.py
```

The HMAC key is never serialized. Resume requires the same configuration (except generation target), Python patch version, benchmark and exact engine/storage source hash. Checkpoint replay is deliberately offline-only: live provider requests may have non-reproducible outputs, irreversible billing or external side effects. The database and directory must be controlled by the operator. HMAC is authentication, not encryption, remote attestation or whole-database rollback protection. Protect the DB and key separately; use local storage with reliable SQLite locking and fsync. A crash during initial DB creation can leave an unusable file, so preserve it for diagnosis and start under a new path. The full-state snapshot is bounded to 128 MiB and rewritten per generation; incremental persistence and network transport remain future work. HMAC cannot detect deletion or replacement with an earlier authentic snapshot. No distributed consensus or production power-loss testing is claimed.

Roadmap: v3 generation-level restart and persistent archive implemented; v4 local/remote worker protocol and distributed scheduling remain open. v5–v10 remain as specified in the preceding architecture, subject to fixed evaluation and promotion gates.

## Increment 4 — local multi-process evaluator pool

See [research traceability](omega/RESEARCH_TRACEABILITY_v4.md). `--evaluation-processes 1..32` selects the trusted local back end. It preserves fixed-order commits, worker results are computed without holdout inputs, and worker failure aborts a generation. Checkpoints created under v3 are intentionally incompatible because their exact engine hashes differ. Multi-host distributed architecture remains open.
