# ONTOS v37-v39 — bounded offline reference increment

Base main: ece7ab7d58b6e3fce64421b6af6c8d6f026552e5. Source: L7 supplemental roadmap and user-supplied L7 PDF SHA-256 4dc81655621585b8c2443983b6362195c8e548448fd263cb1594e31596c46a19, source listings NonStationaryBioDigitalWorld, MetabolicLedger, blahut_arimoto. Python 3.13.5, NumPy 2.3.5, pytest 9.0.2. Direct Git clone blocked by DNS; isolated package subset used exact existing __init__.py (blob 2912b656166f79fe631e6ab48f167429cad6ccea) plus new modules. No mocks of the new code. Full repository regression and package wheel not executed.

## Scope and decisions

- v37: source-environment reconstruction with four 60-step epochs (three regimes, R0 returns), fixed action tapes, immutable observation values (without truth labels), separate scored trace, explicit source seed and bounds, no callbacks, no policy optimization. No repair, survival model or full L7 agent reproduction; these remain later work. Exact source seed draw and first transition cross-check; 30 historical seeds, fixed tape [0,1,2,3] repeated 60 times, per-seed summaries and complete canonical trace hashes saved in v37-campaign.json. Same campaign replayed twice, equal. 7200 scheduled steps, 1788 correct, 0 harm, 0 abstain, 678 OOD observations. No advantage or OOD-detector claim. These are new fixed-tape reference results, not Argon L7 agent results. No live actions.
- v38: validate finite probability distributions and row-stochastic channels (transpose source column convention), allow exact zeros, reject incompatible KL support and malformed distributions. Separate entropy reduction in bits, KL mismatch in nats, theoretical Landauer/mismatch joules and scenario compute debit. Additive accounting convention, not physical power. Immutable ledger with fixed modeled joule cap; over-budget and nonrepresentable debits fail without changing old state. No changes to runtime resource policy.
- v39: finite offline Blahut-Arimoto diagnostics with lower/upper numerical bounds and explicit convergence, capped iterations/work; fixed action-conditioned EFE = state risk minus information gain in bits, VFE for the posterior equals negative log evidence, impossible observation abstains. This is a numerical reference, not a deployed or autonomous Active Inference policy. No selection/execution interface. Full decision-loop integration outside this increment. Prior accepted evaluator, authorization, security and limits unchanged.

## Native isolated tests

| ID | Command | Observed result |
|---|---|---|
| V37-39-RED | python -m pytest -q tests/test_ontos_reference.py before implementation | import failure (missing v37 module), exit 2 |
| V37-39-INTERMEDIATE | same command after initial modules | 10 failed, 22 passed in 0.27s, NumPy scalar boundary |
| V37-39-GREEN | same command after scalar normalization and extra boundary/integration cases | 42 passed in 0.16s, exit 0 |
| V37-39-COMPILE | python -m compileall -q omega_x_evolution tests | exit 0 |
| V37-CAMPAIGN | campaign(tuple(9100+29*i for i in range(30)),(0,1,2,3)*60), repeated | identical 30 rows and trace hashes |

42 tests: 11 environment/boundary checks, 17 thermodynamic and budget checks, 13 channel-information checks plus 1 cross-stage offline integration. No skips. Known symmetric/degenerate channels, asymmetric 20,001-point reference grid, finite posterior/abstention, 10 seeded data-processing checks and work cap. The integration computes an empirical matrix from the fixed trace on the scorer side; it does not feed back or choose actions.

## Integrity

| Artifact | Git blob | SHA-256 |
|---|---|---|
| ontos_testbed.py | d431de36228df2eae4ca15270d115fe854de33e8 | a1725833d29c9f354afe39b89ac49d8956972a6cd307f73bee5727ca10095304 |
| ontos_metabolism.py | 0b4bab79ac20fcafbdac4ccf7d0ca993e12a017b | 617a165af02a0347f02f54cbb2958cee64d22dac3b0a4642efe04ab260c4fdce |
| ontos_information.py | 1d06c208d8f347297c49a0fa8c75efa4843cf0b3 | 5136d7d91069feedb03a203aeae7fddfc25c1717519627cf01208479fba7f0a2 |
| test_ontos_reference.py | d968c26dba418f720c1720b19beb1a47548a02df | 775461c2533ddfdc2008972a9ac669d9e2fbe9e352ef77eb55d978f835632dd0 |
| v37-campaign.json | 77c6788469ae91530c75831fc5f7407eb8c6aaef | 2cd28a92ea6ac60c156b7f2975503c4e0e28ed898d5c01462f408336d986b369 |

Local test logs: RED SHA-256 c8854c1bfc3be209c96737eb925ca934fa0e934940a947cd07e855748933f985; intermediate 43fe88d55f4afefe477b49c56fee69a89acbfd5ddebc35ee92f18299a940087c; GREEN 967a90f81cecadf06daa1a366bb275047d19ab77207db0cb708fbaae451f8f5f. Logs remain local; actual summaries above.

## Gate disposition

GATE-01/02 documented bounded scope; GATE-03/04 implemented and focused tests pass; GATE-05 offline integration passes for the new modules only; GATE-06 static boundary review plus negative input tests, no external security attestation; GATE-07 repeated deterministic reconstruction and immutable ledger atomicity in tested scope; GATE-08 source and test evidence recorded. Stage v37 environment subset TESTED, full source system independence/reproduction remains OPEN. v38 bounded mathematical/accounting contract PASS; v39 bounded numerical reference PASS, full integrated Active Inference loop OPEN. No unconditional stage or release certification, no change to existing bounded GATE-09. New modules are not wired to the operational runtime. v40-v42 next independent research backlog, subject to actual remaining obligations and scope.
