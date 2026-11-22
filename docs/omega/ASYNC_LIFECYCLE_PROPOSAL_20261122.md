# OMEGA-X — Async Life Cycle Context Adapter (2026-11-22)

## Zakres i istniejąca architektura

W `main` OMEGA-X istnieje `engine.run` (generator mutacji, semafor i `asyncio.gather` dla propozycji) oraz asynchroniczny runner `cluster.run_cluster`. Nie ma uniwersalnego `main.py` z metodą `step_life_cycle`, ani zaimplementowanych tutaj klientów Active Inference, Titans i MCP. Ten etap nie zastępuje runnera; wprowadza **opcjonalny adapter istniejącego interfejsu `Proposal(model, prompt, seed) -> Awaitable[str]`**.

### Zaimplementowano

- `omega_x_evolution.async_lifecycle.collect_lifecycle_context` wywołuje do trzech **podłączonych przez operatora** bezargumentowych dostawców asynchronicznych równolegle, z jednym wspólnym deadline.
- `wrap_evolution_proposal` zachowuje pola `parent`, `inspiration`, `contract` i dodaje jedynie `untrusted_context` oraz `context_provenance` do JSON promptu. Bez podłączonych dostawców zachowuje prompt bajtowo.
- Błędy, zły typ wyniku, timeout i anulowanie źródła przerywają agregację i **nie wywołują dalszego `proposal`**. Wyjątki nie wypisują wartości wyników ani treści błędów providerów.
- Limit wejściowego promptu, limit sumy bajtów odpowiedzi (liczony po UTF-8), ograniczony timeout, uporządkowane rezultaty źródeł, anulowanie współbieżnych zadań, zachowanie `CancelledError` przy anulowaniu przez operatora.
- Dostawcy nie otrzymują automatycznie promptu, kodu źródłowego ani identyfikatora użytkownika. Są wywoływani bez parametrów. Decyzja o ujawnieniu danych z ich środowiska jest oddzielnym uprawnieniem operatora.
- JSON oddziela dane od pól strukturalnych promptu, **nie gwarantuje odporności LLM na prompt injection**. Nie ma nowych uprawnień MCP ani zautomatyzowanego zatwierdzania RSI.

### Przykład podłączenia do rzeczywistego runnera

```python
from omega_x_evolution.engine import Config, run, simulated_proposal
from omega_x_evolution.async_lifecycle import wrap_evolution_proposal, AsyncLifecycleConfig

# Źródła są jawnie przypisanymi przez operatora ASYNC klientami.
# Tu przykładowe deterministyczne dane lokalne (bez integracji zewnętrznych).
async def active():
    return '{"hypothesis":"baseline","verified":false}'

async def memory():
    return '{"retrieval":"none","verified":false}'

async def tools():
    return '{"tool_results":[],"verified":false}'

proposal = wrap_evolution_proposal(
    simulated_proposal,
    active_inference=active,
    titans_memory=memory,
    mcp_tools=tools,
    config=AsyncLifecycleConfig(timeout_s=5, max_context_bytes=8192),
)
# asyncio.run(run(Config(generations=1), proposal=proposal))
```

Ten kod nie uruchamia usług sieciowych. Klienci o rzeczywistych skutkach ubocznych i wrażliwych danych wymagają odrębnej autoryzacji, scope'u, rate limitu, izolacji oraz polityki retencji.

## Gwarancje i ograniczenia

`asyncio` współbieżnie obsługuje **kooperatywne operacje I/O**, nie daje automatycznej wielowątkowej równoległości CPU. Bezwzględny timeout jest ograniczony responsywnością event loop: złośliwy natywny kod, który blokuje wątek, wymaga izolowanego procesu. Anulowanie `Task` nie kończy siłą operacji ignorującej `CancelledError`; adapter ogranicza czas sprzątania, ale nie może zapewnić bezwzględnego wyłączenia takiej operacji. Brak retry z powodu ryzyka ponawiania operacji MCP o skutkach ubocznych; ponowienia muszą mieć własny klucz idempotencji i budżet.

Źródła `active_inference`, `titans_memory`, `mcp_tools` są **kontraktami integracyjnymi**, nie implementacjami Active Inference, Titans czy MCP. GATE-09, Lean 4/Coq, JEPA TDA, FHE, kwantowa akceleracja i tokenomika nie zmieniają statusu.

## Testy i bramki

- ALC-001..ALC-027 — `PYTHONPATH=. python -m pytest -q tests/test_async_lifecycle_adapter.py` — uruchomiono na izolowanym kodzie.
- ALC-E2E-01..02 — `PYTHONPATH=. python -m pytest -q tests/test_async_lifecycle_real_engine.py` — testy rzeczywistego runnera; **nie uruchomiono w izolowanym środowisku bez pełnego repozytorium**.
- Python 3.10 compatibility: standard library `asyncio.wait` i adnotacje z `from __future__ import annotations`; nie wymaga `TaskGroup` 3.11+.
- Status: IMPLEMENTED, LOCALLY TESTED. End-to-end z pełnym `engine.run`, natywne Titans/MCP, benchmark CPU i nowy GATE-09 są OPEN.

## Pochodzenie zmian

Wykorzystuje istniejący kontrakt `engine.Proposal`. Oceniono aktualny `main` na podstawie `f3a0d21e5ea8c386489ed0a77ac3147fc203c75d`. Nie powielono `ontos_observability`, `cluster_green`, `constitutional_drift`, `reward_order` ani `graph_memory`.
