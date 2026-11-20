# Cloud workload security-context hardening

Base main: `eadc3a61135ca43a8aaabd67e1ecace6fcdf10e1`. Existing v35 security scope; no new roadmap stage. Source blob before modification `f7a5c957fb528060a184fd9d988459306bb5e2db` matched main. Existing cloud regression test blobs also matched main.

`_match` previously accepted additional effective security-context values because its recursive comparison was a subset check. Container-level options override pod-level settings. The matcher now requires an exact pod security context and an exact container context except for four explicitly security-equivalent defaults. It rejects shared process namespaces, root overrides, unconfined seccomp and unmasked proc mount. Unexpected admission changes fail closed; durable reservations survive and unverified objects are not deleted by the controller. Strict matching intentionally rejects other injected security-context fields, including otherwise benign optional fields. Existing ledgers bind source hashes; no silent migration.

## Executed evidence
Linux x86_64, Python 3.13.5, pytest 9.0.2, CPU thread environment OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1. Tests use real controller, SQLite, local HTTPS transport and deterministic virtual provider, no actual cloud deployment.

- CLOUD-SEC-RED: `python -m pytest -q tests/test_omega_cloud_security_context.py` — exit 1, 5 failed, 1 passed. [log](cloud-security-red.log), SHA-256 `6fbe3c65ce9fc23a24a2a1b5650682501fe91ab408ce36a266588daffcf4d6e3`.
- CLOUD-SEC-GREEN: `python -m pytest -q tests/test_omega_cloud_security_context.py tests/test_omega_remaining_closure.py -k cloud` — exit 0, 11 passed, 19 deselected. [log](cloud-security-green.log), SHA-256 `e30087af03da0c873f75f173b6314795d129b2949b3a33334f0e7277cc6ec4cb`.
- CLOUD-SEC-SIM: `python -m pytest -q tests/test_omega_simulation_acceptance.py -k virtual_cluster` — exit 0, 3 passed, 5 deselected. [log](cloud-security-sim.log), SHA-256 `da27a0adf4b1b8856ff9db69223d1d7e0f3ae3a89f7a9fdc1c2b61ce783949f4`.
- CLOUD-SEC-BUILD: `python -m compileall -q omega_x_evolution/cloud.py tests/test_omega_cloud_security_context.py` — exit 0.

Source SHA-256 `7e72732aca30cc59c3bbc9f9fc5715942479f34e28932636c79991e1d087ca5b`; test SHA-256 `658586e302f450267d7a9a6166a86cb4efc96819f81f5e07792315d87c05acd7`.

PASS for tested effective-context admission and cloud lifecycle contracts. Not a complete Kubernetes admission-control policy, physical Kubernetes deployment or full current-main regression. No new native formal verification or upstream re-run. Maintainer release acceptance remains distinct from technical residuals.
