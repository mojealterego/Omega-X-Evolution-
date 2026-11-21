# OMEGA-X | selektywne wykorzystanie H.A.E.E. v1 i PyNN 0.14.0

**Data:** 2026-11-21 | **Charakter:** opcjonalny moduł badawczy, poza obowiązkowymi etapami kanonicznej Roadmapy. **Baza przeglądu:** `main@5e24375d6e77835e7752f6ef4d489d38b4850b23`.

## 1. Pochodzenie i decyzja

- **HAEE-ENG-001, v1.0.0** (źródło przesłane przez użytkownika, SHA-256 archiwum: `a1ca7baead447e0e43ffe22385828239fbac08d893386eb87afae8673f74149e`). Dokumentacja określa cztery moduły: Genome, Selection Pressure, Recombination i Gödelian Observer. Wyraźnie rozróżnia dokumentację od gotowego runtime; preferuje opcjonalną integrację z projektem **Locally-XXX**, bez duplikacji jego DGM/RSI. Tego pakietu nie kopiujemy do OMEGA-X w całości. Wykorzystujemy wyłącznie referencyjny kontrakt odrzucania niebezpiecznych genomów.
- **PyNN 0.14.0 API** — dziewięć dokumentów API (Populations/Views/Assemblies, Projections, Neuron Models, Synapse Models, Current Sources, Simulation Control, Random Numbers, Parameter Handling, Spatial Structure). Opisuje standardowe typy neuronów `IF_curr_exp` / `IF_cond_exp`, model Izhikevicha, zdarzeniowe źródła impulsów, STDP, `setup()` / `run()` / `reset()` / `end()`, jednostki mV, nA, ms i RNG. Wprowadzony poniżej model LIF NIE jest implementacją PyNN i nie potwierdza zgodności z NEURON/NEST.
- Status źródeł: **RESEARCH / OPTIONAL**, nie „MANDATORY IMPLEMENTATION”. Nie zmieniono żadnego istniejącego evaluatora, polityki promocji, bieżącej Roadmapy, ani GATE-09.

## 2. Wykonany podzbiór: HAEE admission

Plik `omega_x_evolution/haee_admission.py` implementuje rzeczywisty, wyizolowany punkt kontrolny `admit_haee(genome, experiment, policy)` dla manifestów zgodnych ze strukturą HAEE v1.0.0:

- ścisłe zestawy kluczy, typy i allowlisty; UUID, digest SHA-256 datasetu, pola programu uczenia; odrzucenie nieprawidłowego typu `bool` w polach liczbowych i liczb `10**400`;
- graf: unikalne identyfikatory, kontrola brakujących węzłów, duplikatów krawędzi, cykli **zerowego** opóźnienia, osiągalności węzła wyjścia, opóźnionych krawędzi i jawnych limitów;
- odmowa automatycznej promocji oraz wycieku zbioru danych na zewnątrz; ograniczenia liczby kandydatów, pamięci i rozmiaru manifestu;
- deterministyczny `sha256` semantycznie równoważnych kolejności węzłów/krawędzi, związany z polityką przyjęcia;
- wynik **research-admitted only**: `can_execute=False`, `can_promote=False`, `shape_compatibility_verified=False`.

**Bardzo ważne ograniczenie źródła:** dostarczony schemat JSON nie zawiera `port`, `dtype` ani wiązania wag / adapterów. Nie można więc uznać zwykłego przejścia takiego manifestu za sprawdzoną kompatybilność rozmiarów tensorów lub gotową kompilację sieci. Brak dowodu -> UNKNOWN, nie PASS.

## 3. Wykonany podzbiór: offline LIF reference

Plik `omega_x_evolution/pynn_lif_reference.py` implementuje prosty deterministyczny **referencyjny eksperyment prądowy**, inspirowany modelami typu integrate-and-fire i źródłami prądu z PyNN. Używa jawnego modelu z liniowym przeciekiem, stałym napięciem spoczynkowym, progiem, resetem i refrakcją. Przy stałym prądzie na przedziale czasu aktualizuje błonę rozwiązaniem analitycznym, a impuls jest kwantowany do końca kroku.

Wspierane są skończone przedziały DC, kontrola `dt` w milisekundach, do 20 tys. kroków i 32 przedziałów, wznowienie kolejnych segmentów `run()` bez resetu, pełny deterministyczny odtwarzalny replay oraz ścisłe porównanie śladów czasów impulsów. To **testbed**, nie emulacja `IF_curr_exp` 1:1 (brak synaps eksp. i plastyczności STDP, brak biologicznego kalibrowania). Do eksperymentu potrzebna byłaby osobna instalacja PyNN 0.14.0 + symulatora, stworzenie analogicznego scenariusza oraz sprawdzenie tolerancji parytetu.

## 4. Granice bezpieczeństwa i integracji

1. H.A.E.E. nie zarządza obecnymi archiwami MAP-Elites, checkpointami ani promocją. Walidator jest czystą funkcją przyjęcia badawczego.
2. PyNN nie jest wymagane jako zależność instalacji OMEGA-X. Moduł działa ze standardową biblioteką Pythona; żadnego kodu użytkownika nie wykonuje.
3. Nie ma nowych kluczy API, sieci, uprawnień chmurowych, modeli sprzętowych, treningu ani wdrożeń. Zgłoszenie z dokumentacji jest hipotezą badawczą, nie nową bramką blokującą.
4. Zamieszczone w repozytorium `tests/fixtures/haee_*_v1.json` to **syntetyczne** publiczne manifesty odtwarzające kształt źródła; oryginalnych dokumentów i prywatnych danych wejściowych nie publikujemy.

## 5. Wyniki i odtwarzanie

```bash
PYTHONPATH=. python -m pytest -q --strict-markers tests/test_omega_haee_pynn_reference.py
python -m compileall -q omega_x_evolution/haee_admission.py omega_x_evolution/pynn_lif_reference.py tests/test_omega_haee_pynn_reference.py
```

**Testy nowych modułów: 52/52 PASS**, TDD z RED = brak modułów, GREEN = 52 PASS; `compileall` PASS. Python 3.13.5, pytest 9.0.2, Linux x86_64; bez losowych generatorów i usług zewnętrznych. Oryginalny archiwalny pakiet H.A.E.E.: **10/10 testów kontraktowych PASS** w wyodrębnionym środowisku z biblioteką `jsonschema`; nie są to nasze testy runtime. Natywne PyNN **NOT RUN / PyNN nie jest zainstalowane**. Cała regresja repozytorium **NOT RUN** — dostępna była jedynie część drzewa i odizolowany testbed.

Braki: pełna walidacja typów/portów i fizycznych kernelów, cross-backend LIF parity, trening STDP, optymalizacja neuroevolution z zamrożonym holdout, testy wieloagentowe i ogólnorepozytoryjne. **GATE-09 nowych podsystemów: OPEN**, a wcześniejsza decyzja historyczna dla ograniczonego wydania nie jest zmieniana.

## 6. Kierunek dalszego wykorzystania (opcjonalny)

Po dostarczeniu oryginalnych angielskich dokumentów API i środowiska symulatora, oddzielna bramka eksperymentalna może porównać ślady `IF_curr_exp` na NEST / NEURON lub innym obsługiwanym backendzie z naszym modelem offline dla identycznego zegara, prądu i refrakcji. Dla HAEE następnym krokiem jest walidator `dtype/port` uzupełniony o źródłowy typowany IR, ale tylko jeśli istnieje dokładna specyfikacja. Do tego czasu nie promować genomów do realnego runtime.
