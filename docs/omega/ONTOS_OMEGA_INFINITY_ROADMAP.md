# OMEGA-X ONTOS Ω∞ — nadrzędna Roadmapa L7–L12 i post-Ω∞

**Wydanie Roadmapy:** 2026-11-20 / R2. **Status:** REGISTERED / OPEN (nowe etapy). **Baza:** main d699dc2bde2afb0426c326e0799ca1473079f355. **Źródło S2:** Argon, Dokument bez nazwy.PDF, „OMEGA-X ONTOS (Generacje L8–L12 / Ω∞)”, 91 stron, 14 tomów, 1 112 162 bajty, SHA-256 95c2794d9a3b5e237781b296b2aa6da0b6cdb174d6a73e5f754f48e7264edc36. Źródło S1: [L7](ONTOS_L7_ROADMAP.md). Oryginalne binaria nie są publikowane w publicznym repozytorium. Raport zawiera 33 listingi; nie są to jeszcze 33 odtworzone i skompilowane pliki.

**Cel:** jeden spójny system badań i weryfikacji, rozwijany ponad L12 przez poprawę jakości dowodów, reprodukowalności, stabilności numerycznej, odporności na błędy i efektywności zasobów.

**Architektura:** istniejący silnik pozostaje podstawą. ONTOS jest odseparowaną, skończoną domeną eksperymentalną; działa na danych, modelach i symulowanych akcjach, bez uprawnień do hosta, sieci, repozytorium, poświadczeń lub samodzielnych wdrożeń. Interfejs do istniejącego silnika to walidowane dane i certyfikaty czystych, ograniczonych obliczeń. Evaluator, korzeń zaufania, bramki, limity i uprawnienia pozostają poza zasięgiem eksperymentów.

**Stack:** istniejący Python/NumPy/SciPy, SQLite, pytest, ograniczona IR, Lean/Isabelle i SMT; zewnętrzne formaty Rust/Zenoh, WIT/WASI, MLIR/CIRCT, egglog, RTL jako osobne zakresy kompatybilności i symulacji. Wersje i licencje wymagają sprawdzenia przy implementacji; numer w raporcie nie dowodzi dostępności.

## 1. Nadrzędność, granice i statusy

Niniejsza Roadmapa porządkuje wszystkie kolejne etapy. Zachowuje [v1–v36 i wcześniejsze przyrosty](MAINTAINER_ROADMAP.md), [v37–v48](ONTOS_L7_ROADMAP.md) oraz [rejestr odbiorowy](CLOSURE_REGISTER.md). Nie zmienia istniejących wymagań w PASS, nie usuwa długu technicznego i nie powtarza potwierdzonych już własności bez dowodu regresji. [GATE-09](GATE09_MAINTAINER_ACCEPTANCE.md) jest zachowany dla dotychczasowego ograniczonego zakresu wydania, nie stanowi certyfikacji ONTOS L7–L12.

Kolejność: istniejące niezależne reszty v22, v24–v28, v31–v34; bazowe v37–v48 według zależności; następnie integracja Phase0 v49–v54, L8 v55–v58, L9 v59–v62, L10 v63–v67, L11 v68–v71, L12 v72–v75, post-Ω∞ v76–v80. Możliwa równoległa realizacja niezależnych zadań bez tworzenia innych gałęzi, przy zachowaniu atomowych odbiorów. Numery v49–v80 są decyzją projektową niniejszej rewizji, nie numeracją Argona. Status każdego nowego etapu OPEN.

Zakres operacyjny nie rozszerza zgody operatora. Nie zmieniamy harmonogramu, mechanizmów autoryzacji, zabezpieczeń ani produkcyjnego ewaluatora. Eksperymenty nie otrzymują poświadczeń, nie tworzą procesów samomodyfikujących się, nie wykonują generowanego kodu hosta, nie mogą modyfikować weryfikatora, nie rozszerzają praw. Brak dowodu oznacza brak dopuszczenia; nieznany wynik nie jest PASS. Testy deterministyczne mogą zastąpić niedostępne podłoże w zakresie wiernie modelowanego kontraktu; nie zastępują matematycznego dowodu, którego wymaga kryterium, ani nie są dowodem wdrożenia. Żadnych płatnych zleceń, rzeczywistego QPU/FPGA DFX ani zewnętrznych wdrożeń w tej zgodzie.

## 2. Źródłowy stan dowodowy

S2, Tom I, XI–XIII: Argon deklaruje wykonanie 1080 głównych i 720 ablacyjnych epizodów (1800 łącznie, 486,72 s), 4 suity × 30 ziaren i symulatory sześciu podłoży. L7_baseline jest rekonstrukcją, nie oryginalnym L7. Rust/Zenoh, RTL, Lean, SMT, egglog, MLIR i WIT nie mają w raporcie kompletnej natywnej weryfikacji. Zachowujemy te wyniki jako SOURCE-REPORTED. Dla wszystkich nowych etapów repozytorium wymagamy dowodów powiązanych z jego SHA.

| Miara S2 | L7-Phase0 | L8 | L9 | L10–L12 |
|---|---:|---:|---:|---:|
| Przeżycie A/B/C/D | 30/30 każda | 30/30 każda | 30/30 każda | 30/30 każda |
| Trafność A | 91,51% | 90,25% | 90,25% | 90,25% |
| Trafność B | 92,21% | 91,15% | 91,15% | 91,15% |
| Trafność C | 90,74% | 90,17% | 90,17% | 90,17% |
| OOD recall C | 0% | 38,5% | 38,5% | 38,5% |
| Trafność D | 74,31% | 72,93% | 89,71% | 90,79% |
| Zdrowie organelli D | 0,44 | 0,44 | 0,93 | 0,93 |
| Śr. FLOPs A (wg źródła) | 373,5k | 793,2k | 710,8k | 710,8k |

S2 podaje zero Goodharta dla Phase0–L12. Nie jest to uniwersalna gwarancja. Wzrost OOD i odporności D współwystępuje z narzutem obliczeń i spadkiem trafności A/B. Nie wolno ukrywać tego kompromisu. Symulacje SOT-MRAM 11,69 nJ, p-bit 1,14 nJ i H100 167,13 nJ dotyczą założeń 350 000 operacji; nie są pomiarem z gniazdka.

## 3. Faza 0 i ponowne powiązanie v37–v48

Poniższe dziesięć kontraktów P0-01–P0-10 to rekonstrukcja wymagań na podstawie Tomów I, III, V i listingów X.7–X.22, nie deklaracja dokładnego odtworzenia numeracji pierwotnego audytu. Każdy musi mieć test na rzeczywistym komponencie repozytorium. Powtórny test integracyjny nie oznacza ponownej implementacji już przyjętego modułu.

| ID | Defekt / zobowiązanie | Etap bazowy | Nowa bramka |
|---|---|---|---|
| P0-01 | Zanik przekonań: ziarno 9274, predykcja B_eff i dodatnia podłoga po normalizacji | v39 | v50 |
| P0-02 | Skażenie atraktorów: ziarna 9216 i 9651, niezależna ocena przed konsolidacją | v44 | v51 |
| P0-03 | Oddzielenie prawdy symulatora od obserwacji i niezależny holdout | v37/v48 | v49/v54 |
| P0-04 | Memory Skepticism: historia wiarygodności i odwracalna konsolidacja | v44 | v51 |
| P0-05 | Przegląd PACE/VaG oraz długotrwałego zapisu | v46 | v51 |
| P0-06 | Wywołanie rzeczywistych klas w eksperymencie zamiast liczników zastępczych | v40–v44 | v53 |
| P0-07 | Uczciwe rozliczenie kosztu operacji, budżetu i jednostek | v38 | v53 |
| P0-08 | ATLAS Omega i hierarchiczne podcele JEPA w skończonych zadaniach lokalnych | v43 | v52 |
| P0-09 | Norm-preserving OOD: udokumentować ślepotę bazową i odrębnie sprawdzać detekcję | v46 | v54/v58 |
| P0-10 | Kompletność pamięci, bitemporalności i pochodzenia dowodów | v42/v44 | v52 |

