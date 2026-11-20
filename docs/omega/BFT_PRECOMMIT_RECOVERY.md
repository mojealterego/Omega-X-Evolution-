# v32 — recovery of unpublished precommit certificates

Base main `cbd91c32578f6aa0fe531b598c40f8b3493eaf9a`. No new roadmap stage. v3.0 engineering acceptance; native local execution and deterministic virtual-time fault scenarios. This closes the reproduced post-quorum publication failure, not a claim of unconditional BFT liveness.

## Implementation

A validator now persists its most recent signed precommit atomically with its lock. Round changes preserve one receipt; committed height changes clear it. An authenticated read-only RPC returns the receipt and its matching prevote certificate. A hint in the existing view selects only current validators; it is not trusted evidence. Any replica independently validates signer, campaign, height, parent, membership, phase, round, digest, prevote QC and block replay. It assembles a distinct-validator quorum and commits through the existing durable Replica.commit path. After local commit, it disseminates the actual certificates. No leader override, fake votes, or relaxation of quorum. The added state is bounded to one latest signed receipt per validator. Genesis already binds source bytes; a changed protocol version requires new genesis/checkpoints, no silent migration.

## Verification

Environment: Linux-6.18.57-x86_64-with-glibc2.41, Python 3.13.5, local SQLite and real Ed25519; fixed identity seeds 1–4, deterministic virtual clock, 4 validators/f=1, genuine transport on loopback. No physical multi-host prerequisite.

- BFT-REC-01: RED: terminal leader crash after three precommits and recovery after a certified round advance both failed (2 failed, 1 passed). See red log. Test fixture was subsequently tightened to explicitly expire the capped terminal timeout and expanded with signed RPC, invalid QC and wrong voter/round/campaign checks.
- BFT-REC-02: GREEN: all 38 focused tests passed after synchronizing changed runtime sources with exact base Git blob identities, including existing consensus, terminal recovery, round catch-up, forgery and signed RPC tests. Command: `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python -m pytest -q tests/test_omega_precommit_recovery.py tests/test_omega_final_gates.py tests/test_omega_extended_consensus.py tests/test_omega_certified_round_sync.py tests/test_omega_terminal_recovery.py tests/test_omega_v32.py`.
- BFT-REC-03: `python -m compileall -q omega_x_evolution shinka` succeeded; `python scripts/verify_hardening.py` 38 passed on the initial local snapshot. Full current core collection: 428 tests. Earlier full regression attempt timed out before completion and before synchronization of the recent LRAT/IR files; it is not a PASS or a current-source full-suite result.

## Exact tested source and log fingerprints

- `omega_x_evolution/bft.py`: `de4321307565cd562fa8641548833fdf45eeaa3941832feda0cbabb2bb3e1913`
- `omega_x_evolution/pacemaker.py`: `bced4a03e3ef16a48da4ff9b48677934e45397274c8f6bc9dca90cf238291be1`
- `omega_x_evolution/bft_transport.py`: `b41bf71ac389aca3af474d0150f70d8f7f2400f46f3d69426e052d23e978d010`
- `tests/test_omega_precommit_recovery.py`: `815c1e6068209e5020bf391391cb2a3daa691044aa299cab7e76cdd74ad13952`
- `docs/omega/bft-precommit-red.log`: `123d5261fd774fb5e0d80e4b9c23a9fa86c163c83f3fa62f8eecddb6a364d4f7`
- `docs/omega/bft-precommit-green.log`: `276a6944bd6ec45a3a4a345ee79d0a3050b265d525e2b01f0284ed318ddedb75`
- `docs/omega/bft-precommit-hardening.log`: `9a67b0b645c2e02344152631fd84d11ead36117939a7d4f448d9e2676cefb7c3`

## Residual boundary

Recovery requires a reachable matching precommit quorum. A terminal leader that disappears before a quorum votes is still outside this fix; permanent partition, exhausted finite wire/height budgets and general liveness are not proved. Existing formal/proof-kernel and other outstanding functional requirements remain separate. GATE-09 is not marked PASS. No external audit or physical infrastructure validation prerequisite is added.
