# OMEGA–OTCM intake and reproduced reference tests (2026-11-27)

New user-provided corpus: 10 files, 7 PDFs and 3 ZIPs; two v1.10 PDFs are byte-identical. Source inventory JSON recorded in downloadable evidence (SHA256 307dcca531dbb09bb25b7d1814356ff3effd026911a2cb6c405e7ff3222642de). ZIP CRC check all three successful (184, 18, 23 entries). PDF page counts v1.0=21, v1.8=128, v1.9=141, v1.10=154, v2.0=163; standalone RCC monograph=9 pages. No claim of complete review of every archived vendor document or upstream. No original ONTOS L12 archive identified in these named packages; no substitution.

Key pins:
- OMEGA_OTCM_Omega_v2.0.pdf SHA256 9581b093f7880221775603d4c02883e722861ab8c75bc4e2b82d998cdedc3062
- OMEGA_OTCM_RCC_v2.0_Monografia.pdf 3948e26e3c538edebae58db5874f28face86f3a99f249fc62e8787cc7e1cad7b
- OMEGA_OTCM_RCC_v2.0_Pakiet_Reprodukcyjny.zip 583bad723fe772a712b6057e90d8eb41a2f2d7bc9772e8161d9f5a0a2a8fb417
- OMEGA_OTCM_v1.0-v1.7_Pelne_Materialy.zip 1263f5ef64bea4eda2bbb4f389a2a716881e640409c29e83c4887cd71b64cdf3
- OMEGA_OTCM_v1.10_Materialy_i_Testy-1.zip 5d2484f91b1e50f95f7896397c20cee6eb6f2084b46f3eab0523fbb30a5f5f3c

RCC monograph sections 6–10, 13, 16–18: cognitive atom/capsule IR, R0–R4 operator classes, exact R1 ridge sufficient statistics, bitemporal facts and current revocation overlay, dependency closure; no full authenticated tenant API, anti-rollback, physical sanitization, deep model unlearning or deployment. OMEGA-X integration target controlled adapters/replay/rollback. Do not treat supplied local Mesh as an authorized production memory service. The new exec boundary satisfies a separate native prerequisite, not integration of RCC data plane.

Reproduced unmodified RCC code in separate extracted package: sha256sum -c SHA256SUMS exit 0 (22 entries), log c287bcb6e114b10c4b5b8ebe98184dee0e86adbfcf941fd8822893b3e19264c8; python -m unittest discover -s tests -v exit 0, 12 passed (log d2b1fa138516e34d02b32e63d15e0382d15b367075dec809504b8ab56a54baf3). python experiment.py exit 0; 60/60 exact equality of Statistics and Fraction ridge weights after removal vs full rebuild (20 each n=100,1000,5000; d=8), 100 lineage DAGs, 1800 nodes. Median delta/rebuild ms: .7333835/1.601566, .7581445/9.997231, .861594/49.093054. Scope pure Python arithmetic, excludes I/O/LLM. Timing not deterministic; exact equality assertions are. Raw new report SHA256 b31254dc6dcc803d3672918b4b250f008d96682f0c102f7f08a2a272956ffd33. Original manifest verified before experiment rewrote report.
Continuity v1.10: sha256sum -c SHA256SUMS exit 0 (log 2c1741b90193ae9a8493d5e74b8035686fc2c61c4e5bd3a5c58aada81e51fc1f); python -m unittest discover -s tests -v: 10 passed .048s (log 86dd32094b3eb616ee3c81ed472dd0acbe15175b6131fb2238cadd675c372382). No physical hardware or external framework executions. These 22 reference tests are separate from 285 ONTOS tests. Native execution, not merely prior report reading.

Next integration boundary: bind authenticated tenant and encoder/version/lineage scope to R1 contributions; persist policy/revocation via existing fenced journals; test rollback and stale reader rejection; separate physical sanitization from logical unlearning. No automatic promotion or upstream license decision. Reference code reproduced outside production tree; not yet wired into ONTOS.
