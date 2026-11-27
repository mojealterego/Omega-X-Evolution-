# L7+ — paired ablations and bounded calibration (2026-11-27)

Base main 4d0f82d2601532d83e17f65109f8414ad1fd8b5f. Adds validated experimental PolicyConfig to the actual observation-only policy. Default values and historical simulator unchanged. No new operational privileges, no default-policy promotion. Experimental no-veto arms are diagnostics only.

## Protocol and results

30 development seeds 9100+29*i, 30 disjoint validation seeds 30000+73*i (i=0..29), horizon 240. Shared paired-v1 innovations per seed; equal exogenous flags hash checked. Six arms (one parameter changed per ablation), nine threshold grid arms and nine guarded floor/hazard arms, followed by baseline/candidate validation for each grid. 840 episode executions / 201600 steps per complete pass; all three reports repeated exactly (403200 steps across those two complete passes, excluding intermediate experiments/tests). All scheduled steps form denominator. Existing v74 paired statistics: 8192 bootstrap resamples, up to 8192 sign flips, Bonferroni intervals and Holm p adjustment. Approximate model-based inference only; no independent blinded holdout, empirical causal claim or original L12 60-configuration source reproduction.

| Arm | Correct | Abstained | Wrong | Accuracy |
|---|---:|---:|---:|---:|
| recurrent | 6297 | 789 | 114 | .8745833333 |
| memoryless | 4255 | 698 | 2247 | .5909722222 |
| no_ood_veto | 6936 | 117 | 147 | .9633333333 |
| no_confidence_veto | 6362 | 692 | 146 | .8836111111 |
| lower_floor | 6503 | 693 | 4 | .9031944444 |
| zero_hazard | 6251 | 794 | 155 | .8681944444 |

Unconstrained grid selected ood100_conf0 from development data (7004/7200). Validation: 6968/7200 correct, 232 wrong, zero abstentions including all 751 OOD events; baseline 6226 correct, 117 wrong, 857 abstentions. Accuracy .9677777778 vs .8647222222; paired effect +.1030555556, interval [.0934722222,.1133333333]. This numeric target pass disables both vetoes and is not an acceptable operational recommendation.

Guarded grid preserved OOD/confidence thresholds .5/.5, selected floor 1e-6, hazard .1 from development data (6503/7200 correct, 4 wrong). Validation 6432 correct, 746 abstentions, 22 wrong; 746/751 OOD abstentions, conditional accuracy .9965912612, unconditional .8933333333 vs .8647222222 baseline. Paired effect +.0286111111, interval [.01875,.0405555556]. The 91% unconditional target remains FAIL in guarded validation. Guarded grid was added after viewing earlier diagnostic results; not a pristine independent experiment. Both selections remain quarantined, no default change. Zero simulated harm in all arms is due to action-space exclusion, not demonstrated real-world safety.

Protocol pins: ablation ffeca4cba3655cfc361aa7cf587b4ff78dfcecaece3045c0600e99f750b053da; unconstrained 04bfc99919b44ca5e6281411e9fac6049cbb85376de5b2499114f6db85687b3d; guarded d3b49db9a9ff1a7152b814ed9515eedf94c99e2f3b6a3e6a94ed9d3a2dcb3916.
Raw report SHA256 (canonical Python sorted compact JSON + LF; reproducible via functions run_ablation, run_selection, run_guarded_selection):
- ablation.json 1c93a3bb75c091bc326a57e4734b75eeb66369177e98dcc3f6beae72b12753db
- selection.json 351fb625570ae575c9df87441e0801908263a109ff673b34fc0b37b127243ce9
- guarded-selection.json 72cdfe374824676032d9fe01caf020f58facc79ff7133125ef93503b45967fde

## Native evidence

Python 3.13.5, NumPy 2.3.5, pytest 9.0.2, cryptography 46.0.4, Linux x86_64, OPENBLAS_NUM_THREADS=1. Isolated prior evidence archive reconstructed; actual source hashes checked for policy, paired intervention, testbed, v50, v74, JCS. Direct Git DNS failed. RED missing PolicyConfig exit 2 eb95c4c9bf51614697116b4de3bd7117b5c97e0920dd34e0c2924ab9c2fc74a0; guarded RED missing function exit 1 f4bfd76095c62bffbe6d65c6f4eeb84787dd2ad9149032014a8f9ed805b83d12. Final focused green 60 passed in 1.40s exit 0; includes 18 new tests. SHA256 6ccdd21e73eaee013e624ac0d2a4835e30059d70aa89918b10155af793c1504d.

All 220 distinct tests of available slice passed in six complementary runs:
- 197 core: python -m pytest -q tests/test_ontos_ablation.py tests/test_ontos_observation_policy.py tests/test_ontos_paired_interventions.py tests/test_ontos_v46_gate_audit.py tests/test_ontos_v51_sequential_memory.py tests/test_ontos_authenticated_boundary.py tests/test_ontos_lockdown_alarm.py tests/test_ontos_living_memory.py tests/test_ontos_living_profile.py tests/test_ontos_quorum_state_codec.py; 3.72s exit 0; 019e1b304fd496376228da1375ec4d9d4cffb268b578ae2fe85aa82fd6240dd3.
- tests/test_ontos_living_journal.py 8 passed 19.40s exit 0 0f796115c34450a8700dc2ec757c4dc13aaba0a1cbb851370563ebbcb1f031a4.
- tests/test_ontos_v75_managed_gate.py 5 passed 15.60s exit 0 84ded930c7b22eb932f8be5d4e5d0f5d3faf1509f562e929ea134e0a46215318.
- tests/test_ontos_v75_journal_gate.py 4 passed 9.14s exit 0 1742d2c7e2ce2231207cd6797d27d01ef14e140b03b561ba228136b4f4a18db5.
- tests/test_ontos_managed_quorum.py -k 'not actual_state_codec_digest_and_history_capacity' 5 passed 24.18s exit 0 fafe7b2a54539406eef97ea2ea5bb06a960cb1ce3edcd5f83dd1453c6af70288.
- tests/test_ontos_managed_quorum.py -k actual_state_codec_digest_and_history_capacity 1 passed .70s exit 0 f1f22ef45c1b70de0e023f4ffeb8972ed79baca5fa09c008ff043aa87e880398.
All pytest invocations use python -m pytest -q and OPENBLAS_NUM_THREADS=1. Compileall exit 0. Tested Git blobs policy 8851a18d06f8ae14c9210c131cdde943b31a2a1f; ablation 9f515430c0c32aaa67b9ca9ce58c3213dcf28f56; tests b4c918d7273dcc8f407775a127d51d3a8a5c2aa5.

Scoped native ablation/calibration only. Original source archive, full upstream regression, original campaign, independent blind validation and physical deployment not verified. No full GATE-09 PASS. Next: improve guarded inference without unconditional OOD bypass and reconstruct original pinned source inputs.
