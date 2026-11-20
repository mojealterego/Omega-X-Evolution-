# v25 — existing trajectory transfer limit enforcement

Base main: 916a96631855d8fccd59aa03e646bd35f4ace47c. TRANSFER=8, CAPACITY=64 unchanged. Oversized foreign batches were accepted; len(foreign)==64 caused local[-0:] to retain all local records. Reject oversized batches before slicing. Valid ordering and suffix semantics unchanged.

## Focused native TDD
Python 3.13.5; pytest 9.0.2. Git clone unavailable (DNS). Exact production holographic.py from pinned SHA verified as original Git blob fcfe093df37ee75cd23ae4e990401bda19a2df97. The import and Memory smoke test reuse the extracted production Expression constructor/validator from v24 (extracted dependency Git blob 0045b84cf2c64c712a2c6086b837ed8199d669be). No mock merge or Memory implementation.

| ID | Command | Observed result |
|---|---|---|
| V25-RED | python -m pytest -q tests/test_omega_memory_bounds.py | 5 failed, 73 passed in 0.11s; exit 1 |
| V25-GREEN | same command after fix | 78 passed in 0.09s |
| V25-COMPILE | python -m compileall -q omega_x_evolution/holographic.py tests/test_omega_memory_bounds.py | exit 0 |

5 oversized batch cases, 72 legal batch combinations, 1 Memory integration with 64 actual records and normalized retrieval weights. No skipped tests.

Corrected module SHA-256 fd267adc391ce80802f47862dfc755f9a38dc6d2fa6e1e72309b481709b0944f; Git blob 7b442a497b64071e1517e58cec0159252e5bdcce.
Test SHA-256 5c074a055c14174e1e2386efe66c684a5456fea4d41fde4364f1b324932eba90; Git blob 008bbe53a84c4e7609a34341edaf178414579911.
Local log SHA-256 RED 9f6b10631154d6cd2da0c864e06c6622f7419b7985979ca3d7bdc2b12caf2e29; GREEN 34495c3948acc00ba3caadd3189e405b09cc5877d384da5d0642b76f3af11803. Raw logs remain local; observed results recorded above.

PASS limited to tested properties. Full cluster suite, global native Ray and production validation not performed. Existing bounded GATE-09 acceptance unchanged.