## 4. Roadmapa wykonawcza v49–v80

Wszystkie poniższe etapy mają status OPEN. „S” oznacza wymaganie źródłowe; „E” oznacza dodatkowe proponowane rozszerzenie, a nie zacytowany wynik Argona. Proponowane lokalizacje: omega_x_evolution/ontos_research/ dla izolowanych, czystych modułów i tests/test_ontos_vNN_*.py dla testów. Istniejące moduły wykorzystywać przez ich rzeczywiste kontrakty, bez zastępowania silnika ani kopiowania monolitu. Każde zadanie ma oddzielny dowód odbioru.

### Phase0 — v49–v54 (S2, Tom I, X, XI; poprzednik v37–v48)

| Etap / proponowane pliki | S: wymaganie i zależności | E: rozszerzenie i kryterium odbioru |
|---|---|---|
| v49 source_ingest.py, test_ontos_v49_source.py | Manifest 33 listingów; v37 | Kontrolowany import źródła po przeglądzie, SHA każdego pliku, stos zależności i licencje; 33/33 pozycji z dyspozycją REUSE/PORT/REJECT/RESEARCH i uzasadnieniem. Niezaufane listingi nie są wykonywane. Testy zniekształceń PDF, braków i kolizji nazw. |
| v50 belief.py, test_ontos_v50_belief.py | P0-01, v39; B_eff, prior mix 0,06, ε=1e-4 | Jawna definicja podłogi po normalizacji, kontrola skończoności i sumy; długie ślady zera, skrajne likelihood i ziarno 9274; porównanie z niezależną referencją o większej precyzji. |
| v51 memory_evidence.py, test_ontos_v51_memory.py | P0-02/04/05, v44/v46; PACE/VaG, Memory Skepticism | W izolowanym zbiorze prototypów audyt statystyczny e-procesu, kontrola wielokrotnych prób, korelacji i fałszywej konsolidacji; niezmienne ślady dowodowe, brak publikacji do pamięci operacyjnej. Ziarna 9216/9651 i przypadki błędnych etykiet. |
| v52 temporal_contracts.py, test_ontos_v52_temporal.py | P0-08/10, v42/v43/v44; Titans/JEPA/VSA/NARS/KG | Recenzja zgodności zegarów 1/6/24 i okna 4; obie osie czasu, korekty wsteczne, niezależność dowodów; powtarzalna retencja na małym zbiorze; ponowne użycie graph_memory.py i holographic.py. Nie utożsamiać uproszczonej pamięci z produkcyjnym HOPE. |
| v53 accounting.py, test_ontos_v53_accounting.py | P0-06/07; v38/v40; FLOPsCounter | Instrumentacja obejmuje inferencję i aktualizacje, QR/SVD/LP, oddzielne koszty pamięci i I/O; walidacja licznika dla znanych jąder; jawne UNKNOWN dla niepoliczonych operacji; rezerwacja przed wykonaniem w testbedzie; powiązanie z green.py. |
| v54 phase0_replay.py, test_ontos_v54_replay.py | v49–v53, v48; suity A/B i bazowa C | Zamrożony comparator i seedy; scorer poza observation API; per-seed log, replay, uwzględnienie abstynencji i awarii. Cel źródłowy 30/30 w A/B, ≥91% wg tej samej definicji i zero symulowanych lure hits. Raportować niepowodzenia, nie dostrajać holdout. |

### L8 — przyczynowość i epistemika, v55–v58 (S2, Tom II–IV, VII, X.11)

| Etap / proponowane pliki | S: wymaganie i zależności | E: rozszerzenie i kryterium odbioru |
|---|---|---|
| v55 causal_contract.py, test_ontos_v55_scm.py | Obserwacje i interwencje SCM; v54 | Ocena identyfikowalności na skończonych, jawnie określonych modelach; osobno obserwacja i do(a), brak ukrytych etykiet, testy confounding i brak danych. Nie twierdzić, że log obserwacyjny jest interwencją. |
| v56 harm_bounds.py, test_ontos_v56_lp.py | Balke–Pearl LP [l,u], v55 | Dwa niezależne orakle małych tabel, jawne ograniczenia i niepewność danych; p00=0, sprzeczne marginesy i brak identyfikacji → UNKNOWN/[0,1]; nie dopuszczać działań na podstawie fikcyjnych marginesów. |
| v57 causal_metrics.py, test_ontos_v57_metrics.py | VoI, EI i przyczynowe pomiary; v45/v55 | Znane analityczne przykłady informacji, rozdzielić mutual information od empowerment; sprawdzić jednostki i szum, raportować brak niezależnej identyfikacji. Tylko skończone dane eksperymentalne. |
| v58 ood_evaluation.py, test_ontos_v58_ood.py | Vietoris–Rips/dDCA i Suite C; v54–v57 | Rzeczywista ocena separowalności, nie nazywać prostego NN wynikiem homologii trwałej; skalibrowane raporty ROC/PR, false-positive i coverage. Cel E (nie wynik): recall ≥70% w zamrożonej C i FPR ≤5% z przedziałami ufności, bez zwiększania praw. Nie zastępować istniejących barier bezpieczeństwa detektorem. |

### L9 — substrat i odporność, v59–v62 (S2, Tom III–V, X.9–X.10)

| Etap / proponowane pliki | S: wymaganie i zależności | E: rozszerzenie i kryterium odbioru |
|---|---|---|
| v59 oscillator_reference.py, test_ontos_v59_numeric.py | Niskorangowy Kuramoto-CTM; v40/v53 | Weryfikacja matematyczna i numeryczna istniejącego wzoru na skończonych macierzach, osobno przypadek bez wymuszenia i z wymuszeniem; test kroku całkowania, tolerancji i symetrii. Nie przenosić gwarancji Lapunowa na dowolny dyskretny krok. |
| v60 sheaf_reference.py, test_ontos_v60_sheaf.py | Dyfuzja snopów, v59 | Zgodność z małymi jawnie złożonymi macierzami, energia przed/po, izolacja uszkodzeń i przypadek źle uwarunkowany; próbkowanie profilu kosztu z jawnie podaną szerokością. |
| v61 fault_testbed.py, test_ontos_v61_faults.py | BraiNCA, (M,R), TAME; v41/v54 | Symulacja awarii stałej siatki, równoczesne uszkodzenia, brak zasobów, rollback stanu danych; zero samonaprawy kodu/procesów. Oceniać odzyskanie stanu, nie sam wskaźnik health. |
| v62 memory_noise_bench.py, test_ontos_v62_noise.py | Kinetic Proofreading, v51/v52 | Sprawdzić p_err^(m+1) wyłącznie przy niezależności; wprowadzić skorelowany szum i drifty jako testy falsyfikujące. Docelowe 89,71% trafności D i health 0,93 wg źródła, raport obu metryk z kosztem. |

### L10 — formalna kompatybilność i izolacja, v63–v67 (S2, Tom IV, VII–VIII, X.14, X.23–X.31)

