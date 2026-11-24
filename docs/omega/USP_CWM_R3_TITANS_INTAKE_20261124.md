# OMEGA-X — ingestion of USP / CWM / R³Mem / Titans (2026-11-24)

**Status:** optional research implementation; no release or RSI privilege. Target branch `main` only. Base commit at review: `93c2cec2ec3490b3dbbefb42149920cca08b9b0c`.

## Source register, independently inspected PDFs

| Source | Identification | Engineering decision |
|---|---|---|
| `2610.34343v1.pdf` | Li et al., *Xing USP: A Cross-Family Semantic Contract for Information Extraction and Intent-Slot Parsing*, arXiv:2610.34343v1, 25 Oct 2026; §3, §4, Table 4, p. 18 | **IMPLEMENT** bounded independent diagnostic scorer with instance association |
| `557661924_1786317938658057_6511429830363523883_n.PDF`, `2510.02387v1.PDF` | Meta FAIR, *CWM: An Open-Weights LLM for Research on Code Generation with World Models*, arXiv:2510.02387v1, Sep 2025 | Research input: observation/action trace design, actual interpreter-based verification, mutate-fix tasks; **NO** neural execution claims |
| `2025.findings-acl.235 (1).pdf` | Wang et al., *R³Mem: Bridging Memory Retention and Retrieval via Reversible Compression*, Findings ACL 2025, pp. 4541–4557 | Research input: hierarchical representation, forward/backward reconstruction and cycle-consistency evaluation; **NO** trained reversible network |
| `NeurIPS-2025-titans-learning-to-memorize-at-test-time-Paper-Conference.pdf`, `5479_Titans_Learning_to_Memori.pdf` | Behrouz et al., *Titans: Learning to Memorize at Test Time*, NeurIPS 2025 | Research input: surprise-adaptive update with momentum, forgetting, memory as context/gate/layer; **NO** trained neural memory |

The two Titans PDFs are byte-for-byte identical; the two CWM documents contain the same 58-page research paper but have distinct file bytes.

## Why USP is the first increment

The existing OMEGA-X `graph_memory.py`, `semantic_memory.py`, `ontos_v65_hypertraces.py`, and `simulation_contracts.py` already cover bounded graph retrieval and finite, explicit trace-model checking. These do **not** score category/field/value/instance assignment errors consistently across NER, relation extraction, event extraction, and intent-slot parsing. Existing evaluator modules were reviewed before choosing the addition.

The new `omega_x_evolution/usp_contract.py` supplies:

1. A bounded validator for the paper's serialized `[{"category":"...","args":[{...}, ...]}]` representation and its schema (`category`, `args:[{"name": ...}]`). Categories, field names and values are treated as untrusted data, **not** executable commands. Duplicate JSON keys, unknown schema fields, over-budget arrays and invalid gold are rejected.
2. **Five distinct counts**: category set overlap; `(category,field)` set overlap; `(category,field,value)` set overlap; maximum one-to-one instance-field overlap; complete-instance multiset overlap. The latter two preserve multiplicity and binding. Matching is an O(k³) deterministic Hungarian assignment, not greedy.
3. Exact multiset Equality Accuracy and independent parse-success result. Failed/invalid predictions are counted as empty and cannot obtain successful Equality Accuracy, even for empty gold.
4. Dataset-level micro-count pooling, followed by equally weighted dataset macro scores **within each family** and equally weighted family scores (only families actually present). This is diagnostic evaluation, not the paper's benchmark reproduction.
5. Zero side effects; `promotion_authorized=False`. CLI: `python -m omega_x_evolution.usp_contract --schema schema.json --records records.jsonl` prints canonical UTF-8 JSON, accepts bounded on-disk JSONL records (`id`, `family`, `dataset`, `gold`, `prediction`).

### Distinguishing example

Gold contains two `ToolCall` instances: `read(a)` and `write(b)`. Prediction contains `read(b)` and `write(a)`. Category, field and unbound field-value views all score 1.0, yet instance-bound F1 is 0.5 and complete-instance F1 is 0.0. This is the exact failure class absent from category-only evaluation.

### Explicit scope and caveats

- This implementation realizes the mathematical diagnostic views and a **strict, documented subset** of the paper's serialized contract. It is **not** the official scorer, not the released 61-dataset corpus, not training, and does **not** reproduce the paper's reported 57.70 Field-Value result.
- Matching uses **exact text values** with no dataset-specific normalization, alias resolution, ontology, multi-value-in-one-field syntax, or semantic matching. Explicit empty string is a separate internal sentinel (not the literal string `NO_VALUE`).
- Bounds: max 64 categories and 32 field definitions/category; max 32 instances/category and 256 total; max 1024 Unicode characters/value; 2 MiB input JSON/JSONL and up to 10,000 JSONL lines. These are implementational safety limits, not claims about the research corpus.
- No MCP tools are invoked, permissions changed, or model-generated commands executed. No PII/secret export in normal operation; CLI output contains metrics, not raw content.
- The CWM software is BSD-3 (upstream repository) but the model weights are under a **separate noncommercial research license** (Meta/FAIR). No model weights are integrated; an open-weights release is not permission for arbitrary commercial use.
- R³Mem's term *reversible* refers to a learned bidirectional reconstruction model; lossy compression is **not** automatically exact or cryptographically reversible. Titans' surprise/forgetting formula is a learned test-time neural mechanism, **not** an authenticated durable memory store. Neither is used to bypass retained evidence integrity or constitutional policy.
- Training/model benchmarks, GPU latency, memory recall accuracy, full-repository regression, CI and native MCP integration are **NOT VERIFIED** by this increment.

## Verification contract

Run from an isolated source checkout containing these new files:

```shell
python -m pytest -q tests/test_usp_contract.py
python -m pytest -q --cov=omega_x_evolution.usp_contract --cov-branch --cov-report=term-missing tests/test_usp_contract.py
python -m compileall -q omega_x_evolution/usp_contract.py tests/test_usp_contract.py
```

ID `USP-TDD-RED`: import failed before source implementation (report `red.log`).

ID `USP-FIVE-VIEW`: adversarial binding swaps and duplicates retain correct count units. 

ID `USP-ASSIGN-ORACLE`: exact Hungarian score compared against exhaustive permutations for controlled random square/rectangular weights.

ID `USP-FAIL-CLOSED`: malformed, duplicate-key, unknown-field, invalid gold, Unicode, schema and resource-limit checks.

ID `USP-AGGREGATE-CLI`: dataset/family aggregation and JSONL CLI end-to-end.

All source SHA-256, environment, commands and observed results are in `USP_CWM_R3_TITANS_EVIDENCE_20261124.json`. This is a narrowly verified increment; no historical acceptance gate is overwritten.

## Recommended acceptance gate for future memory integrations

Any future Titans or R³Mem integration must establish: trained weights + license; source-to-recall fidelity on adversarial and long-horizon corpora; durable checkpoint/replay and recovery; tenant isolation; read/write authorization; redaction and prompt-injection defenses; deterministic simulated faults; paired accuracy/latency/energy measurements under identical workload. CWM-type *predicted* traces must never substitute for interpreter/VM execution traces as proof of program behavior.
