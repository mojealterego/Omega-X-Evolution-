# ONTOS v2 / L7+ — source intake and exact PACE gate audit (2026-11-26)

Base main: 264cd976ea302a33a4657f8f866e652ffbb8d31c. Source: user-supplied 17-file monograph listing in conversation, not original archive or independently authenticated logs. Treat 240/240 survival, 96.1% accuracy, 99.7% R0 recall and other figures as source-reported, not reproduced. The original v49 33-file manifest is a different source inventory and is not satisfied by this listing.

## Mapping and static findings

Preserve v37–v75 and managed quorum; do not replace existing TCB with listing code. CfC/CTM v40/v59; Active Inference v39/v50; relational repair v41; Poly/Heyting/NARS v42/v60/v63; memory v43/v44/v51/v52; statistical gate v46; causal bounds v55–57; pure IR v47/v64; effects v65; WIT v63/v66; DFX v67; energy v38/v53/v68–71; evidence v72–75. Existing bounded implementations are not complete native reproductions.

Static source issues (not new runtime regression findings):
- A01: untrusted sympify/lambdify and arbitrary RTL expression strings; use restricted verified IR.
- A02/A03: object loop reads immune._key, and deterministic HMAC canary is reusable; no separate trust boundary.
- A04: Python lockdown can be cleared by next reshape; current capability sets may expand without ratification.
- A05: wealth floors and the 2.15/0.25 multiplier need a valid conditional null; four successes alone do not certify safety.
- A06: true regime enters empowerment/calibration and evaluator labels train probes; empowerment term constant over actions, so cannot change argmin by itself.
- A07: certificate covers RTL hash but not actual bitstream bytes, MLIR, size or freshness; hardware shell compares supplied signature rather than authenticating the complete stream. No physical programming was demonstrated.
- A08: bitemporal query lacks transaction-time filtering.
- A09: partial hand-assigned operation counts are estimates, not exhaustive instrumented FLOPs or measured joules.
- A10: synthetic TPM derived from accuracy is not an independently sampled interventional causal matrix.
- A11: simulated tamper branch verifies its own valid canary, not a forged token.
- A12: abstentions excluded from accuracy but included in the energy-efficiency numerator via alive*acc; zero-event stealth rate reported as 100%, not undefined.
- A13: finite effect-signature checking is not general HyperLTL; greedy pair merge is not minimum assembly complexity.
- A14: editorial span markers corrupt syntax in transmitted listing.
- Reported mean compute gain and ratio of aggregate efficiencies are distinct estimands; 6.71/0.948 is approximately 7.08, not 7.37. No claim of error if 7.37 is an independently defined mean of per-step gains.
- Scientific literature and device specifications are not independently reviewed in this increment.

## Implemented exact diagnostic

New offline module ontos_v46_gate_audit.py extends v46 diagnostics to arbitrary bounded rational binary multipliers, up to 240 trials. No memory promotion, operational authorization, new evaluator or policy. For win w and loss l, conditional null Pr(success | past) <= p is sufficient when p*w+(1-p)*l <= 1. Maximum p=(1-l)/(w-l). Exact IID first-passage probability uses integer mass DP over (step,success count), absorbing threshold crossings. Monotone coupling yields the same upper bound for the stated dominated conditional null. O(T^2) states, O(T) live storage ignoring integer bit complexity. No floor, no reset, no adaptive hypothesis selection in this model.

At threshold 20, 240 trials:
- source multipliers 43/20, 1/4, p=1/2: expected multiplier 6/5, crossing 0.16021326056843352, no Ville certificate; maximum p=15/38. Four consecutive successes already cross (probability 1/16 under IID half null).
- same multipliers, p=15/38: expected multiplier 1, crossing 0.042173408392371874.
- comparison fair factors 3/2, 1/2, p=1/2: expected multiplier 1, crossing 0.041160915068260404.
- floor at 1/20 with fair factors and wealth=1/20 increases one-step expectation to 1/16, violating supermartingale property at that state. Full source floor/reset first-passage rate is NOT computed.
- 30 candidate tests each alpha=0.05 have union-bound cap 1, not 0.05. Equal allocation 1/600 gives total <=0.05 if each per-candidate test is valid. No empirical claim that the actual source labels satisfy these null premises.

## Evidence

Python 3.13.5, pytest 9.0.2, Linux 6.18.57 x86_64. RED initial test collection missing module, exit 2, log SHA256 72049c480103e92264b10e35f8251825c5378962e4c97b13c7cc10a73439a955. Final additional floor test included in GREEN. Command: python -m pytest -vv tests/test_ontos_v46_gate_audit.py; 35 passed in 0.14s, exit 0; log SHA256 480873a3a0caa60fbc6ffd9d514cb9b5c0471ddfd518f1bed860d5bff3cd0274. python -m compileall -q omega_x_evolution tests exit 0 on isolated slice. Test IDs are pytest node IDs; exact enumeration is independent reference for 15 cases. No RNG required.
- implementation blob SHA1 98ade5a14807bdfa22020f12c1e64548ba1c9bc7; SHA256 ec6d597de1eae1079032256c2d483424aa31398ecdc80b92c5f9ae9aa391eeec
- tests blob SHA1 1c7f21cce0143a2d962eca77099b518b24715271; SHA256 58f5a774728fa3c3d5e34b4588b180d547210f9dc9098fb47aec1279bcee59ce

Scope: IMPLEMENTED/TESTED, NATIVE exact arithmetic in isolated component; no full repository build/regression (git ls-remote DNS failure, exit 128), no native reproduction of supplied 17-file experiment, no empirical validation of null, no new L7/L12 GATE-09. Remaining source issues and prior L12 obligations stay open.