| Etap / proponowane pliki | S: wymaganie i zależności | E: rozszerzenie i kryterium odbioru |
|---|---|---|
| v63 finite_interface_model.py, test_ontos_v63_interface.py | PolyTr_U/WIT, kanały A–E; v42/v47 | Skończony model stanów i śladów, monotoniczna redukcja w obrębie transakcji; restart nie przywraca praw. Model nie przyznaje realnych capabilities. Testy LOCKDOWN, błędów ramek, przeterminowania; niezależna kontrola nieinterferencji. |
| v64 ir_certificate_review.py, test_ontos_v64_ir.py | UIR, egglog/MLIR/CIRCT, EqSat/MDL; v26/v28/v31/v47 | Reuse proof_kernel.py, bitproof.py i lean_native.py; tylko czyste IR i statyczne fixture. Cztery próbki nie są dowodem; test znanych kontrprzykładów, floating point i modularne domeny oddzielnie. Zewnętrzny certyfikat wiązany z dokładnym IR i wersją semantyki. |
| v65 trace_noninterference.py, test_ontos_v65_traces.py | Bezalternacyjny HyperLTL, SMT; v63/v64 | Rozróżnić deklarowane zbiory zapisu od rzeczywistych obserwacji śladów; model skończony, self-composition, konflikt RAW/WAR/WAW, wyczerpanie limitu → UNKNOWN. Stały evaluator bez zmian. |
| v66 transport_contracts.py, test_ontos_v66_transport.py | Rust/Zenoh/WASI, v47/v63 | Model kontraktowy serializacji, wersjonowania, awarii/replay i opóźnienia; natywna kompatybilność osobno, jeżeli dostępna. Limit źródłowy IPC <1 ms jest fizycznym celem testowym, nie rezultatem symulacji. Bez nowej usługi. |
| v67 rtl_model.py, test_ontos_v67_rtl.py | FPGA DFX, static shell, CIRCT LEC; v64/v65 | Wyłącznie statyczny testbed RTL/DFX bez generowania wdrażalnych zmian urządzenia; ślady reset/timeout/awaria, dowody równoważności dla ustalonych jąder, fail-closed. ≤2,5 ms jest źródłowym celem ICAP, nie poświadczeniem sprzętowym. |

### L11 — termodynamika i heterogeniczne podłoża, v68–v71 (S2, Tom III, V–VI, X.12/X.18)

| Etap / proponowane pliki | S: wymaganie i zależności | E: rozszerzenie i kryterium odbioru |
|---|---|---|
| v68 si_units.py, test_ontos_v68_units.py | GΩ+ w J, v38/v53/v57 | Zweryfikować bity/naty, T>0, termodynamiczne granice kasowania; odrębnie operacje i bity, bez automatycznego utożsamiania FLOP z wymazaniem. Test skali, sumowania i porządku raportowanych miar. |
| v69 substrate_model.py, test_ontos_v69_substrate.py | Sześć podłoży, v68 | Model wall-plug, ADC/DAC, memory traffic, chłodzenie, zużycie i niepewność kalibracji. Zakres parametrów i scenariusze skrajne; odtwarzanie źródłowych liczb jako scenariusza, nie pomiaru. |
| v70 endurance_model.py, test_ontos_v70_endurance.py | SOT-MRAM/s-MTJ/RRAM i trwałość, v69 | Symulacja rozkładu zapisów, wear-out i awarii, fizyczne jednostki i warunki graniczne; założenie pięciu lat przy 100 Hz sprawdzić na profilu zapisów, nie uznać za osiągnięte sprzętowo. |
| v71 energy_pareto_report.py, test_ontos_v71_pareto.py | Źródłowa granica ≤15 nJ dla 350k operacji, v68–v70 | Ocena porównawcza przy równych zadaniach i poprawności; przedziały kosztów, analiza wrażliwości i Pareto; raportować przecięcie przedziałów bez obietnicy przewagi. Cel E: kompletność rachunku w całym eksperymencie. |

### L12 — pełna integracja dowodowa, v72–v75 (S2, Tom VII–XII, X.5/X.13/X.25/X.30/X.31)

| Etap / proponowane pliki | S: wymaganie i zależności | E: rozszerzenie i kryterium odbioru |
|---|---|---|
| v72 receipt_contracts.py, test_ontos_v72_receipts.py | HMAC/Merkle, RFC 8785, profile Ed25519/ML-DSA/SLH-DSA i ML-KEM; v63/v66 | Offline test vectors, kanoniczność, separacja kluczy testowych i odrzucanie uszkodzeń; digest nie jest podpisem PQC, ML-KEM to ustanawianie klucza, nie podpis. Zewnętrzne biblioteki wymagają natywnej kwalifikacji. Bez zmiany produkcyjnego korzenia zaufania. |
| v73 isolation_evidence.py, test_ontos_v73_isolation.py | T_ext ≠ T_obj i kanały A–E, v65–v72 | Dowody na skończone modele i istniejące granice izolacji, testy negatywne dla dostępu do hosta/sieci/kluczy/evaluatorów. Nie utożsamiać prywatnego pola obiektu z izolacją procesu. |
| v74 campaign_report.py, test_ontos_v74_campaign.py | Pełne Suity A–D, 30 ziaren, ablacje; v54/v58/v62/v67/v71/v73 | Raport z 1080+720 źródłowych konfiguracji po zamrożeniu protokołu, osobne rozliczenie generacji, paired bootstrap/permutation z korektą wielokrotnego testowania, bez selekcji korzystnych seedów. Publikacja zagregowanych pomiarów i niezmiennych artefaktów, bez automatycznej promocji. |
| v75 integration_acceptance.md, test_ontos_v75_contracts.py | Wydanie badawcze L12, v72–v74 i wszystkie obowiązujące zależności | Weryfikacja 33/33 pozycji manifestu, pokrycie wymagań, zgodność licencyjna, testy odzyskania, TCB i dowody niezmienione; osobne NATIVE/SIMULATION/HYBRID. GATE-09 nowego zakresu wyłącznie po wszystkich obowiązujących bramkach. |

### Post-Ω∞ — rozszerzenia autorskie E, v76–v80 (S2, Tom XIV)

Te etapy nie tworzą nowej certyfikowanej generacji L13. Stanowią rozszerzenie metodologii i rygoru w dziedzinach wskazanych jako otwarte. Zakaz współewolucji weryfikatora, przyznawania uprawnień, automatycznej migracji TCB i samodzielnej egzekucji rezultatów.

| Etap / proponowane pliki | Rozszerzenie | Kryterium odbioru |
|---|---|---|
| v76 ood_benchmark_registry.py, test_ontos_v76_ood_cases.py | Zewnętrzny względem modelu rejestr testów semantycznej spójności i niezmienności względem transformacji, v58/v74 | Odrębny zamrożony zbiór falsyfikacji, pokrycie klas błędów, worst-group recall/precision, koszt i ryzyko błędnej abstynencji. E: recall ≥85% jako cel badawczy przy FPR ≤5%, z zakazem dostrajania do testu. |
| v77 planning_evaluation.py, test_ontos_v77_planning_eval.py | Ocena istniejących podcelów JEPA w skończonych światach, v52/v74 | Niezależny oracle dla małych przestrzeni, koszt i sukces w kilku horyzontach, błędy poza rozkładem; badanie ograniczeń, bez otwartego generowania realnych celów. |
| v78 proof_evidence_catalog.py, test_ontos_v78_proof_catalog.py | Archiwum krzyżowej weryfikacji niezależnych dowodów, v64/v65/v73 | Weryfikatory zewnętrzne względem badanego programu pozostają zamrożone; różne reprezentacje jednego twierdzenia sprawdzane bez migracji TCB, brak dowodu → UNKNOWN. Nie implementować samoweryfikującej się zmiany interpretera. |
| v79 local_learning_measure.py, test_ontos_v79_energy.py | Rachunkowość fizycznego uczenia kontrastowego, v68–v71 | Symulacja bilansu energetycznego układów referencyjnych, jawne granice i koszty odzysku; porównanie ilościowe bez przypisywania potencjału sprzętowi, którego nie testowano. |
| v80 reproducibility_release.md, test_ontos_v80_replay.py | Długoterminowa reprodukcja i audyt jakości dowodów po L12 | Manifest danych/narzędzi/testów z SHA, dwie niezależne rekonstrukcje z zachowaniem tolerancji, pełne rozliczenie regresji i decyzji; brak automatycznej akceptacji przez model. |

## 5. Pełna identyfikowalność 33 plików S2 (Tom IX–X)

