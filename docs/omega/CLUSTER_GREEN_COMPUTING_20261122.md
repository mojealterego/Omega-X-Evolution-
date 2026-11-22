# OMEGA-X Evolution — Green Computing dla asynchronicznych wysp MAP-Elites

**Data:** 2026-11-22. **Tryb:** NATIVE / DETERMINISTIC-SIMULATION, eksperymentalne rozszerzenie opt-in.

## Motywacja i brak duplikowania istniejącego kodu

System zawiera `omega_x_evolution/green.py` (szacowanie energii procesu CPU), `performance.py` (Stage-3: trzy parowane rundy p50/p95/p99 i względny limit regresji), `cluster.py` (aktorzy lokalni i Ray, chroniona baza CAS oraz migracje), `topology.py` (adaptacyjna geometria SPD), `holographic.py` (pamięć trajektorii), `safety_synthesis.py`, `proof_kernel.py`, `federation.py`, `annealed.py` oraz `epigenetics.py`. **Nie kopiować** struktur z dostarczonych szkiców `MultiStageEvaluationCascade`, `RemoteIslandActor`, `OmegaXAsyncController`, ponieważ nie odpowiadają obecnym kontraktom repozytorium.

Nowy `cluster_green.py` uzupełnia `green.py` o *per-island* rejestr kosztów wykonywania kroków **na rzeczywistym workerze**. W domyślnym trybie kod klastra zachowuje oryginalny kontrakt. W trybie Green aktor opakowuje rzeczywiste `IslandActor.step()` w `sample_worker_step`, mierzy `perf_counter_ns` i `thread_time_ns`, a driver zapisuje metryki **dopiero po `verify_transition` oraz zatwierdzeniu transakcji `Store.commit`**. Odczyty pozostają poza podpisanym stanem wyspy i nie mogą zmienić GATE ani decyzji promotora. Ray i backend lokalny korzystają z tego samego kontraktu.

## Interfejs i polecenie

```bash
python -m omega_x_evolution.cluster \
  --db /trusted-path/cluster.sqlite --key-file /trusted-path/cluster.key \
  --backend simulation --islands 2 --rounds 2 --batch 1 --budget 8 \
  --green-watts 2 3 4 \
  --green-power-source reference-active-thread-power \
  --green-intensity-g-per-kwh 450 \
  --green-intensity-source reference-grid-intensity
```

Argumenty `--green-*` są opcjonalne, ale jeśli podano jeden, należy dostarczyć wszystkie. Wielkości `LOW/MID/HIGH` to **przyjęte przez operatora waty na aktywną sekundę CPU pojedynczego wątku**, nie waty mierzone na gnieździe ani automatycznie kompletne zużycie procesu. Natężenie emisji `gCO₂e/kWh` jest parametrem wejściowym pochodzącym od operatora, nie geolokalizowanym pomiarem. Model oblicza `E_CPU_Wh = t_thread_cpu_s × W / 3600`, `CO₂e_g = E_Wh × intensity_g_per_kWh / 1000`. Obydwa wyniki mają dolny, centralny i górny wariant scenariuszowy; **to nie jest przedział ufności**.

Raport `green_computing` obejmuje energię i CO₂e, czas pracy wątku, czas ścienny pojedynczych kroków, liczbę commitów, propozycji, odrzuceń i profilowań Stage 3. Eksport JSONL i Prometheus jest dostępny przez `cluster_green.render_jsonl` i `cluster_green.render_prometheus`. Prometheus publikuje wyłącznie agregaty stałej kardynalności; brak danych to pominięcie gauge i `_known=0`.

## Granice, bezpieczeństwo i restarty

- W czasie współbieżności `thread_time_ns` mierzy CPU konkretnego wątku, nie proces łącznie; wpływ GPU, DRAM, sieci, zasilacza, chłodzenia, idle oraz emisyjności produkcji sprzętu pozostaje **UNKNOWN**.
- Niesprawdzone dane czasu pochodzą od pracownika (actor); granica zaufania aktora, Ray i hosta nie jest granicą pomiarową. Podanie źródła profilu nie uwierzytelnia sprzętu ani źródła carbon intensity.
- Odmowa odczytu zegara i błędy danych oznaczają `UNKNOWN`; nie wystawiają zera ani PASS. Problemy telemetryczne nie blokują zatwierdzonego postępu silnika. Tylko zweryfikowana zmiana w `Store.commit` jest zapisywana w pamięci raportowej ledgera.
- Ledger jest procesowym sidecarem, bez nowego punktu zaufania TCB ani możliwości modyfikacji kandydatów. Po wznowieniu istniejące `revisions > 0` są jawnie oznaczane jako `previous_commits_unknown`; **nie można porównywać ich z dzisiejszymi krokami jako kompletny ślad energetyczny**.
- Wskaźniki p50/p95/p99 pozostają w oryginalnych zweryfikowanych profilach `performance.py`. Green ledger zapisuje liczbę profile/reject, ale nie zmienia progu 5%, kompromisów poprawności ani referencji rodzic/komórka/champion.

## Testowanie i bramki

`GCL-UNIT`: `PYTHONPATH=. pytest -q tests/test_cluster_green.py` (19 PASS w środowisku izolowanym). `GCL-COMPILE`: `python -m compileall -q omega_x_evolution/cluster_green.py tests/test_cluster_green.py` (PASS). `GCL-E2E` to cztery testy w `tests/test_cluster_green_integration.py` wymagające **pełnego repozytorium i zależności**: commit dwóch wysp, wznowienie po 2 rewizjach, kompatybilność bez Green, zgodność z Stage 3. Muszą zostać uruchomione i przejść przed zakwalifikowaniem tej integracji jako INTEGRATED. Nie zakładać natywnego Ray ani prawdziwych danych energetycznych.

**Status**: nowy model ledger TESTED lokalnie; pełna integracja i wszechstronny GATE-09 = OPEN dopóki nie ma powyższych wyników. Źródłowe sugestie Greena/Grovera, TDA, Lean, FHE i autonomicznej tokenomiki pozostają inspiracjami; nie są automatycznie nową obowiązkową Roadmapą. Użycie FHE nie dowodzi odporności na prompt injection; sam Tensor Train nie zapewnia kwantowego przyspieszenia; formalne narzędzia wymagają niezależnego kernela.
