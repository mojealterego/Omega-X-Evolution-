# IR boundary hardening — corrective patch following v36.4

Base main: `7ea90d9955c6c1a3cd8884ac89b10d52da6c16ce`. Scope: v13 portable typed IR, GATE-06 corrective hardening; no new roadmap stage or assertion that v31 or GATE-09 is closed.

## Defect and correction

A frozen Python dataclass does not enforce validation at consumption: its tree can be replaced after construction or a subclass can bypass __post_init__. Before this patch, evaluate, emit and verify_backends trusted the Program type. A string literal could reach generated code or a compiler. This requires an invalid Python object at the API boundary; no remote exploit or OS sandbox claim is made.

The public boundaries now require the concrete Program type, revalidate the immutable tree snapshot and reject invalid literals, shape, depth and operations. The native compiler verification uses a fresh validated Program for both expected outputs and generated source. The internally constructed evolutionary loop uses the private evaluator after validation to avoid repeating tree validation on each training row. No change to the u16 semantics or public IR format. Program subclasses are deliberately no longer accepted at these boundaries. Other proof adapters are not audited by this patch.

## Verification record (NATIVE, local isolated source subset)

The original polyglot.py, __init__.py and test_omega_v13.py were reconstructed byte-for-byte from the pinned GitHub blobs and checked with git hash-object before testing. A complete checkout was unavailable: direct GitHub DNS/network failed in the execution environment. No paid CI was activated.

Environment: Linux 6.18.57 x86_64, glibc 2.41; Python 3.13.5, pytest 9.0.2, GCC/G++ 14.2.0, Go 1.23.2, Node 22.16.0, javac 21.0.12.1.

- OMEGA-IR-001..005 RED: PYTHONPATH=. python -m pytest -q tests/test_omega_ir_boundary.py — exit 1, 14 failed in 0.12s. All six emit routes accepted an invalid string, five evaluation cases failed to reject, subclass bypass accepted, invalid input reached compiler discovery, and excessive depth accepted.
- OMEGA-IR-001..005 and V13 regression GREEN: PYTHONPATH=. python -m pytest -q tests/test_omega_ir_boundary.py tests/test_omega_v13.py — exit 0, 19 passed in 7.37s.
- OMEGA-IR-006: python -m compileall -q omega_x_evolution tests — exit 0 for the checked subset.
- OMEGA-IR-007: real verify_backends execution for Program(('or',('and',('xor',('mul',('x',),('y',)),('sub',('x',),('y',))),('lit',65535)),('add',('lit',0),('lit',1)))) on ((0,0),(0,65535),(65535,65535),(32768,2),(1234,9876)) — exit 0; all six backends returned pass (C, C++, Go, Java, JavaScript, Python).

Tested source blob: `53289dcf148ad7159af67ae2e997eeae0a41ca85`; SHA-256 `760bfc549c2a2c7ce84e2aa44c1cf7d08dc142d0e17584fbe03ed613fef85905`.
Test blob: `c4c7c3fb08103482d9aee7e8fc1d911cb1cc4159`; SHA-256 `0ec7898ce3fc821d10e163b864c2373377ec5e8e80c55a4596a714a4bb77441d`.

Full repository regression not executed in this session; kernel proof, BFT, large pretrained LLM, novel primitives and upstream dependency obligations remain open as recorded in v36.4. PASS only for the tested IR boundary properties. GATE-09 remains BLOCKED. No deployment or production claim.