Poniższy rejestr nie jest deklaracją, że pliki z PDF istnieją już w repozytorium. Nazwy zachowano zgodnie z manifestem źródła. Żaden listing nie ma domyślnego statusu zaufanego kodu.

| Nr z X | Ścieżka źródłowa | Docelowy etap integracji / przeglądu |
|---|---|---|
| 1 | README.md | v49, v75 |
| 2 | pyproject.toml | v49; istniejący manifest pozostaje nadrzędny |
| 3 | requirements-lock.txt | v49; poprawność składni, wersje, hashe |
| 4 | config/ontos_l12_config.json | v49, v54 |
| 5 | schemas/telemetry_schema.json | v63, v72 |
| 6 | src/omega_ontos/__init__.py | v49; brak nowego drugiego runtime |
| 7 | src/omega_ontos/types.py | v50, v53, v63 |
| 8 | src/omega_ontos/poly_interface.py | v63 |
| 9 | src/omega_ontos/cognitive_substrate.py | v59–v61 |
| 10 | src/omega_ontos/living_memory.py | v51, v52, v62 |
| 11 | src/omega_ontos/causal_engine.py | v55–v57 |
| 12 | src/omega_ontos/thermodynamics.py | v68–v71 |
| 13 | src/omega_ontos/immune_kernel.py | v51, v58, v65, v72–v73; przegląd offline |
| 14 | src/omega_ontos/uir_evolution.py | v64 |
| 15 | src/omega_ontos/organism.py | v53–v54, v74; tylko testbed |
| 16 | simulators/__init__.py | v49 |
| 17 | simulators/environments.py | v54, v61 |
| 18 | simulators/hardware_substrates.py | v69–v71 |
| 19 | benchmarks/__init__.py | v49, v74 |
| 20 | benchmarks/run_benchmarks.py | v54, v74 |
| 21 | tests/__init__.py | v49 |
| 22 | tests/test_ontos_suite.py | v50–v75 |
| 23 | interfaces/wit/ontos_poly.wit | v63, v66 |
| 24 | runtime/rust_zenoh_core/Cargo.toml | v66 |
| 25 | runtime/rust_zenoh_core/src/main.rs | v66, v73; test kontraktów |
| 26 | compiler/mlir/ontos_uir.mlir | v64, v67 |
| 27 | compiler/egglog/uir_eqsat.egg | v64 |
| 28 | hardware/rtl/static_shell_guard.sv | v67 |
| 29 | hardware/rtl/dfx_cfc_accel.sv | v67 |
| 30 | formal/lean4/OntosInvariants.lean | v63, v65, v78 |
| 31 | formal/smt/hyperltl_noninterference.smt2 | v65 |
| 32 | scripts/compute_manifest_sha256.py | v49, v80 |
| 33 | scripts/verify_all.sh | v75, v80; rozróżnić SKIP/BLOCKED/PASS |

## 6. Audyt dokumentu S2: defekty i granice deklaracji

To statyczny przegląd listingów, nie wykonane reprodukcje testów. Wnioski wyznaczają dodatkowe testy i nie są podstawą wprowadzenia zmian bez weryfikacji.

| ID | Lokalizacja | Problem do sprawdzenia | Odbiór |
|---|---|---|---|
| A01 | X.3 | Ekstrakcja PDF lockfile może zgubić operatory wersji; zakaz zgadywania oryginalnych bajtów | v49 |
| A02 | X.15 | max(prior*likelihood, ε), potem normalizacja: deklarowana podłoga ε wymaga dowodu po normalizacji | v50 |
| A03 | X.13/X.10 | Czynnik sukcesu PACE 2,3 i porażki 0,4 przy p0=0,25 daje oczekiwanie 0,875 przed obcięciami; floor/cap i selekcja prób zmieniają proces; potrzeba jawnej hipotezy i kontroli powtarzania | v51 |
| A04 | X.10/X.15 | KG zapisuje recorded_at, ale query_at nie rozdziela osi transakcji; test bitemporalny i historia korekt konieczne | v52 |
| A05 | X.15 | Rozliczenie ledger następuje przed observe_outcome, gdzie są dalsze aktualizacje; SVD i LP nie są kompletnie naliczane | v53 |
| A06 | X.7/X.15/X.17 | ObservationPacket zawiera prawdę o OOD/reżimie, fault flags, a wynik correct/new_state_est jest dostarczany przez środowisko; sprawdzić wycieki oraz zakres legalnego feedbacku w benchmarku | v54 |
| A07 | X.11/X.15 | LP okresowo otrzymuje stałe 0,04/0,03, między wywołaniami harm_u=0,02; zakres bez danych musi pozostać nieznany | v55/v56 |
| A08 | X.15 | macro_ei=emp_bits; EFE i information gain przekazywane z log naturalnych do pól bits; decyzja oparta na g_norm, nie total_G_omega_J; raport typu i jednostki wymagają niezależnej kontroli | v57/v68 |
| A09 | X.13 | Nearest-neighbor ratio nie wystarcza do pełnej homologii trwałej; SAE/dDCA nie są gwarancją bezpieczeństwa | v58 |
| A10 | X.9 | Symetria J=UUᵀ nie gwarantuje spadku energii przy naturalnych częstościach, wymuszeniu i dowolnej dyskretyzacji | v59 |
| A11 | X.8 | Przynależność caps do root_universe nie dowodzi monotoniczności kolejnych przejść; ograniczenia wykonawcze muszą pozostać zewnętrzne | v63 |
| A12 | X.14 | Cztery punkty testowe nie są dowodem równoważności; fma w kodzie to osobne mnożenie i dodawanie; nie wolno nazywać wyniku formalnym certyfikatem | v64 |
| A13 | X.13/X.15 | Zbiory nazw zapisów nie stanowią ogólnego HyperLTL; scenariusz konfliktu używa znanych z góry konfliktowych zbiorów | v65 |
| A14 | X.12 | N_ops nie jest liczbą bitów wymazanych; korekta podwójnego liczenia, kosztów i wspólnej jednostki | v68 |
| A15 | X.13 | Domyślny publiczny secret_key, json.dumps zamiast pełnego RFC 8785, SHA3 digest zamiast PQC i łańcuch hashy zamiast pełnego dowodu Merkle | v72; nie używać produkcyjnie |
| A16 | X.13/X.15 | Jądro i organizm w tym samym procesie; zliczenie trybu symulacyjnego nie dowodzi fizycznej separacji ani blokady ataku | v73 |
| A17 | Tom XI | Dane generacji L10–L12 agregowane, syntetyczne baselines i rekonstrukcja L7; statystyka musi uwzględnić wspólne ziarna, cenzurowanie i wielokrotne porównania | v74 |

## 7. Kontrakty wykonawcze i odbiór

Wszystkie nowe moduły mają być małe, czyste i testowalne. Proponowany kierunek interfejsów testbedu: immutable Observation (tylko dane dostępne w danej chwili) → istniejący, ograniczony model eksperymentalny → Proposal (skończona domena symulowana) → zewnętrzny, niezmieniany evaluator → Outcome → log i komplet dowodów. GroundTruth pozostaje w evaluatorze. Raporty nie są certyfikatami wdrożenia. Nie stosować niejawnych fallbacków, przekroczeń budżetu ani modyfikacji środowiska podczas prób.

Dla każdego vNN: zapis testów RED/GREEN, lokalne polecenie python -m pytest -q na konkretnych rzeczywiście utworzonych testach, compileall modułu, regresja dotkniętych kontraktów, SHA wejścia/wyjścia oraz wersje środowiska. Brak dostępnego natywnego toolchainu: oznaczyć NATIVE-BLOCKED i wykonać deterministyczny model tylko właściwej części kontraktu. Wzorzec rejestru: requirement_id, source_section, base_sha, code_blob, test_id, seed, environment, command, exit_code, evidence_sha256, verification_mode, verdict, limitations. Artefakty i logi przechowywać z kontrolą integralności. Zmiany wyłącznie na main, bez force push; sprawdzić zegar i HEAD przed modyfikacją, nie publikować niezweryfikowanej implementacji.

