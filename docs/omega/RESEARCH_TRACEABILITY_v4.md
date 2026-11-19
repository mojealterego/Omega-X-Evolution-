# OMEGA-X v4 — research traceability and local evaluation pool

The supplied AlphaEvolve paper (44 pages), English DGM ICLR 2026/arXiv v3 paper (72 pages), two user-supplied translations and both NOEVARIS traceability documents are preserved byte-for-byte in `research/`, with SHA-256 and lengths in `research/sources.json`. NOEVARIS reports are reference designs/evidence for another project, not test results for ShinkaEvolve. No code from NOEVARIS was supplied in these two documents. No upstream code was fetched or executed.

| Source / section | Implementation in Shinka OMEGA | Evidence and boundary |
|---|---|---|
| AlphaEvolve §2.1 task specification, pp. 3–5 | Fixed ratio surrogate, bounded expression problem | One synthetic task, not general algorithm execution |
| AlphaEvolve §2.2 prompt sampler | Parent and one island champion inspiration | Rich multi-source context and meta-prompt experiments remain open |
| AlphaEvolve §2.3 SEARCH/REPLACE, p. 7 | Exact expression patch contract; existing provider adapter | No unrestricted file editing, no live LLM evaluation |
| AlphaEvolve §2.4 parallelized evaluation, pp. 7–8; Figure 2 p. 4 | NEW: spawn-based local evaluator process pool, fixed-order commit and holdout-free worker input | Actual child process, parity, worker failure tests; no remote cluster or isolation attestation |
| AlphaEvolve §2.5 program database | Existing Pareto archive, islands, genealogy and migration | Local storage; implementation inspired by the publication, not identical |
| AlphaEvolve §2.6 controller loop | Deterministic generation scheduling, durable commit from v3 | Local, offline recovery, no networked consensus |
| AlphaEvolve Table 2 p. 9; scientific results | Source retained for future task adapters | No reproduction of 48-multiplication result, no comparison with published benchmarks |
| DGM §3, pp. 4–5, Figure 1 p. 2 | Archive stepping stones, novelty-weighted sampling, bounded meta-genome | Does not evolve executable agent code; no SWE-bench or Polyglot reproduction |
| DGM §4 experiments | Fixed surrogate metrics and existing synthetic baseline | Ablation matrix and external benchmarks remain open |
| DGM §5 and Appendix H | Existing strict AST, fixed promotion objective and HMAC receipts | No sandbox for arbitrary code; no actual tool-call attestation. Logs alone are not evidence; marker manipulation in Appendix H motivates independent trust boundaries |
| NOEVARIS v1.17.7 / v1.18.1 | Design references for holdout, replay, signed evidence and exact symbolic proof | Separate project; 207 tests and 192 iterations reported there do not transfer to ShinkaEvolve |

## Local execution and recovery

```sh
python -m shinka.omega --seed 5 --generations 5 --evaluation-processes 2
python -m pytest -q tests/test_omega_workers.py tests/test_omega_checkpoint.py tests/test_omega_coevolution.py
python scripts/benchmark_omega_workers.py
```

The controller plans candidate jobs in deterministic order, validates patches, and sends only candidate expressions and public challenge/grid points to trusted workers. Results and per-point failure increments are returned in order; the coordinator updates the archive, signs receipts and commits a generation only after the complete evaluation batch. A broken worker pool aborts the run without a partial checkpoint commit. Resume restores the last committed generation. The worker pool count is an operational parameter, not a scientific one, and may change on resume within v4. The benchmark and compatibility hashes remain fixed. v3 checkpoint databases cannot be resumed directly under v4: the source hashes deliberately differ; keep the v3 release for old checkpoints. No migration is claimed.

This uses Python multiprocessing with trusted local code. It is **not** a hostile-code execution sandbox, remote worker authentication, cluster scheduling or a distributed database. Child processes may inherit environment and filesystem access; candidate expressions cannot use them through the bounded interpreter. No checkpoint HMAC key or holdout is included in worker inputs. The pool has bounded candidate work, but there is no hard OS watchdog for a hung trusted worker. Process startup overhead can dominate this small synthetic benchmark; no speedup is claimed.

Roadmap v4 is partially implemented (local process-pool evaluation). Remaining: explicit leased queue and fencing across hosts, authenticated transport, network failure and reordering tests, operator-controlled deployment. Subsequent work: comparable ablation experiments, constrained operator-level workflow evolution, proof-oriented task adapters and separately controlled evaluation. Untrusted arbitrary source execution and automatic deployment remain outside this release.
