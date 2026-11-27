# ONTOS — exact selective-classification feasibility audit (2026-11-27)

Base main 001066f6b791a52bd397a0b77ff69da2b1d93878. No changes to the policy or acceptance criteria. New module ontos_feasibility.py computes exact finite-count constraints. For N scheduled steps, M actual OOD observations, required correct fraction a and minimum OOD abstention fraction r, correct >= ceil(a*N) and abstentions >= ceil(r*M). Since abstention is never a correct action, correct <= N-ceil(r*M). The counting constraints are compatible iff ceil(a*N)<=N-ceil(r*M). This is a sharp combinatorial bound, not proof that a controller can realize the upper bound. OOD recall is a diagnostic condition chosen to quantify the trade-off, not an externally authorized new requirement.

Re-executed actual paired simulator and two frozen controllers on 30 previously evaluated validation seeds, 240 steps per episode. Full raw report repeated exactly, 60 episodes per execution, 28,800 steps across two executions. Each of the 60 trace hashes and counts matches the prior guarded-selection.json artifact. All ground truth is scored after termination; same-process logical boundary only.

| Arm | Clean correct | Clean abstain | Clean wrong | OOD correct | OOD abstain | OOD wrong |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 6225 | 108 | 116 | 1 | 749 | 1 |
| guarded | 6431 | 0 | 18 | 1 | 746 | 4 |

Zero harm in both arms because harmful action is excluded by the controller, not proof of external safety. Guarded clean accuracy 6431/6449, selective accuracy 6432/6454, unconditional 6432/7200. At observed OOD abstentions 746, even zero errors cannot exceed 6454/7200 (89.6389%). At an illustrative 99% recall floor, 744 abstentions are necessary and maximum 6456/7200 (89.6667%), 96 correct decisions below 6552 required for 91%. At 100% recall maximum 6449/7200. Target 91% remains FAIL; no veto disabled, no requirement relaxed. Prior validation seeds are now known; no new blinded holdout or full source reproduction.

## Evidence
CPython 3.13.5, SQLite 3.46.1, NumPy 2.3.5, pytest 9.0.2, cryptography 46.0.4, Linux 6.18.57 x86_64. All 46 original source/test Git blobs of reconstructed slice matched base tree; new tested blobs source 1fc63dc6e0213f2d676fbe0667274b151411c6c1, test 5ea7ce66429047199ae6c3938c6f20258a3631df. Tests executed with OPENBLAS_NUM_THREADS=1. TDD RED missing module exit 2, red.log SHA256 0abcfbae787af18b40590a822ab4d7f908a667006df7b2212cdf14e7b1cb42a9. GREEN python -m pytest -q tests/test_ontos_feasibility.py: 16 passed in .20s, exit 0, SHA256 fe7d42fa4595ec28138d47b584be346fb0d7ce12eef6744104232a5c89ef0f4b. Exhaustive count model for N=1..8 and targets/recalls 0,1/2,1; input validation, actual replay and metric accounting. Raw report feasibility.json SHA256 298099fd62dd70a2968e26b5227426457016a6c413311649e7757291fea2b87e.

All 236 distinct tests of available slice passed (16 new, 220 regression):
- python -m pytest -q tests --ignore=tests/test_ontos_living_journal.py --ignore=tests/test_ontos_managed_quorum.py --ignore=tests/test_ontos_v75_journal_gate.py --ignore=tests/test_ontos_v75_managed_gate.py: 213 passed 4.25s, SHA256 56e974226bd248bbf4533e827181abd8d4450072ab9f85af3bb2f9d18bdb3583.
- python -m pytest -q tests/test_ontos_living_journal.py: 8 passed 21.71s, SHA256 ab03b050f44927b6d787f195dd9f0134f48af3c330a1a37f2327e41bb7b3fa98.
- python -m pytest -q tests/test_ontos_v75_managed_gate.py tests/test_ontos_v75_journal_gate.py: 9 passed 24.90s, SHA256 ce796ad691e8b55db44f656f172295d54f4d36355477ae901eaa09c991d972df.
- python -m pytest -q tests/test_ontos_managed_quorum.py -k 'not actual_state_codec_digest_and_history_capacity': 5 passed 24.12s, SHA256 81e87c8ac6cfa758545528e2590aac147cf0a5d77d0b3c5c205172fdb6067b5a.
- python -m pytest -q tests/test_ontos_managed_quorum.py -k actual_state_codec_digest_and_history_capacity: 1 passed .65s, SHA256 a489b95f991cf3b2af940c3efd76379c549066ca66f8db75a93d48cac043aa0e.
All five regression invocations exit 0. python -m compileall -q omega_x_evolution tests exit 0. Test IDs are pytest node IDs; evidence package includes actual logs and raw report.

## L12 source recovery
Current docs/omega/V49_SOURCE_MANIFEST.json blob 2463a3831c91789fc5083428095ec2998fee5478 still declares all 33 originals RESEARCH, UNKNOWN license and null SHA256. Searched accessible conversation/library for ONTOS source archive; no original source archive located. Search is not proof of absence elsewhere. Original source bytes verified 0/33. Do not substitute locally reconstructed reference modules as original source bytes. Direct git ls-remote exit 128 DNS; API access works. Full upstream suite not run. GATE-09 remains BLOCKED. Next: obtain original source archive and independent pins; separate process-boundary verification of reference policy.