Bramki GATE-01 wymagania → 02 architektura → 03 implementacja → 04 testy → 05 integracja → 06 bezpieczeństwo → 07 recovery → 08 dowody → 09 odbiór. Obowiązkowe kryterium nie może być zastąpione wynikiem statycznej analizy. Brak natywnego sprzętu nie blokuje przyjęcia poprawnego modelu; nie zmienia statusu fizycznego. W żadnej fazie nie deklarować absolutnego bezpieczeństwa, świadomości, globalnej niesprzeczności, pełnej autonomii ani dowolnego udowodnionego przyśpieszenia.

## 8. Horyzont źródłowy i kolejność prac

S2 Tom XII: Phase0 Q4 2026; L8–L9 2027; L10 2027–2028; L11 2028–2031; L12 2031–2035+. Traktujemy te daty jako projekcję źródłową, nie zobowiązanie dostawy. Testy kontraktowe można wykonać wcześniej niż dostępność fizycznego sprzętu. Nie obiecywać dat wdrożenia i nie uruchamiać płatnych usług.

Następny etap nowej linii: v49 (odzysk i kontrola manifestu) oraz v37 (testbed), po których następuje walidacja Phase0 zgodnie z zależnościami. Dotychczasowa kolejka v22–v34 nadal obowiązuje. Nie zmieniamy istniejącej automatyzacji ani ramy 20.11.2026 08:26 CET – 21.11.2026 08:26 CET. Dalsze wykonanie poza tą ramą wymaga nowej autoryzacji. Niniejsza zmiana dotyczy wyłącznie dokumentacji.


**v37–v39 bounded offline reference:** [implementation and test evidence](ONTOS_V37_V39_REFERENCE.md), [30-seed campaign](v37-campaign.json). 42 focused tests PASS, 7200 fixed-tape steps reproducible. v37 environment subset TESTED (full source reproduction OPEN); v38 finite thermodynamic-accounting contract PASS; v39 finite information diagnostics PASS (full integrated decision loop OPEN). No change to operational code, evaluator or existing GATE-09. Full repository regression unavailable. Historical OPEN labels remain historical; this entry governs the tested subsets.


**v40–v42 — sampled numerical and finite logic reference:** [TDD and integration evidence](ONTOS_V40_V42_REFERENCE.md). 39 new tests plus 42 prior subset regressions PASS (81 total). v40 sampled CfC/CTM reference PASS, native compatibility OPEN; v41 bounded data repair/contraction and 15% reserve PASS, actual TAME competence measurements OPEN; v42 finite Poly/Heyting/NARS evidence contracts PASS, broader inference and authenticated provenance OPEN. No runtime capability changes. Existing bounded GATE-09 preserved. Full upstream regression unavailable. Next v43–v45; all earlier residuals retained.


**v43–v45 — offline evidence references:** [test evidence](ONTOS_V43_V45_REFERENCE.md). 36 new tests + 81 prior ONTOS regressions = 117 PASS. v43 fixed synthetic multirate regression audit TESTED (native Titans/HOPE/JEPA and continual-retention integration OPEN); v44 immutable bitemporal snapshot and Hopfield/VSA diagnostics TESTED (durable integration and authenticated provenance OPEN); v45 exact tiny assembly and finite EI/CP reference PASS within stated model (general assembly and causal inference OPEN). No operational adaptation, promotion or changes to evaluator or privilege controls. Full upstream regression unavailable. Existing bounded GATE-09 preserved; all previous residuals retained.


**v43/v46 — independent zero-gradient and statistical audit:** [focused evidence](ONTOS_V43_V46_ANALYTIC_AUDIT.md). Nine new tests PASS; 30 synthetic seeds replay identically; exact 4096-path null enumeration exposes wealth-floor counterexample. v43 and v46 sub-contracts TESTED only, actual frozen-model integration and remaining v46 diagnostics OPEN. v47/v48 not completed. No private source publication, operational change or new GATE-09 acceptance. Full repository regression unavailable.


**v46–v48 — audyt statystyczny, skończony IR i kampania referencyjna:** [implementacja i TDD](ONTOS_V46_V48_INCREMENT.md). 40 nowych testów PASS, dokładny null z 4096 ścieżek, pełne sprawdzenie i4 na 256 parach, 30 nasion × 4 stałe taśmy × 240 kroków = 28 800 kroków, 20 dev / 10 holdout. Zgodność z przypiętym v37 (1788 poprawnych i 678 OOD, SHA śladów). **TESTED wyłącznie ograniczone podkontrakty**, całość v46–v48 OPEN: brak natywnego MLIR/egglog/Rust/WASI, pełnego PACE/GSAI/SAE i adaptacyjnej ewaluacji L7. Brak zmiany praw, evaluatorów i istniejącego GATE-09.


**Phase0 v49–v51 (2026-11-20) — [kod i dowody](ONTOS_V49_V51_PHASE0.md):** 33/33 nazw źródeł zidentyfikowanych w [rejestrze](V49_SOURCE_MANIFEST.json), 0/33 faktycznych plików źródłowych odzyskanych/weryfikowanych, wszystkie wpisy RESEARCH/UNKNOWN (brak automatycznej promocji). v49: kontrolowane bajty+SHA/ścieżki/licencja TESTED; v50: podłoga posterior ε=1e-4 po normalizacji, abstencja i 30-seed replay TESTED; v51: kwarantanna, korekty bitemporalne, źródła/tenant/grupy TESTED. **51 nowych + 40 regresyjnych = 91 PASS w lokalnym wycinku**, pełna regresja/integracja nieuruchomione. Szersze v49–v51 pozostają OPEN, historyczny ograniczony GATE-09 PASS bez zmian. Następne v52–v54.


**Phase0 v52–v54 (2026-11-21):** [implementacja i TDD](ONTOS_V52_V54_PHASE0.md). v52: model dwóch osi czasu, zegary 1/6/24 i cztery okna, walidacja korekt i migawki TESTED (produkcyjna pamięć/uwierzytelnienie OPEN). v53: rezerwacja i niezmienna księga opłat za modelowe jednostki obliczeń i bajty I/O TESTED (**prawdziwe FLOPs/energia UNKNOWN**, instrumentacja OPEN). v54: odtworzenie stałych Suite A/B na 30 seedach × 240 kroków × 2 = 14 400, 20 dev/10 holdout, A=1788/7200 (24,83%), B=1817/7200 (25,24%), 60 nierozliczonych fizycznie opłat; kryterium źródłowe trafności ≥91% **FAIL**, nowy GATE-09 nieprzyznany. 25 nowych + 91 wcześniejszych = **116 lokalnych testów PASS**, compileall PASS. Pełna regresja i integracja natywna OPEN, wszystkie zaległe wymagania zachowane, historyczny ograniczony GATE-09 PASS bez zmian. Kolejne v55–v57.


**ONTOS L8 v55–v58 (2026-11-21)** — [implementacja i testy](ONTOS_V55_V58_L8.md), [Suity C holdout](V58_SUITE_C_HOLDOUT.json), [SHA-256](V55_V58_SHA256SUMS). v55: binarne SCM, 16 latentnych typów i kontrola `observation`≠`do(X)` TESTED; v56: numeryczne przedziały Balke–Pearla (HiGHS dual simplex/IPM, infeasible→UNKNOWN/INFEASIBLE bez fikcyjnego efektu) TESTED; v57: VoI/EI/pojemność kanału ze świadomą separacją jednostek TESTED; v58: H0 Vietorisa–Rips na 32-punktowych kohortach i zamrożony OOD holdout 10/10/10 nasion, 2 400 prób, recall 246/247=99,60%, FPR 101/2153=4,69%, ROC AUC 0,99824; 95% CI FPR 3,88–5,67% → **confidence gate FAIL**, promocja niedozwolona. **48 nowych + 116 regresyjnych = 164 PASS** w lokalnym wycinku, compileall PASS. Pełne dDCA, wymagania natywne, generalizacja i operacyjna integracja pozostają OPEN. Historyczny ograniczony GATE-09 PASS bez zmian; nowy L8 GATE-09 niezaliczony. Następne v59–v62.


