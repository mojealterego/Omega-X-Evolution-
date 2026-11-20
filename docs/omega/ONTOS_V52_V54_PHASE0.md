# OMEGA-X ONTOS — v52–v54 Phase0 (ograniczone podkontrakty)

**Bazowy main:** `44dc3005931f31f1c69fca3f228636d7d3a6ffcd`  
**Status:** TESTED w izolowanym modelu; pełne v52–v54 **OPEN**. **Historyczny ograniczony GATE-09 PASS** pozostaje bez zmian. Źródło: [Roadmapa ONTOS Ω∞](ONTOS_OMEGA_INFINITY_ROADMAP.md), P0-03/06/07/08/10 oraz A04–A06.

## Implementacja

**v52 — temporal contracts:** `ontos_v52_temporal.py` implementuje dwie osie czasu (`valid_from/valid_until`, `recorded_at`), korekty historyczne według identyfikatora i czasu transakcji, logiczne filtrowanie tenantów, jawne grupy dowodów, 1/6/24 taktów i okno czterech pozycji. Sprawdzony rekord kopiowany jest do niezmiennego snapshotu, bez aliasowania wejścia. Zwrot `provenance_authenticated=False` i `independence_verified=False`: SHA i identyfikator grupy nie potwierdzają pochodzenia ani statystycznej niezależności. To nie trwała pamięć Titans/HOPE ani natywna integracja `GraphMemory`/`Holographic.Memory`.

**v53 — pre-reservation accounting:** `ontos_v53_accounting.py` udostępnia niezmienną księgę `WorkLedger`, rezerwację przed wywołaniem testbedu, limit operacji i bajtów I/O, jednorazowe rozliczenie oraz wykrywanie nieautoryzowanego przekroczenia kosztu. Modele inference/update/QR/SVD/LP/I/O mają odrębne wzory na **szacowane jednostki pracy**, nie zmierzone FLOPs ani J. Gdy nie ma pomiaru realnego, księga zwraca `UNKNOWN_ACTUAL_WORK`, obciąża rezerwę i `complete=False`. Dodatkowo testowana jest zmiana obiektu rezerwacji po utworzeniu.

**v54 — frozen Phase0 A/B:** `ontos_v54_phase0.py` wywołuje rzeczywisty referencyjny `ontos_testbed.replay` z niemodyfikowalnymi strategiami `A_cycle=[0,1,2,3]×60` i `B_offset=[1,2,3,0]×60`, bez uczenia i zmieniania polityki. Obserwator v50 używa tylko `ScoredStep.observation`; etykiety scorer (`correct`, `ood`, `true_state`) wykorzystuje dopiero podsumowanie. **Nie wykazano izolacji oddzielnego procesu.** 30 ustalonych ziaren, 240 kroków na strategię, 20 dev / 10 holdout, łącznie **14 400 kroków**.

| Metryka | A_cycle | B_offset |
|---|---:|---:|
| Kroki | 7200 | 7200 |
| Poprawne decyzje | 1788 | 1817 |
| Bezwarunkowa trafność | 24,83% | 25,24% |
| Błędy | 5412 | 5383 |
| OOD (po stronie scorera) | 678 | 713 |
| Harm/lure hits | 0/0 | 0/0 |
| Dev poprawne | 1191 | 1210 |
| Holdout poprawne | 597 | 607 |
| Źródłowy próg ≥91% | **FAIL** | **FAIL** |

Zero harm/lure wynika z braku akcji 4, **nie dowodzi bezpieczeństwa**. A odtwarza 1788 poprawnych i 678 OOD ze wcześniejszego [`v37-campaign.json`](v37-campaign.json) oraz trzy pierwsze pełne skróty śladów SHA-256. Mamy **60 nieweryfikowanych fizycznie rozliczeń**. `meets_source_target=False`, `eligible_for_release=False`; nie przyznawać nowego PASS.

## Rzeczywiste testy i SHA

Środowisko: Python 3.13.5, pytest 9.0.2, NumPy 2.3.5; lokalny Linux. Przed implementacją test RED: `ModuleNotFoundError`. Po pierwszym GREEN dodano testy negatywne: aliasowanie migawki, podmienialna tablica strategii, brak powtórnej walidacji zmutowanej rezerwacji i naruszona przez to zgodność SHA; testy wykazały cztery FAIL przed naprawą.

**Weryfikacja końcowa:**
```sh
PYTHONPATH=. python -m pytest -q --strict-markers tests/test_ontos_v46_v48.py tests/test_ontos_v49_v51.py tests/test_ontos_v52_v54.py
# 116 passed in 4.78s, exit 0
python -m compileall -q omega_x_evolution tests
# exit 0
```
25 nowych testów (w tym trzy parametryzowane przypadki zegarów) i 91 istniejących. Testy na rzeczywistych kodach w izolowanym wycinku, nie na atrapach. Cała upstream suite, natywne MLIR/Rust/WASI, fizyczna infrastruktura i instrumentacja rzeczywistych operacji — **niezweryfikowane**.

| Plik | Blob Git SHA-1 | SHA-256 |
|---|---|---|
| `ontos_v52_temporal.py` | `109d14b597c1406fd1040941944ec131ae450ce3` | `e0cab1f0e33a02ba4839d8cd7d8a3ea2df618479c4791b82dfa634809c1e70cf` |
| `ontos_v53_accounting.py` | `aed5e5120047badffa3d5eb1ba073bafab5e7bfd` | `937c41308427ab673765a531660724b46c0522aaf6dc964a5e6ab482c312cab5` |
| `ontos_v54_phase0.py` | `e94f07fe015351b39422770ffc89e5f010ec923b` | `8c69e1cda7d4de59d21ef52bb1c0d22bf16651827e6d1d0d4ae076c183a46317` |
| `test_ontos_v52_v54.py` | `d17ced7765b9a2b847819844fdce4bb471fbd20c` | `db35c717c7bb9ff1f76c24f4a46e36d3f97ed41bfd34875c12c9993062762959` |

Log testowy lokalny w paczce ZIP: SHA-256 `792d487966489eb28d8564cf395d7dbb3d94ecbfa670cae01e9d586d3f3be1c8`. Pełny per-seed `V54_PHASE0_CAMPAIGN.json` (ZIP, 52 173 B): SHA-256 `98aa7895cebc81e9b5733b53d39d216aeaac74d88e8e596dbf66a79d0ddbd943`. Komplet raportu można odtworzyć deterministycznie przez `run_phase0(PHASE0_SEEDS)`.

## Odbiór

GATE-01/02: kontrakty i ograniczenia; GATE-03/04: ograniczona implementacja i 116 testów PASS; GATE-05: wyłącznie lokalna integracja v37/v50/v52/v53/v54; GATE-06: testy błędnych wejść i niezmienności (nie pełny security audit); GATE-07: deterministyczny replay (nie natywne recovery); GATE-08: SHA i dowody; GATE-09: historyczny ograniczony PASS bez zmian, **nowy zakres v54 FAIL względem 91%**. Wszystkie poprzednie otwarte wymagania zachowane. Kolejne etapy: **v55–v57** (SCM, Balke–Pearl, informacja przyczynowa).
