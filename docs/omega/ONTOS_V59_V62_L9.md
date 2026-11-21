# OMEGA-X ONTOS — L9 v59–v62: wdrożenie ograniczonych modeli i audyt rozszerzeń

**Baza `main`:** `bf67e6b3d2a5269b5a29002d59f846caa35c0868`. **Tryb:** NATIVE (lokalne unit/contract), DETERMINISTIC-SIMULATION (testbed). **Pełne L9 GATE-09 OPEN**; historyczny ograniczony GATE-09 PASS zachowany, brak wdrożenia lub zmiany uprawnień. Source: ONTOS Ω∞ 91 stron, TOM V–VIII. Kod źródłowy rzeczywistych klas v37–v58 wykorzystywany zgodnie z dotychczasowymi kontraktami.

## Zrealizowane referencje

| Etap | Faktyczny moduł | Mierzalny wynik lokalny | Pozostały zakres |
|---|---|---|---|
| v59 | `ontos_v59_oscillator.py`: dodatni symetryczny niskorangowy Kuramoto (W=FFᵀ), siła O(nr), energia diagnostyczna, ograniczone kroki Eulera | 4 fazy/rank 2; 100 kroków, E 0,7243034→0,1086437; koherencja 0,6808421→0,9578089 | Ogólne niezmienniki dla wymuszonych oscylatorów i natywny CTM |
| v60 | `ontos_v60_sheaf.py`: restrykcje krawędziowe, grad E=1/2 Σw||R_u x_u−R_v x_v||², kontrola CFL i monotoniczności E | 3 węzły, 2 krawędzie; 100 kroków E 8,0625→0,1921434 | Cohomologia snopowa, skalowanie i hardware |
| v61 | `ontos_v61_faults.py`: niezmienne checkpointy 3×3, idempotencja, v41 RepairState/inject/repair, 15% rezerwy | 30 ziaren, po 2 awarie i 3 próby naprawy; średnia redukcja błędu 31,8736% | BraiNCA i fizyczny recovery |
| v62 | `ontos_v62_noise.py`: dokładny model niezależnego i skorelowanego kinetic proofreading, test dryfu i koszt liczby porównań | 7 200 prób; niezależny model 14 błędów, skorelowany 942; 4 sprawdzenia/próbę | Źródłowa Suite D 89,71%/health 0,93, rzeczywisty koszt J |

Przy skorelowanym szumie prawo p⁴ nie obowiązuje: model z mieszanką common cause daje \(P_{false}=\rho p+(1-\rho)p^4\). Nie przedstawiamy redukcji potencjału matematycznego jako energii w dżulach.

**Dane i replikacja:** [podsumowanie kampanii L9](ONTOS_V59_V62_L9_SUMMARY.json) i `scripts/ontos_v59_v62_campaign.py`. Pełny JSON 30-seed (SHA-256 `266af02dca9b790c661d68ae74d9e4b198a2da9842fda270097ada4731ffc715`) jest w dostarczonym ZIP, nie jest duplikowany w repozytorium. `physical_energy_joules=UNKNOWN`.

## Uzupełnienia użytkownika do Roadmapy

[Dokładne zadania EXT-01..EXT-07 / v81–v87](ONTOS_EXTENSIONS_V81_V87.md): [diagram sekwencji A–E](ONTOS_CHANNELS_A_E_SEQUENCE.md), [ziarna Phase0](PHASE0_FAILURE_SEEDS_SUMMARY.json), [energetyka core/peak vs wall-plug](ONTOS_ENERGY_BOUNDARIES.md), wyższe PolyTr_U z adjunkcją (OPEN), zdarzeniowe LBF/SOT-MRAM (OPEN), HyperLTL multi-trace (OPEN), RTL+LEC/Z3/DFX (OPEN). v81: diagram wykonany, **runtime protokołu nadal OPEN**. v82: syntetyczne ślady wykonane, **reprodukcja oryginalnego błędu Argona OPEN**. v83: specyfikacja jednostek gotowa, realne pomiary OPEN. v84–v87: wymagania z testowalnymi bramkami, **OPEN**.

### Ziarnowe zrzuty Phase0 — prawdziwy testbed OMEGA, nie źródłowe awarie Argona