## ONTOS L9: v59–v62 (2026-11-21, ograniczone podkontrakty)

[Implementacja i dowody](ONTOS_V59_V62_L9.md) · [Kampania L9, SHA z ZIP](ONTOS_V59_V62_L9_SUMMARY.json) · [Diagnostyka ziaren](PHASE0_FAILURE_SEEDS_SUMMARY.json). v59: low-rank symmetric Kuramoto, siła O(nr), 100 kroków w modelu, potencjał 0,7243034→0,1086437 (TESTED); v60: snopowa dyfuzja z restrykcjami, 100 kroków, E=8,0625→0,1921434 (TESTED); v61: rzeczywisty kod v41 RepairState, 30 seedów i 2 symultaniczne usterki/seed, 31,87% modelowej kontrakcji oraz 15% rezerwy (TESTED); v62: 7200 prób korekty szumu, 14 fałszywych akceptacji w modelu niezależnym i 942 w wariancie skorelowanym (TESTED). **220/220 lokalnych testów PASS**, 164 wcześniejsze + 56 nowe; compileall PASS, reprodukcja po rozpakowaniu ZIP PASS. Nie jest to natywne L9 ani potwierdzenie SOURCE Suite D 89,71%/health 0,93. Pełny L9 GATE-09 OPEN; historyczny ograniczony GATE-09 PASS niezmieniony. Regresja całego upstream repo nieuruchomiona.

## Nowe rozszerzenia v81–v87 — wymagana realizacja po zależnościach

Dokumentacja: [EXT-01..07 i kryteria](ONTOS_EXTENSIONS_V81_V87.md), [diagram sekwencji A–E](ONTOS_CHANNELS_A_E_SEQUENCE.md), [tabela energetyczna peak / core / wall-plug](ONTOS_ENERGY_BOUNDARIES.md). Uzupełnienia nie skreślają v1–v80 i stanowią **obowiązkowe nowe wymagania**, nie osiągnięcia:
- **v81** (v63/v65): model sekwencji kanałów A–E i pre-commit; dokument diagramu TESTED, runtime/izolacja TCB OPEN. Wymagane walidacja ramek, timeout, E-LOCKDOWN, niezmienność Caps.
- **v82** (v49–v54): pełne ślady ziaren 9216/9274/9651, log obserwacji oddzielony od scorera, SHA, skrypt odtwarzania; syntetyczne zrzuty TESTED, reprodukcja błędów oryginalnego źródła OPEN. Zrzuty surowe w ZIP, manifest z SHA w repo.
- **v83** (v68–v71): separacja mocy akceleratora [W] od wall-plug [W] i E_core/E_wall [J]; specyfikacja jednostek TESTED, fizyczna kalibracja i symulacje ADC/DAC/PSU/chłodzenia OPEN.
- **v84** (v42/v63): PolyTr_U, dynamiczna adjunkcja w kategorii fibrowanej, bezpieczna rekonfiguracja koindukcyjna, monotonia uprawnień i rollback, model checking → OPEN.
- **v85** (v38/v53/v68–v71): zdarzeniowy model Landauer-Bounded Free Energy z deterministyczną kolejką, rezerwacją pracy i modelami SOT-MRAM, bez urojonych fizycznych oszczędności → OPEN.
- **v86** (v65/v73): HyperLTL ∀* dla współbieżnych śladów; self-composition i RAW/WAR/WAW na ograniczonej domenie, UNKNOWN dla limitów, bez deklaracji uniwersalnej eliminacji konfliktów → OPEN.
- **v87** (v64/v67/v72–v73): synteza wyłącznie kandydata RTL i niezależna LEC/Z3 w DFX, stała powłoka FPGA z SHA, bez fizycznej podmiany, fail-closed → OPEN.

**Brama akceptacyjna:** żadne nowe wymaganie v81–v87 nie dostaje pełnego PASS na podstawie samego planu lub diagramu. Zamykanie tylko z rzeczywistą implementacją, testami, falsyfikacją, dowodami SHA i niezależnym od podmiotu weryfikatorem. Brak infrastruktury dopuszcza wierną symulację tylko modelowanych własności, nie udowadnia władania sprzętem.


## ONTOS L10 v63–v66 (2026-11-21): finite reference gates

[Implementacja, dowody, bramki](ONTOS_V63_V66_L10.md) · [kampania JSON](ONTOS_V63_V66_CAMPAIGN.json) · [SHA-256](V63_V66_SHA256SUMS). Zaimplementowano 4 odseparowane referencyjne moduły: v63 A–E pre-commit, modelowa monotoniczność Caps i blokada restartu (TESTED); v64 certyfikat pełnej domeny i4 256/256, niezależny interpreter, fałszerstwa odrzucane (TESTED); v65 skończona samokompozycja śladów, RAW/WAR/WAW, UNKNOWN przy przekroczeniu budżetu (TESTED); v66 kanoniczny komunikat IPC, nonce/sequence/replay/timeout, atomowy most v63↔v66 i deklaracja WIT (TESTED wyłącznie Python; **RUST/ZENOH/WASI/WIT NATIVE-BLOCKED**). Kampania 30-seed: 120 doręczeń, 30 powtórek odrzuconych, 30 celowo konfliktowych przeplotów wykrytych i 0 realnie przyznanych praw; nie zmierzono fizycznego IPC poniżej 1 ms. **40 nowych + 220 poprzednich = 260/260 lokalnych testów PASS**, compileall PASS. Pełne etapy v63–v66 oraz formalne HyperLTL, Lean/SMT, izolacja TCB i natywne porty pozostają OPEN; nie przyznano nowego GATE-09. Historyczny ograniczony GATE-09 PASS niezmieniony. Następny etap v67.


## L10 v63–v67 — weryfikacja po rozszerzeniu (2026-11-21)

[Raport i decyzje GATE-09](ONTOS_L10_V63_V67_CLOSEOUT.md) · [Dowody SHA/logi i zakresy](ONTOS_L10_V63_V67_GATES.json) · [reprodukcja](ONTOS_L10_REPRO.md). **303 testy PASS, 1 XFAIL** świadomie wskazujący niechroniony wspólny rollback podpisanego checkpointu i jego pliku kotwicy. Go race detector PASS, compileall PASS i uruchomiony skrypt bramkowy PASS w ograniczonym modelu. v63: A–E pre-commit i monotonia Caps. v64: pełna domena i4 256/256 oraz rzeczywista biblioteka Z3 i Ed25519. v65: symboliczna dwusladowa nieinterferencja QF_BV i konflikty RAW/WAR/WAW. v66: odseparowany natywny proces Go, Unix socket, canonical wire, replay, podpisane checkpointy. v67: model DFX/static shell, podpisane cztery warunki dowodu, C/WASM Q16.16 i źródło RTL. **GATE-09 dla zweryfikowanych właściwości skończonego testbedu PASS** (DETERMINISTIC-SIMULATION/HYBRID). **Pełny L10 GATE-09 BLOCKED**: brak kwalifikacji natywnego Rust/Zenoh/WASI + WIT ABI, HDL/CIRCT LEC i FPGA, zewnętrznego monotonicznego TCB, fizycznego IPC/ICAP oraz źródłowej Suite D i regresji pełnego repo. Wszystkie te wymagania pozostają obowiązkowe i otwarte; historyczny ograniczony GATE-09 PASS niezmieniony. Brak wdrożenia i produkcyjnego potwierdzenia.


## ONTOS L11 v68 — units and thermodynamic accounting (2026-11-21)

