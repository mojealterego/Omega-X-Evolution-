# OMEGA-X Evolution — import v4

Based on SakanaAI/ShinkaEvolve (Apache-2.0); upstream authorship and LICENSE preserved.

This is the v4 evaluation-pool source snapshot, not a new benchmark claim. Previous verification: 80 targeted tests; full upstream collection blocked by missing dependencies. See `docs/omega/verification-v4.txt`.

- The upstream workflow definitions are retained in `docs/upstream-workflows/`, not in `.github/workflows/`, to avoid automatic Actions runs and release jobs.
- Research PDFs are retained in the complete Drive package, not republished in this public Git repository. Their digests are recorded in the import manifest and source inventory.
- Complete original archive: https://drive.google.com/file/d/1MC5-ikM9vAt7uJjuCGGRIBg4OH7q5siK/view
- Archive SHA-256: 8b6d0f6d2eff0754f942ff3259f49d7f6c7ba517e618b00c7a7b6908878deca9
- Next roadmap stage: multi-host evaluation transport, authentication, lease fencing and recovery; not implemented by this import.

Run the local offline evolution mode from a source checkout with `python -m shinka.omega --help`.
