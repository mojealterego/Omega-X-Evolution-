# L7+ — native living-memory profiling (2026-11-27)

Base main 2b3e5a9d96daff3d12d7b45b8c1c038782af2690. Adds bounded native measurements around actual fixed offline diagnosis and authenticated review. Uses Python perf_counter_ns, process_time_ns and thread_time_ns. 1–32 complete invocations per call. Asserts exact repeatability of the result, not timing. Reports individual raw samples and median_low (lower middle for even sample count). No caller-supplied callback API; internal function invokes only existing fixed paths. No bypass of signed replay, lockdown or candidate/tenant binding. Physical energy, hardware FLOPs, allocator peak and isolated production timing are unknown. Process CPU includes other threads; thread CPU excludes other threads and BLAS worker time. Does not replace the existing v53 model work estimate.

Native timing experiment: Python 3.13.5, NumPy 2.3.5, cryptography 46.0.4, Linux, OPENBLAS_NUM_THREADS=1. 32 repetitions per path, actual test fixture batch with 24 train and 2 probe pairs of dimension 8; 8 signed evidence events, four signed A-E events for approved and six for lockdown. No warmup excluded; sample order offline, approved, lockdown. Median_low wall/process/thread ns:
- offline: 1246434 / 1245506 / 1243923
- approved: 39655556 / 39651931 / 39649597
- lockdown: 43067656 / 43064579 / 43062105 (two additional authenticated events, no memory diagnostic)
These are uncalibrated observations on one host, not an SLA, paired causal effect, mobile benchmark or production proof. Raw report SHA256 d0a984909735e0e926adbc7ca3aa5c897f8b9921f35fc4c4bab67a28906d62de.

Reproduce from isolated source checkout:
```python
from test_ontos_living_memory import batch, evidence, boundary
from omega_x_evolution.ontos_living_profile import profile_diagnostic, profile_review
b=batch()
p,t,h=evidence(b)
print(profile_diagnostic(b,repeats=32))
for alarm in (False,True):
    bp,m,bh=boundary(p,b,h,alarm)
    print(profile_review(b,p,p.sha256,t,h,bp,bp.sha256,m,bh,repeats=32))
```
Set PYTHONPATH=.:tests and OPENBLAS_NUM_THREADS=1 before invoking Python.

RED python -m pytest -q tests/test_ontos_living_profile.py: exit 2 missing module, log SHA256 1bd7f7dccc36b018960d1bf9b80f347fef3460472ab6efd329afb5c5681d6c00.
GREEN python -m pytest -q tests: exit 0, 136 passed in 2.96s (7 new, 129 prior), SHA256 ef7af0198a263fcb53599cf44c34e04ef6181aabcea34298f81268945149f478.
compileall exit 0. Source blob ee183dc278a56593e4413d16087a04d746e3beb0, test c4d9ff834691be704c47363156a5dec8e7aabe3c. Test IDs are pytest node IDs.
Scoped native measurements and tests only; GATE-09 full remains BLOCKED. Persistence, calibrated energy, FLOPs and real accelerators unverified. Full upstream regression unavailable due direct Git DNS. Next: durable custody of exact signed histories and interventional workload comparisons.
