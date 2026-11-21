# OMEGA-X — przegląd ośmiu propozycji i opcjonalna telemetria ONTOS (2026-11-21)

**Gałąź:** `main`. **Zweryfikowana podstawa:** `16eae9789d046b2720b98f84777fbf44dc4433c2`.
To **niewymuszający rejestr badawczy**, nie nowy obowiązkowy punkt `docs/ROADMAP.md` ani awans pełnego GATE-09.

## Wynik audytu kodu

W obecnym repozytorium nie znaleziono `step_life_cycle`, wskazanego przez materiał `main.py`, ani implementacji nazwanych `ConstitutionalShield`, `Huxley-Godel` lub `DynamicJEPA`. Istnieją za to: natywnie asynchroniczny `shinka/core/async_runner.py`, `omega_x_evolution/graph_memory.py`, księgowość `ontos_v53_accounting.py`, model SI `ontos_v68_units.py`, scenariusze v69, porównania Pareto v71 i ograniczony kernel certyfikatów `proof_kernel.py`/`lean_native.py`. Nie kopiować fikcyjnych interfejsów między produktami.

| # | Propozycja | Decyzja | Ograniczenie i wymagany następny dowód |
|---|---|---|---|
| 1 | Async step_life_cycle/MCP/Titans | **ADAPT** do istniejącego runnera; brak targetu do patchowania | `asyncio` współbieżnie obsługuje I/O, nie daje automatycznej równoległości CPU. Potrzebne konkretne entrypointy, nieblokujące API MCP, timeouty, anulowanie, benchmark throughput i bezpieczeństwo zależności. |
| 2 | Drift tarczy i DAG GoT | **RESEARCH** | W repo istnieje GraphMemory, lecz nie zidentyfikowano żądanych klas; wymagane rzeczywiste wejścia, brak pozornych testów fikcyjnego GoT. |
| 3 | JSONL/Prometheus energia, FEP, ewolucja | **IMPLEMENTED optional**: `ontos_observability.py` | Używa istniejących raportów v69/v71 oraz interfejsu do v53/v68. Metryki nie są fizycznie zmierzone, FEP/generacja oznaczają wyłącznie deklarację wywołującego. Brak bezpośredniego instrumentowania hipotetycznej pętli Huxleya. |
| 4 | Grover/neuromorphic DAG | **RESEARCH** | O(sqrt(N)) dotyczy zapytań kwantowego oracle, nie dowolnej klasycznej selekcji UCB, wall-joules ani braku narzutu. Wymagany oracle, QPU i uczciwy end-to-end baseline. |
| 5 | TDA w przestrzeni JEPA | **RESEARCH** | v58 zawiera ograniczony H0 Vietoris-Rips. Zewnętrzna persistent homology H1/H2 mogłaby pomóc diagnostycznie, ale nie gwarantuje uniknięcia zapadania się reprezentacji ani kontekstu 10M tokenów. |
| 6 | Lean4/Coq proof synthesis | **EXTEND EXISTING** | `proof_kernel.py` oraz `lean_native.py` wspierają ograniczony język IR; dowód wymaga stałej specyfikacji i niezależnego checkera, nie jest zamiennikiem testów ani uniwersalnym dowodem każdej mutacji. |
| 7 | FHE dla agentów | **THREAT-MODEL FIRST** | FHE chroni poufność danych pod obliczeniem, nie powstrzymuje prompt injection, SSRF ani dowolnej eksfiltracji metadanych. Porównać FHE, MPC, TEE i zwykłe mTLS według kosztów i modelu zagrożeń. |
| 8 | Autonomiczna tokenomika | **REJECT external finance; REUSE internal budgets** | Skorzystać z v53/infrastructure: limity, rezerwacje, fair scheduling, audyt. Brak autonomicznych płatności, zakupów zasobów lub nadawania uprawnień. |

## Działające API telemetryczne

```python
from omega_x_evolution.ontos_observability import make_snapshot, render_prometheus, render_jsonl, AsyncJsonlExporter
# scenario: real v69 SubstrateScenario instance; result: real v71 compare() result
snap = make_snapshot('experiment_001', 1, substrate_report=scenario.report(), pareto_report=result)
prometheus_text = render_prometheus(snap) # one snapshot per scrape
jsonl_line = render_jsonl(snap)
# opt-in asynchronous I/O with caller-owned trusted stream:
# await AsyncJsonlExporter(stream).emit(snap)
```

Only 10 fixed metric names are exported; no arbitrary labels or raw prompts. Values missing from real source reports are null in JSONL and suppressed from Prometheus gauges with `*_known=0`. Run ID is validated and not exported as a Prometheus label. Real physical measurement and release flags are always false. The async writer serializes events off-loop, enforces monotone sequence numbers per writer and poisons its stream after write errors. A partially failed write may still corrupt the last JSONL line; repair the caller-owned stream before resuming. No fsync, multi-process lock, persistence guarantee or complete runner instrumentation is claimed.

## Reprodukcja lokalna i granice odbioru

```sh
PYTHONPATH=. python -m pytest -q tests/test_ontos_observability.py tests/test_ontos_v69_v70_ramxeed.py tests/test_ontos_v71_energy_pareto.py
PYTHONPATH=. python -m pytest -q --cov=omega_x_evolution.ontos_observability --cov-report=term-missing tests/test_ontos_observability.py
python -m compileall -q omega_x_evolution/ontos_observability.py tests/test_ontos_observability.py
```

W izolowanym lokalnym środowisku Python 3.13.5, pytest 9.0.2, z rzeczywistymi modułami v69–v71 z wcześniej zweryfikowanego ZIP: **106/106 PASS**, **32/32 nowego zestawu PASS**, 100% statement coverage nowego modułu, compileall PASS. Testy nie zawierają wirtualnej symulacji całego istniejącego systemu ani nie dowodzą interoperacyjności MCP, Lean lub QPU. **Zakres TESTED lokalnie; L11 i pełny GATE-09 pozostają OPEN.**
