# ONTOS v75 manifest archive boundary — 2026-11-25

Base main 29cd675b8c55861e4c1a7ffc9f624cc4bd01e30d. Refactor verify_manifest into a dedicated production module, retaining the old import path by re-export. audit_l12 accepts a typed SourceArchive or the legacy byte dictionary; both use identical per-file validation and gate reduction. Independent manifest and ZIP pins, canonical bounded JSON parsing, no extraction/execution or automatic release. Actual original bytes remain 0/33. The typed archive is input, not a new authority.

## Execution evidence
CPython 3.13.5, pytest 9.0.2, Linux x86_64. Locally reconstructed Git blobs verified: v49 manifest 11515442fa9adb3ff42f50595d79fcb8da400756; v72 JCS 1b61af871b78740203cb2418b0a7ca8d1bd06884; previous v49 archive tests bf5339f34e6f20aa2f0e55e60bea735dcb9cf01e; base v75 reducer 60b78532594769e742994ebf76ef3bc9b08588ac. New implementation 2cda8a91a6d16e6d883bd36dace0be9feb7b169d; tests 1bb17686f0b541bc190b0c6e36762e344d5daf9b; compiled reducer 0e07d9c1426532efe053b24c12df97417ce388bb.

- RED python -m pytest -q tests/test_ontos_v75_manifest_archive.py: missing module, exit 2; log SHA256 0a26f4d85e0ef8c30b93ebce03a80683ffdcd499fc579364ebf8b89a05f47a76.
- GREEN same command: 10 passed, exit 0, 0.12s; SHA256 27eb5ae8749462bee4fc1349efc0be2576d5b5585c8e974541e7128c15164326.
- Regression python -m pytest -q tests (isolated slice of 2 test files): 23 passed, exit 0, 0.11s; SHA256 4180455bfd3c95077fd59776dcae69c3a9a7cef18311fb2f922a413a55372c14.
- python -m compileall -q omega_x_evolution tests: exit 0, includes modified reducer and executed test files.

New tests use synthetic source bytes, actual ZIP/v49/JCS code and actual manifest verification. All 10 new case IDs in tests/test_ontos_v75_manifest_archive.py. A further full-reducer archive integration test added to tests/test_ontos_v75_acceptance.py is NOT RUN: exact full dependency tree unavailable in container (git ls-remote DNS failure). No full build, full regression, production TCB or source campaign claim. GATE-05/full reducer runtime and final L12 acceptance remain OPEN/BLOCKED. Historical bounded GATE-09 unchanged.