[Źródło, kryteria, wyniki i SHA](ONTOS_V68_SI_ACCOUNTING.md). Moduł `omega_x_evolution/ontos_v68_units.py` implementuje jednostki SI bit/nat, dolną granicę Landauera wyłącznie dla zadeklarowanych bitów nieodwracalnie skasowanych, niezależność liczby operacji od liczby kasowań, agregację niepełnych danych z propagacją UNKNOWN i separację modelowej energii rdzenia/wall od pomiaru. **43/43 ukierunkowanych testów PASS**, compileall PASS (Python 3.13.5; pytest 9.0.2). **v68 modelowy kontrakt PASS**; pełny L11 i etapy v69–v71, v83, v85 oraz metrologia fizyczna pozostają OPEN. Nie rozszerza uprawnień i nie zmienia wcześniejszego ograniczonego GATE-09.

[Przegląd sugestii v21–v35 otrzymanych 2026-11-21](USER_PROPOSALS_TECH_AUDIT_20261121.md): brak tworzenia duplikatów już istniejących funkcji; otwarte regresje Ray, metrologia, retrieval i dowody pozostają osobnymi kryteriami odbioru.


## L11 v69–v70 — RAMXEED FeRAM supplementary reference (2026-11-21)

[Native Python implementation, qualified source assumptions and test evidence](ONTOS_V69_V70_RAMXEED_REFERENCE.md) · [SHA-256 and test IDs](V69_V70_EVIDENCE.json). Based on RAMXEED MB85RQ8MX (DS501-00074-1v1-E) and 2026 catalog: 8 Mbit Quad-SPI FeRAM, conditional power-state current maximums and 1e14 read/write cycles at +85°C / 1e13 at +105°C. Both uploaded datasheets have identical SHA-256 (one independent specification). **44 targeted tests PASS** (Python 3.13.5, pytest 9.0.2, seed 70), compileall PASS, including wrong PSU range, missing rails, workload timing, partial interrupted writes and per-cell wear exhaustion. Six L11 substrate names have a pure explicit-component wall-power model; **no power constants are invented for H100/RRAM/SOT/p-bits/photonics/QPU**. FeRAM is a separate, optional nonvolatile peripheral reference, NOT a new inference accelerator; supply energy is not wall-plug. 100 Hz × 5 years produces 15,778,800,000 modeled worst-address accesses, not a life guarantee. **v69 generic accounting and v70 FeRAM reference TESTED; full v69 six calibrated device models and v70 SOT/RRAM distributions remain OPEN.** New full L11 GATE-09 OPEN; historical scoped GATE-09 unchanged; no deployment or physical measurements.


## ONTOS L11 v71 — scenariuszowe Pareto i przegląd materiałów (2026-11-21)

[Model i testy](ONTOS_V71_PARETO_RESEARCH.md) · [dowody](V71_EVIDENCE.json) · [rejestr źródeł](RESEARCH_SOURCE_INTAKE_20261121.md). Czysty moduł `omega_x_evolution/ontos_v71_energy_pareto.py` porównuje energię wall-plug [J], czas [s] i poprawność przy tym samym hash zadania i liczbie operacji. Tylko jawne, kompletne scenariusze z v69 i znane przedziały wrażliwości; brak danych i przecięcie przedziałów => UNKNOWN. **74/74 testy lokalnej, ukierunkowanej regresji v69–v71 PASS**, compileall PASS; brak pełnej regresji repo, natywnych pomiarów MRAM/FeRAM i kalibracji. **Ograniczony model v71 TESTED; pełny zakres v71 sprzętowej walidacji, v70 wear-out SOT/RRAM i cały L11 GATE-09 OPEN.** Dokumenty dołączone przez użytkownika są badawcze/nieobowiązkowe; nie tworzą nowych zadań poza realizacją już istniejącego v71.


**ONTOS-TDA — bounded input corrective increment (2026-11-24):** [native TDD evidence](ONTOS_TDA_INPUT_BOUNDS_20261124.md). JSONL read requests bounded to 4097 bytes, strict 4096-byte wire limit, deterministic maximum JSON nesting. 4 RED failures reproduced; 8 focused tests PASS after correction. Full regression NOT RUN. No change to diagnostic mathematics, privileges or historical bounded GATE-09.


**L12 v72 — bounded Merkle proof primitives (2026-11-24):** [native evidence and L11–L111 intake](ONTOS_V72_MERKLE_20261124.md). RFC 6962 SHA-256 inclusion and consistency, 528 inclusion and 560 prefix cases on trees of 1–32 leaves, 11 pytest cases PASS. Bounded generation and verifier inputs; empty root and malformed proofs fail closed. This is a mathematical sub-contract, not checkpoint authentication, external-anchor closure, or a new GATE-09. v72 remains OPEN for JCS, signed receipts, PQC and integration. v81–v87 preserved. L13–L111 proposals do not become binding by import.


**L12 v72 — bounded JCS evidence preimages (2026-11-24):** [verification](ONTOS_V72_JCS_20261124.md). UTF-16 key ordering, finite binary64 formatting, strict duplicate/Unicode admission, 1 MiB/32-depth/65536-node budgets. 24 JCS and 11 Merkle tests PASS, including seed-72 differential parity with Node.js on 9997 finite binary64 values. TESTED within bounded profile; full RFC qualification, signed receipts, schema semantics and PQC remain OPEN. No change to evaluator, permissions or historical GATE-09.


**L12 v72 — strict Ed25519 detached receipts (2026-11-24):** [verification](ONTOS_V72_RECEIPTS_20261124.md). Native cryptography signing and verification with public-only canonical prime-order point validation and S<L; detached receipt binds level, gate, commit, tenant, evaluator and actual canonical record digest. 14 receipt cases + 35 earlier v72 cases = 49 PASS. Authentication only, not truth of evidence or promotion. Section 10 schema, HMAC/PQC profiles, checkpoint notes, integration and v72 full acceptance remain OPEN; historical GATE-09 unchanged.


**L12 v72 — nine-section evidence admission (2026-11-24):** [verification](ONTOS_V72_EVIDENCE_20261124.md). Strict Section 10 field/semantic validation and binding to externally supplied source/log/provenance/replay bytes, pinned scope and Ed25519 receipt; 39 new cases + 49 prior v72 cases = 88 PASS. A valid record authenticates the bytes and stated outcome only; never authorizes promotion. HMAC/PQC, C2SP checkpoint note interoperability, runtime integration and complete v72 acceptance remain OPEN. Historical GATE-09 unchanged.


**L12–L111 planning registry (2026-11-24):** [implementation and verification](ULTRA_EVOLUTION_MAP_20261124.md). Registers all 100 level IDs/titles, 400 phase packages, ten epochs, eight tracks and sixteen cross contracts. Cycle checking includes cross edges and package phases; readiness uses transitive prerequisites and is not release authority. Ten map tests + 88 v72 cases = 98 PASS in isolated subset. Only L12 is binding in this new registry; 396 L13–L111 packages remain PROPOSED_NON_BINDING. Prior mandatory v81–v87 and L11 obligations are unchanged; no level promotion or new GATE-09.


**L12 v72 — HMAC and native PQ profiles (2026-11-24):** [verification](ONTOS_V72_CRYPTO_PROFILES_20261124.md). Native HMAC-SHA256 domain separation, bounded ML-DSA-65 and SLH-DSA-SHA2-128s public signature verification via OpenSSL 3.5.5, ML-KEM-768 public/ciphertext shape and actual native test roundtrip (not a signature). Eight focused tests PASS, zero skipped locally. Scope: profile interoperability and negative cases, not official PQ KATs, key custody, production KEM adapter or evaluator integration. C2SP and complete v72 acceptance remain OPEN; no changes to historical GATE-09.


