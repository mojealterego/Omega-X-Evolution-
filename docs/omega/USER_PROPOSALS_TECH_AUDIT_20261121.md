# OMEGA-X — przegląd propozycji rozwoju dostarczonych 2026-11-21

**Bazowy audyt:** `main` na `4ef94a1660529732207ebd246e603fbf7071eb4a`. **Zasada:** bez duplikowania istniejących etapów, bez traktowania nazw koncepcyjnych jako dowodów wykonawczych. To rejestr triage, nie deklaracja nowych testów.

| Propozycja | Istniejący komponent i etap | Decyzja | Kryteria dalszego odbioru |
|---|---|---|---|
| Stage 3 performance regression | `performance.py`, `engine.Cascade`, v21 | **JUŻ WDROŻONE W ZAKRESIE OPT-IN**. Pomiary porównawcze z rodzicem i elitą komórki/globalną, p50/p95/p99, trzy rundy AB/BA, próg 5% i tradeoff poprawności, zapis profili w checkpoint. | Stabilizacja środowiska CI, A/A noise floor, przedziały ufności, osobne profile hostów; nie porównywać starych bezwzględnych czasów na różnych maszynach. |
| Ray async MAP-Elites | `cluster.py`, v22, `distributed.py` | **ISTNIEJE BACKEND, NIEZWERYFIKOWANE NATYWNE RAY**. Ograniczony aktor/wyspa, CAS snapshot, replay, wymuszone limity, symulacja/process. | Uruchomić `scripts/verify_ray_cluster.py` na zgodnym z przypiętą wersją Ray; testy node-loss/restart, network partition, affinity, migracja, p95 throughput i odporność na duplikaty. |
| Riemannian topology | `topology.py`, v23 | **JUŻ ZREALIZOWANA SKOŃCZONA GEOMETRIA SPD**: siatka/quad-tree, metryka konforemna, Dijkstra, kontrolowana zmiana topologii. | Niezależna metryka różnorodności, ablacje vs stały MAP-Elites, poprawność przemapowania i brak regresji jakości; bez fikcyjnej geodezji ciągłej. |
| Quantum-inspired annealed TT | v24, `annealed.py` | **BOUNDED RESEARCH**; nie jest superpozycją fizyczną ani inferencją wszystkich gałęzi przy stałym koszcie. | Dokładne ograniczenia rangi TT, błędu kompresji, pamięci i kosztu obliczeń vs uczciwy baseline. |
| Holographic Hopfield memory | `holographic.py`, `cluster.py`, v25 | **BOUNDED IMPLEMENTATION**: stabilne BLAKE2b zamiast Python `hash()`, limitowane wektory/rekordy, ring transfer. | Walidacja trafności retrieval, odporność na prompt injection, nieudane transfery i stale provenance; skojarzenie nie zastępuje aktualizacji wag. |
| Autonomous formal synthesis | `safety_synthesis.py`, `modal.py`, v26 | **OGRANICZONY FORMALNY KONTRAKT ISTNIEJE**; nie samodzielna zmiana TCB. | Oddzielić syntezę specyfikacji od niezależnego checkera; brak dowodu → UNKNOWN/REJECT, mutacje i testy empiryczne pozostają obowiązkowe. |
| Quantum-assisted QUBO | `quantum.py`, v27 | **KONTRAKT SYMULACYJNY/JEDNO ZLECENIE**. Ocean real native + koszty niepotwierdzone. | Jawne uprawnienie do każdej płatnej sesji, klasyczny baseline, powtarzalność, end-to-end koszt wraz z overhead. |
| Architectural synthesis | v28, `architecture.py` | **BOUNDED typed composition**; nieograniczone odkrywanie prymitywów pozostaje otwarte. | Gramatyka AST/IR, niezależny test/rewriter, mierzone zyski OOD, brak samozatwierdzania. |
| Swarm Federation + P2P | `federation.py`, v29, v32 | **AUTENTYKOWANA IMPLEMENTACJA OGRANICZONA**; brak dowodu planetarnego HA. | mTLS/Ed25519, identyfikacja i revocation, canonical signing, lease replay, fault schedules, kontrolowany WAN test. |
| Epigenetics | `epigenetics.py`, v30 | **ISTNIEJE** jako ograniczony switchboard opcjonalnych funkcji; nie modyfikuje praw/dowodów. | Sprawdzać hysteresis i że zawsze `MANDATORY` nigdy nie są wyłączane, restart/replay. |
| Lean/Isabelle | v31 | **DOWODY W WĄSKIM ZAKRESIE**; nie 100% poprawności programu. | Kernel-checked exact theorem, źródłowe kompatybilności, niezależny verifier, pełne rozszerzenie bez pomijania testów. |
| New axioms | `axioms.py`, `rational_axioms.py`, v33 | **OGRANICZONE LEMATY/WERYFIKACJA**; nie dopuszczać samowolnego rozszerzania aksjomatów bazowych. | Nowe stwierdzenia najpierw jako *conjectures*; dopiero kernel-checked theorem + negatywne kontrprzykłady i kontrola spójności. |
| On-the-fly LoRA | `llm_plasticity.py`, `plasticity.py`, v34 | **OGRANICZONA REALNA ADAPTACJA**. | Frozen-base digest, atomic rollout/rollback, badanie OOD i regresji jakości, target > toy decoder bez automatycznej promocji. |
| Autonomous infrastructure | v35, `infrastructure.py` | **BOUNDED LOCAL + SIMULATED CLOUD**; bez uprawnienia do nieograniczonego provisioningu. | Operator-approved budgets, tenant isolation, idempotencja, kwoty i shutdown, testy retry/awarii, zero domyślnej ekspansji. |

