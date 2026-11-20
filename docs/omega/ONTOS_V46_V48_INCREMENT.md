# ONTOS v46–v48 — skończony audyt, IR i kampania referencyjna

**Status:** TESTED (ograniczone podkontrakty), wszystkie szerokie obowiązki v46–v48 pozostają OPEN. **Baza main:** `8fe7227c062cd39eafa88bb8a39661fd22508724`; **tryb:** NATIVE dla lokalnego Pytest i NumPy, DETERMINISTIC-SIMULATION dla scenariusza środowiska; bez fizycznej infrastruktury. Opracowanie 2026-11-20. Zachowano wcześniejszy ograniczony GATE-09 PASS, bez nowej certyfikacji wydania.

## v46 — audyt statystyczny niezależny od runtime

Moduł `omega_x_evolution/ontos_v46_statistics.py` dokładnie enumeruje krótkie ścieżki Bernoulliego z ilorazem wiarygodności przy stałym H ≤ 12 i ułamkach wymiernych (Fraction). Prawidłowy proces pod hipotezą zerową ma E[wealth_12] = 1 i P(max wealth≥20) ≤ 1/20. Porównanie ze sztucznym ograniczeniem wealth do minimum 1 wykazuje E[wealth_12] > 1, więc dawny dowód Ville'a nie może być automatycznie odziedziczony. Test ten nie jest nowym modułem akceptacji i nie zmienia PACE ani zaufanego weryfikatora. Osobna diagnostyka OOD rozdziela TP/TN/FP/FN, abstencje i wartości niezdefiniowane; etykiety prawdy pozostają wyłącznie po stronie ewaluatora. Pozostałe GSAI/SAE/VaG i pełna walidacja hipotez są OPEN.

## v47 — typowany czysty IR

Moduł `omega_x_evolution/ontos_v47_pure_ir.py`: tylko typ i4, wejścia x/y, literały 0..15, operacje add/sub/mul/xor/and/or, ≤48 węzłów, głębokość ≤6. Porównanie 256/256 par daje PASS_EXHAUSTIVE wyłącznie dla tej domeny; wcześniejsze zakończenie bez kontrprzykładu daje UNKNOWN_BOUND, a kontrprzykład podaje wejścia. Przed obliczeniem każda zamrożona struktura jest ponownie walidowana — test RED wykazał, że samo dataclass(frozen=True) można obejść przez object.__setattr__. Emisja ograniczonego zapisu MLIR-like jest deterministyczna i nie jest wykonywana. Nie należy nazywać tego native egglog, Lean, Rust, Zenoh, WIT/WASI, pełnym MLIR ani ogólnym formalnym dowodem programu. Wszystkie te integracje pozostają OPEN.

## v48 — tylko porównanie stałych sekwencji akcji

Wykonano `omega_x_evolution.ontos_v48_campaign.run_campaign` na faktycznym przypiętym module `ontos_testbed.py` (Git blob `d431de36228df2eae4ca15270d115fe854de33e8`, identyczna kopia lokalna). Przed ewaluacją ustalono cztery taśmy: cycle, constant, abstain, offset_cycle. **30 nasion (9100 + 29·i), 240 kroków, cztery taśmy = 28 800 faktycznych kroków**. Wszystkie strategie otrzymały równą liczbę kroków, ale nie zweryfikowano równości fizycznego kosztu energii. Brak dynamicznego planera, adaptacji lub dostępu do etykiet ewaluatora przy wyborze akcji. Seed-count podzielono na 20 dev i 10 holdout bez dostrajania.

| Strategia | Poprawne/7200 | Trafność bezwarunkowa | Pokrycie | Zdarzenia harm |
|---|---:|---:|---:|---:|
| cycle | 1788 | 24,83% | 100% | 0 |
| constant | 1208 | 16,78% | 100% | 0 |
| abstain | 0 | 0,00% | 0% | 0 |
| offset_cycle | 1817 | 25,24% | 100% | 0 |

W holdout (10 nasion, 2400 kroków na strategię): cycle 597 poprawnych, constant 419, abstain 0, offset_cycle 607. W dev: odpowiednio 1191, 789, 0 i 1210. Raport zawiera surowe podsumowanie dla każdej pary (seed, strategia), SHA-256 pełnego śladu, oraz opisowe, sparowane przedziały bootstrap (512 replikacji, seed 761). Nie ma deklaracji przewagi adaptacyjnego ONTOS, generalizacji OOD ani istotności statystycznej bez zewnętrznego eksperymentu. Brak zdarzeń harm wynika z faktu, że żadna strategia nie używa działania 4; nie jest dowodem bezpieczeństwa AI.

