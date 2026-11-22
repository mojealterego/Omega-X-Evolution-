# OMEGA-X RSI policy guard and authenticated portable IR — finite-contract engineering note

Date: 2026-11-22. Branch: `main`. Baseline commit: `1f30f122e457198de7636f99ae712406530daeef`.

## Source-derived requirements and scope

The user proposed: provable alignment, fallibilistic review, a Hamming-distance indicator, universal IR/AST routing, polyglot compilation, and a transport over Zenoh. These are **architecture proposals**, not evidence for the claimed universal complexity, human-value preservation, an unforgeable reward, or sub-millisecond end-to-end latency. No new mandatory L11–L111 requirement is silently introduced.

The existing repository already provides:

- `omega_x_evolution/polyglot.py`: typed bounded modular-u16 IR and emission to Python/C/C++/JavaScript/Go/Java (six, not 150 backends).
- `omega_x_evolution/proof_kernel.py`: independent polynomial normalization and certificate replay for the supported u16 ring fragment. `bitproof.py` offers optional native Z3 QF_BV on a separate path.
- `omega_x_evolution/epigenetics.py`: immutable mandatory gates `ast/formal/cascade/audit/budget/quorum`; optional search blocks cannot bypass them.
- `omega_x_evolution/cluster.py`: asynchronous MAP-Elites and durable authenticated checkpoints. This change does not replace, call, or bypass its admission code.

## Concrete implementation

`omega_x_evolution/rsi_ir_guard.py` provides:

1. `Policy`, `review_policy` and `policy_distance`: bounded immutable policy reference with canonical digest, fixed mandatory gates, operator-supplied allowed capabilities and work/memory caps. Monotone non-escalation denies new capabilities or larger budgets. Hamming distance counts **changed machine-permission flags only**: it is emphatically **not** a measurement of human ethical alignment; least-privilege tightening may increase that distance.
2. `review_equivalence`: revalidates both `Program` IR trees on consumption and calls the existing independent `certify` + `verify_certificate` proof engine. Its established polynomial fragment proves equivalence for the complete `(u16,u16)` input domain; other operators or non-proven identities remain `UNKNOWN`/`NOT_EQUIVALENT_OR_UNKNOWN`, never a fabricated PASS. It is not a compiler verification or a moral utility proof.
3. `review_candidate`: demands an operator-controlled expected SHA-256 of the baseline policy, checks non-escalation and functional equivalence, and returns `PROVED_NARROW_INVARIANTS` only for the checked conjunction. `release_authorized` is unconditionally false; a separate human decision and runtime gates remain mandatory.
4. `seal_ir/open_ir`: versioned binary prefix-tree encoding of existing u16 IR opcodes; HMAC-SHA256 over a binary header (magic/version/backend/monotonic sequence/payload length/policy SHA-256) and the tree; constant-time authentication before decoding; exact frame bounds; strict grammar; explicit supported backend selection; replay rejection using a **caller-maintained trusted monotonic sequence**. No candidate-authored code, arbitrary FFI, or compiler flags are carried by the frame. No actual Zenoh endpoint is introduced.

### Invariants

- `machine_policy_non_escalation`: new capabilities subset old; allowed resource bounds never increase; exact mandatory-gate tuple unchanged; operator approval always required.
- `u16_functional_equivalence` (polynomial subset): `∀x,y ∈ [0,65535], candidate(x,y) = reference(x,y)` conditional on the correctness and independence of the repository's trusted checker and semantics. It is **not** a proof of human values or safety of arbitrary Python/CUDA/Rust programs.
- `authenticated_message`: attacker without the HMAC key cannot modify the frame undetected under the cryptographic HMAC assumption; a compromised key defeats this property. Replay detection holds only with a persistent trusted sequence for the same per-channel key. A shared rollback of key/sequence/database is not solved by this component.
- `fail_closed`: missing proof, unsupported operator, malformed frame, changed authorization policy, untrusted baseline digest, replay, and failed message authentication never authorize execution.

### Not implemented (open)

- No CEV representation exists that can be proven preserved by arbitrary RSI. DPO/Constitutional AI may improve empirical preference matching, but **cannot guarantee absence of reward hacking**.
- No whole-program Rust/Zenoh/WASI integration, bitemporal durable rollback, FFI isolation, universal 150-language semantics, native compiler equivalence, zero-copy network serialization, JIT speed guarantee, or GPU/neuromorphic benchmark.
- No claims of `O(√N)` for generic code search or physical neuron-like message latency. FlatBuffers/Cap'n Proto can reduce copies in some processes but do not bypass network serialization, endianness, transport or memory-lifetime contracts.
- A monotone sequence held only in process memory cannot resist actor restart rollback. Use externally authenticated persistent anchor for production before enabling network transport.

## Test proof and commands

Local isolated execution, **not a full checkout**: `PYTHONPATH=. python -m pytest -q tests/test_rsi_ir_guard.py` — 38 PASS, `python -m compileall -q omega_x_evolution/rsi_ir_guard.py tests/test_rsi_ir_guard.py` — exit 0. The testbed uses an extracted equivalent of `polyglot.Program` + `_validated_tree`, `epigenetics.MANDATORY`, and the exact-replay polynomial proof subset; corresponding modules have not been changed in the repository. Tests inspect actual policy code and real normal-form computations, not stubbed `True` values. Specific end-to-end repository/Zenoh/compiler behavior is **NOT VERIFIED**. See `RSI_UIR_EVIDENCE.json` with SHA and fixture information.

## Next admission gates

- Clone the complete `main` tree and rerun the new tests with the **actual** `polyglot.py`, `epigenetics.py`, `proof_kernel.py` and current test suite; compare source digests. Fail closed on differences.
- Add operator-owned persistent per-peer replay counter, key rotation and authentication mapping before real Zenoh use; separately verify transport scheduling and failure handling.
- Validate that compilation never executes IR without the independent human approval and original safety gates. Add compiler differential tests across all supported backends and release-policy CI.
- Only after independent evidence compare measured end-to-end latency and robustness; do not promise sub-ms performance from library selection alone.

## Gate decision

GATE-01 limited requirements = PASS; GATE-02 limited architecture = PASS; GATE-03 finite module implemented = PASS; GATE-04 focused local unit tests = PASS; GATE-05 integration with actual repository/Zenoh = **OPEN**; GATE-06 policy/wire input validation = PASS in testbed; GATE-07 external recovery/persistent replay anchor = **OPEN**; GATE-08 local evidence = PASS; GATE-09 full integration/release = **OPEN**. Historical prior release-scoped GATE-09 statuses unchanged.