## Korekta przekazanych szkiców

1. `await ray.get(futures)` jest błędnym wzorcem: w async driverze `await asyncio.gather(*object_refs)` albo `await object_ref`, z osobną kontrolą deadline i anulowania. Restart aktora nie odzyskuje sam stanu aplikacji.
2. Macierz `np.ones((...,2,2))` ma wyznacznik zero, nie jest metryką Riemannowską SPD. Midpoint `sqrt(v.T @ g @ v)` nie wyznacza geodezyjnej ogólnej krzywizny. Istniejący `topology.py` ma osobne, skończone przybliżenie.
3. Baza wydajności względem `_baseline_performance` z odejmowaniem `0.05` ocenia różnicę *punktów znormalizowanej oceny*, a nie względny spadek czasu. `time.perf_counter` na pięciu wejściach i `asyncio.sleep` do benchmarku wprowadzają szum. Kod nawet nie sprawdza obiecanego `correctness_gain` ≥2%. v21 już rozwiązuje te problemy w kontrolowanym zakresie.
4. `hash(text)` jest losowo zasalany między procesami Pythona; używać stabilnego, wersjonowanego hash/embedding i zachować metadane pochodzenia. Pamięć Hopfielda wyszukuje skojarzenia, nie przeprowadza jednoetapowej destylacji wszystkich wag ani nie dowodzi świadomego działania.
5. Klasyczne Tensor Train i simulated annealing nie dają komputerowej superpozycji ani bezkosztowego uruchamiania wykładniczo wielu alternatyw. Dostęp do płatnego QPU wymaga osobnego uprawnienia.
6. **Syntetyzowane aksjomaty nie mogą modyfikować trusted checker ani być uznane za prawdziwe bez dowodu**. Formal verification uzupełnia, a nie zastępuje testy, fuzzing i obserwacje produkcyjne.

## Priorytet

**P0:** natywna weryfikacja istniejącego v22 Ray i skalowalność z awariami; stabilność v21 p95/p99 i benchmarki A/A. **P1:** v25 retrieval/federacja z prowieniencją, v23 adaptacyjne metryki oraz integracja v24 z prawdziwym modelem w wąskim budżecie. **P2:** v27/QPU i nowe rodzinne architektury/aksjomaty jako hipotezy, dopóki niezależne dowody nie istnieją.

Nowe zgłoszenie **nie tworzy duplikatów v21–v35** i nie nadaje im nowych PASS. Dokument nie zawiera nowych wyników testów.