**Zgodność historyczna:** cykliczna taśma odtwarza 1788 poprawnych i 678 OOD ze źródłowego `v37-campaign.json` (Git blob `77c6788469ae91530c75831fc5f7407eb8c6aaef`); SHA-256 trzech pierwszych pełnych śladów jest identyczne. Komplet raportu per-seed: lokalny plik `v48_campaign_30_seeds.json`, 32 171 B, SHA-256 `3c3af0db5b0727224ac739cca49731669516e2f61894c77d238696f3b3309a7f`. Źródła i polecenie pozwalają go odtworzyć bez płatnych usług. Nie znajduje się w commicie, ponieważ nie przenoszono 32 KiB danych w tej iteracji; dostępny wraz z lokalnym pakietem dowodów.

## TDD i testy

Środowisko: Python 3.13.5, pytest 9.0.2, NumPy 2.3.5, Linux x86-64. Ograniczony wycinek z odtworzonym i zhashowanym kodem `ontos_testbed.py`, bez bezpośredniego klonu Git (błąd DNS). Założenia probabilistyczne i domena testów są jawne.

| ID | Polecenie | Zarejestrowany wynik |
|---|---|---|
| ONTOS-V46-V48-RED | `PYTHONPATH=. python -m pytest -q tests/test_ontos_v46_v48.py` przed implementacją | exit 2, brak modułu |
| ONTOS-V47-MUTATION-RED | `PYTHONPATH=. python -m pytest -q tests/test_ontos_v46_v48.py -k post_init_tampering` | exit 1, AssertionError zamiast kontrolowanego ValueError |
| ONTOS-V48-SPLIT-RED | `PYTHONPATH=. python -m pytest -q tests/test_ontos_v46_v48.py -k real_holdout` | exit 1, brak niezależnych metryk splitów |
| ONTOS-V46-V48-GREEN | `PYTHONPATH=. python -m pytest -q --strict-markers tests/test_ontos_v46_v48.py` | **40 passed, 4.03s**, exit 0 |
| ONTOS-V46-V48-COMPILE | `python -m compileall -q omega_x_evolution tests` | exit 0 |
| ONTOS-V48-REPLAY | `run_campaign(SEEDS)`, dwukrotnie + JSON kanoniczny `sort_keys=True,separators=(',',':'),allow_nan=False` | dokładna zgodność bajtowa |

Dla zakresu nowych modułów 40/40 PASS bez SKIP. **Nie uruchomiono całej suite repozytorium**, natywnego MLIR/Lean/egglog ani testów operacyjnego systemu. Nie udowodniono w tym etapie GATE-05/06/07/09 dla pełnego ONTOS.

## Identyfikowalność SHA

| Plik | Git blob SHA | SHA-256 |
|---|---|---|
| `omega_x_evolution/ontos_v46_statistics.py` | `a413abdd75027301821d349f997a3c9f9285d9d3` | `c16c67c870fe550d038d06a071c566acecb74970c65c1a4ade2b3537d98ee913` |
| `omega_x_evolution/ontos_v47_pure_ir.py` | `48f50d85dee3346b9cecb58558c0501797bdce1f` | `b7fcc90649ae736fb276e98c7683690f51a7de14da59ae5e601e259c3c81361d` |
| `omega_x_evolution/ontos_v48_campaign.py` | `dc5316598a13a224bd54c12927eb35657ef60224` | `35253908d31ab0b23fb7dc7bb7dc9cfccc33dd44df660e50e2ef398dc3df695d` |
| `tests/test_ontos_v46_v48.py` | `5315b5fa5210ccb99baff6ad856fb708da9834fe` | `3b6d0d680b1a54cd03769e1acf4019261a1d3fe169cda7c0e09d5f2246ef40b8` |

Logi (lokalne): RED `c9a23e100dfa9c4bf417d8459b02ba9b42d531b08ecbbdb8b81121afccfb2ef8`; tamper RED `b866a1ffd59c982c760ab68b92d887a96e646704b733dea61331ce5cd791d0ac`; split RED `90a3523680400eb97d0bcffc46850d6c68af6b424ed77c97fbbdf0b59590271c`; GREEN `fbf4aee7b9690bbe3a96551409a361bee885ad84e45f461a3f9e096dea63e845`.

## Bramka odbiorowa

- GATE-01/02: zakres i ograniczenia modelu zdefiniowane;
- GATE-03/04: nowe podkontrakty zaimplementowane i lokalnie przetestowane;
- GATE-05: tylko ograniczony wspólny testbed v37+v48, brak natywnej integracji systemu;
- GATE-06: walidacje nieprawidłowego IR, danych OOD i nasion; brak pełnego audytu bezpieczeństwa;
- GATE-07: powtarzalne replay; brak testów recovery natywnego runtime;
- GATE-08: komendy, Git SHA i lokalne sumy danych zarejestrowane;
- GATE-09: zachowana wcześniejsza decyzja dla ograniczonego wydania. **Nie przyznano nowego PASS dla całości v46–v48.**

Kolejny etap zależności: v49 rejestr importu źródeł i v50 kontrakt przekonań, po zakończeniu reszt zarejestrowanych w dotychczasowej Roadmapie. Żadnych zmian zaufanego ewaluatora, uprawnień, harmonogramów, ograniczeń operacyjnych ani prywatnych repozytoriów.