`scripts/ontos_phase0_seed_diagnostics.py` generuje 240 obserwacji i 240 oddzielnych ocen scorera na każde z ziaren, bez dostępu obserwatora do etykiety `true_state` lub `ood`. Skrypt dodaje **wyraźnie syntetyczny** scenariusz skażenia pamięci i korekty. Pełne 465 065 B JSON z SHA-256 `68d7f7f03f621295aa3b8003fa1ca10afa87ea95e99530cd820fd8e915d17cbf` jest w ZIP; [w repozytorium podsumowanie z manifestem](PHASE0_FAILURE_SEEDS_SUMMARY.json). Po korekcie e-value zmniejsza się z 32 do 32/3; brak automatycznej promocji danych.

| Seed | Poprawne/240 | OOD | Tamper | Lure | Min posterior | SHA-256 śladu scorera |
|---:|---:|---:|---:|---:|---:|---|
| 9216 | 60 | 17 | 12 | 73 | 0,002103719 | `3888409f221f1c66756542f855a7ffc68249a1fe020a86b5216a4675f3bafd74` |
| 9274 | 60 | 20 | 12 | 72 | 0,002234219 | `aa944f40eb79d4d3af2da66774c73458ea0da28487e61b785772557834580e33` |
| 9651 | 60 | 28 | 12 | 60 | 0,002080455 | `5cc3cb66bccbdfd760af985172e5ac5369cbcdacc7e376770f6607638512a342` |

## TDD i testy dowodowe

Środowisko Linux x86-64, Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0, pytest 9.0.2; `OPENBLAS_NUM_THREADS=1`; istniejący v41 `ontos_repair.py` sprawdzony obiektem Git `454fcfb2164722748e486e9067c5b66732893dfd` i v37 testbed `d431de36228df2eae4ca15270d115fe854de33e8`. RED: brak `ontos_v59_oscillator`; po pierwszym GREEN poprawiono przypadek testowy niewłaściwej granicy CFL. Test z awarią zasobów, duplikacją event ID, współbieżnością logiczną i skorelowanym szumem.

```bash
OPENBLAS_NUM_THREADS=1 PYTHONPATH=. python -m pytest -q --strict-markers tests/test_ontos_v46_v48.py tests/test_ontos_v49_v51.py tests/test_ontos_v52_v54.py tests/test_ontos_v55_v58.py tests/test_ontos_v59_v62.py tests/test_ontos_phase0_diagnostics.py tests/test_ontos_extensions_docs.py
# 220 passed in 7.14 s, exit 0
python -m compileall -q omega_x_evolution scripts tests
# exit 0
```

Nowe testy: 45 v59–62, 6 diagnostyka, 5 dokumentacja; regresja wcześniejsza: 164. Łącznie **220/220 PASS**. Po rozpakowaniu deterministycznego ZIP ponownie **220/220 PASS w 8,38 s**; suma kontrolna ZIP OK. Całego upstream repozytorium (poza wycinkiem) nie skompilowano ani nie przetestowano.

SHA-256 lokalnie testowanych modułów:
- v59 `7f81c6aa3aea974e541d120d0f8c9d70ee5d5bc02325143e3404da9b133af606` (Git blob `14c5f98df72093da0223820329781f8e6a719971`).
- v60 `8579c9d33d5318dd19f5cd11dd9569edd6c7990015ae5e2e0a12da16970e474d` (Git blob `eab7b8de2b5e4cedee8e9fde4c899b4dc3d7978d`).
- v61 `2511ef17e0f32a1c8e2c04dc68d94ac1e3ea16f1f5efcdd05672f941f909a70c` (Git blob `9e8e412ee319de2430470ab5d9f468cf75759f0f`).
- v62 `e85d53506759caf86e58c64783a5aaf179472d0064898352fcd44a1e0a6a40b5` (Git blob `8d609ea670ce9bb53bcdf7a51d32b63afe515214`).

**GATE:** v59–62 referencyjne IMPLEMENTED/TESTED w skończonych kontraktach; pełne L9 GATE-05/06/07/09 OPEN. Brak aktywnej rekonfiguracji, nieautoryzowanego deploymentu, dostępu do GPU, NPU, FPGA, kwantowego sprzętu lub hostowych procesów. Rzeczywista implementacja następujących v63–v67 i rozszerzeń v84–v87 wymaga odrębnych dowodów. 