**L12 v72 — signed checkpoint note (2026-11-24):** [verification](ONTOS_V72_CHECKPOINT_NOTE_20261124.md). Implements bounded C2SP v1.0.0 three-line single Ed25519 log signature profile with pinned origin/name/public key, strict canonical Base64, size and empty-root checks. 23 new tests plus eight crypto-profile regressions = 31 PASS in current isolated subset. Does not imply external monotonic anchoring, witness cosignatures, or integrated acceptance. Official PQ KATs, production key custody/KEM, integrated v72 evidence and v73–v75 remain OPEN. Historical GATE-09 unchanged.


**L12 v72 — authenticated checkpoint transitions (2026-11-24):** [evidence](ONTOS_V72_CHECKPOINT_CHAIN_20261124.md). Reuses actual signed-note and Merkle verification code, serializes competing appends and rejects rollback, equivocation and divergent proofs against an operator-pinned starting root. 6 new integration tests; 37/37 PASS including 31 prior checkpoint/PQ profile tests in local subset. Process-local only; simultaneous rollback of state and pin, cross-process persistence and external anchoring are not solved. v72 overall OPEN; v73–v75 and existing obligations unchanged. Historical GATE-09 unchanged.


**L12 v73 — authenticated finite A–E isolation boundary (2026-11-24):** [evidence](ONTOS_V73_ISOLATION_20261124.md). Existing v63/v66 transition and receiver integrated with v72 strict Ed25519; distinct pinned T_obj/T_ext authorities, tenant/session/history binding including trusted delivery tick, atomic commit, rejection of role confusion and forbidden model operations. 14 new cases + 37 earlier local cases = 51 PASS. HYBRID (native cryptography + finite deterministic model); no OS isolation, holdout broker, key custody or real capabilities claimed. v73/v81/v86 remain OPEN for remaining obligations; v72 and historical GATE-09 unchanged.


**L12 v73 — one-shot blind holdout contract (2026-11-24):** [verification](ONTOS_V73_HOLDOUT_20261124.md). Frozen protocol/feature/artifact digest manifest, salted label commitment, distinct Ed25519 keys, one signed batch per candidate, no scores before external seal, missing and abstained rows remain in denominator. 12 new tests, local subset 63/63 PASS. HYBRID finite protocol with native cryptography; no claim of OS isolation, durable uniqueness, artifact execution provenance, multi-campaign privacy or actual full Suite A-D run. v73/v74 remain OPEN. Historical GATE-09 unchanged.


**L12 v74 — preregistration and paired report engine (2026-11-24):** [verification](ONTOS_V74_CAMPAIGN_20261124.md). Enforces a pinned 30-seed, 36 primary/24 ablation configuration plan over A-D; explicit missing/failed accounting, generation separation, paired integer contrasts, seeded percentile bootstrap, exact/Monte Carlo sign flip and Holm adjustment. 12 new tests; 75/75 local subset PASS. Tested on 1800 synthetic fixture records, not actual source episodes. Source configuration identity/provenance, broker integration and full executed campaign remain OPEN; no new GATE-09.


**L12 v74 — reference A-D preregistration:** [frozen plan](ONTOS_V74_REFERENCE_PREREG_20261124.md). Integrates real v73 broker (C) and v74 report with v37 replay (A/B) and v62 noise (D). 3 focused tests PASS; reference plan pinned before complete execution. Original source configurations and full L12 acceptance remain OPEN.


**L12 v74 — executed reference A-D campaign and authenticated report:** [results](ONTOS_V74_REFERENCE_EXECUTION_20261124.md), [signed attestation](ONTOS_V74_REFERENCE_ATTESTATION.json). 1800/1800 real reference runs (432000 trials), 30 holdout brokers, no missing runs. Report and 1800 record leaves bound to pinned plan in 1802-leaf signed history. 3 focused attestation tests PASS; actual attestation verified. Original source suite reproduction and target attainment OPEN; A/B reference results below source target. No automatic promotion or new GATE-09.


**L12 v75 — gate admission and actual review:** [evidence](ONTOS_V75_ACCEPTANCE_20261124.md), [machine-readable gates](ONTOS_V75_L12_GATES.json). 33/33 registry identity verification PASS; 0/33 original source bytes, licenses unreviewed, full L12 01–09 BLOCKED. Actual reference run reproduced byte-identically (1800/1800); attestation verified again. 13/13 focused local integration tests, compileall PASS. v75 gate verifier implemented and tested, full-scope acceptance OPEN. Historical GATE-09 unchanged.


**L12 v72 — durable monotonic witness / key provisioning (2026-11-24):** [evidence](ONTOS_V72_WITNESS_20261124.md). Real SQLite durable CAS, C2SP log validation, signed fresh challenge, separated key roles, encrypted PKCS8 provisioning, and retained client pin consistency including restored-witness fork detection. 11/11 focused tests, two process crash points, real 1802-leaf reference checkpoint admitted in temporary simulation store. HYBRID; external witness hosting and operational TCB provisioning are NOT performed, joint rollback of all trust domains remains out of scope. Full clone DNS failure and archive transfer unavailable; full regression still OPEN. Historical GATE-09 unchanged.


**v72 witness regression follow-up:** pinned main `94ecb3752669cfbf7272522d94aab2e2fe29dda5`, 89/89 PASS in exact-blob isolated subset (11 witness + 78 existing Merkle/JCS/receipt/checkpoint-note/checkpoint-chain tests), no skips, `python -m pytest -q tests` exit 0 in 4.43 s. Full repository regression not run; external archive still unavailable. See [witness evidence](ONTOS_V72_WITNESS_20261124.md).


**L12 v75 — mandatory fresh monotonic witness tip (2026-11-24):** [evidence](ONTOS_V75_WITNESS_GATE_20261124.md). Eight authenticated gate receipts, scope, evaluator pins, manifest and campaign digests committed to exact last leaf of independently pinned witness history. Missing anchor blocks final PASS; invalid anchor fails. Six new tests and modified regression, 102/102 PASS in isolated dependency slice, compileall PASS. Operational authority protocol exercised with test keys, no live TCB provisioning or complete repo regression. Historical GATE-09 unchanged; full L12 still BLOCKED.


**L12 v72 — authenticated routine witness key rotation (2026-11-24):** [evidence](ONTOS_V72_ROTATION_20261124.md). Offline pinned authority signs exact old/new policy and receipt handoff, same Merkle root/size, monotonic epoch, retired-key exclusion, no environment escalation; eight new native-crypto/SQLite tests including v75 anchor compatibility. Local focused dependency regression 24/24 PASS; compileall PASS. Durable client epoch CAS, coordinated quiescence/recovery, emergency root rotation and independent operational deployment remain OPEN. Full repository regression still BLOCKED by archive/DNS access. Historical GATE-09 unchanged.


**L12 v72 — durable client epoch journal (2026-11-24):** [evidence](ONTOS_V72_EPOCH_STORE_20261124.md). Replays canonical authenticated transitions from externally pinned bootstrap; atomic SQLite CAS, hash-linked cursor, durable rotation/retirement state, fail-closed recovery relative to retained external floor. Eight new tests include process crashes before/after commit, concurrent CAS, replay recovery, snapshot restoration and old-policy rejection. Focused dependency regression 32/32 PASS, compileall PASS. Bounded 256-event journal, independently retained cursor and operational separation still require external provisioning. No simultaneous all-domain rollback claim, no deployed TCB, full repository regression remains blocked. Historical GATE-09 unchanged.


**L12 v72 — fixed 3-of-4 monotonic witness quorum:** [evidence](ONTOS_V72_QUORUM_20261124.md). Native SQLite and Ed25519, roster/epoch-bound challenge, strict distinct signatures and pinned Merkle continuity. Ten focused tests PASS, one Byzantine key or one database rollback, 2+2 partition fail-closed, late recovery; divergent 2+2 fork can remain blocked. Review-leaf verifier implemented; gate reducer wiring, quorum reconfiguration, external custody and full repo regression remain OPEN. Not a consensus or production deployment. Historical GATE-09 unchanged.
