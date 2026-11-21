# OMEGA-X ONTOS Ω∞ — v63–v66, ograniczony model zgodności L10

**Baza `main`:** `09d162a321721c433f8cedd434202497bc39f5c3` (21.11.2026). **Status:** IMPLEMENTED/TESTED w modelowanych, skończonych podkontraktach, pełne L10 / native Rust–Zenoh–WASI / HyperLTL i GATE-09 **OPEN**. Nie nadano żadnych uprawnień, nie uruchomiono sieci, poświadczeń, akceleratorów ani kodu kandydata. Dokument źródłowy: `docs/omega/ONTOS_OMEGA_INFINITY_ROADMAP.md` L10 v63–v66, wcześniejszy `docs/omega/ONTOS_CHANNELS_A_E_SEQUENCE.md` i `docs/omega/ONTOS_EXTENSIONS_V81_V87.md`.

## v63 — model protokołu A–E, PolyTr/WIT i monotoniczna redukcja

`omega_x_evolution/ontos_v63_interface.py` implementuje zamknięty automat `Session`/`Frame`, kanały A–E, `A:observe → B:assess → C/D:propose → E:allow/veto`, tryb LOCKDOWN, timeouty oparte na **logicznym** zegarze, kontrolę nonce, kolejności komunikatów i pojemności audytu. Proponowane uprawnienia mogą wyłącznie redukować aktywny zbiór; `E:restart` nie przywraca praw. Stary kontrakt `Poly`/`Lens` z v42 jest wykorzystywany w testach kompozycji. Właściwość `operational_capabilities_granted` stale zwraca `False` — nie jest to rzeczywiste Jądro Immunologiczne ani zaufane TCB. Klasę Python można modyfikować poza kodem modelu; granica izolacji procesowej wymaga v73/v81.

## v64 — wiązanie certyfikatu IR z semantyką i pełną domeną

`omega_x_evolution/ontos_v64_certificate.py` opiera się na **rzeczywistym** `ontos_v47_pure_ir.PureIR`, buduje SHA-256 obu drzew, hash pełnej 256-wierszowej tablicy zachowania, dokładną wersję semantyki `ontos-pure-i4-v1`, liczby węzłów (diagnostyczna proxy MDL) i weryfikację przez **oddzielną implementację** interpretatora z ponownym porównaniem 256 przypadków `0..15 × 0..15`. Zmieniona struktura, dowolny bit certyfikatu lub cztery próbki zamiast 256 powodują odmowę. `f32`, `u16` i domeny nieznane zwracają UNKNOWN — to nie jest certyfikat Lean, dowód Z3 ani pełny egglog/MLIR/CIRCT. Istniejące `proof_kernel.py`, `bitproof.py`, `lean_native.py` pozostają w repozytorium, ale **w tej sesji nie było natywnej integracji tych backendów**.

## v65 — wielośladowe własności skończone, konflikty interleavings

`omega_x_evolution/ontos_v65_hypertraces.py` porównuje pary śladów przy identycznym publicznym wejściu i różnych tajnych wejściach (wymaga identycznego `low_output`) oraz enumeruje wszystkie przeploty dwóch krótkich śladów zachowując porządek wewnętrzny. Zwraca jawne kontrprzykłady i klasy RAW/WAR/WAW, oddziela zasoby `global:*` od przestrzeni `tenant:*`, blokuje obcy tenant, rewaliduje modele, a po wyczerpaniu limitu zwraca `UNKNOWN_BOUND`, nie PASS. Wykrywanie konfliktu bazuje na **modelowanych deklaracjach odczytów/zapisów**, nie faktycznych śladach pamięci procesu. `proved_unbounded_hyperltl=False`, `verified_native_smt=False` — nie jest to pełny dowód nieinterferencji HyperLTL `∀*ψ`, który pozostaje wymaganiem v86.

## v66 — wiadomości i replay bez fikcyjnej latencji

`omega_x_evolution/ontos_v66_wire.py`: kanoniczny JSON (jedna kolejność kluczy), jawna wersja schematu `ontos-ipc-v1`, 4 KiB payload/8 KiB wiadomości, ścisłe typowanie, SHA-256 całej treści, `tenant`, `nonce`, u32 `sequence`, ważność w krokach logicznych, odrzucanie niezgodnej wersji, nadmiarowych kluczy, uszkodzonej sumy i replay. `Receiver` jest niezmienny, przeterminowane/obce/niewłaściwie uporządkowane komunikaty nie zmieniają stanu. `model_precommit_delivery` **atomowo** łączy odbiornik i automat v63: gdy ramka A–E narusza politykę, nie konsumuje numeru sekwencji ani nie emituje zgody.

`interfaces/wit/ontos-ae-v1.wit` jest **typowanym projektem interfejsu**; nie ma wdrożonego adaptera WIT↔JSON, kompilacji WIT ani procesu Rust/Zenoh/WASI. Integracja natywna, mTLS, transport, podpisy i pomiar opóźnienia sieci pozostają OPEN. `observed_ipc_latency_ms=null`; źródłowy cel IPC `<1 ms` nie został przetestowany. SHA-256 envelope jest integralnością danych, **nie uwierzytelnieniem nadawcy**; E:allow bez zewnętrznej atestacji nie może dawać realnych praw.

## Kampania zamrożona i dowody wykonania

`python -m scripts.ontos_v63_v66_campaign` wykonuje 30 deterministycznych ziaren `9100 + 29*i`, każdy zawiera A/B/C-or-D/E, pełnodomenowy certyfikat i4, konflikt RAW, pozytywny zgodny ślad poufności oraz 4 wiadomości IPC i próbę replay. Podsumowanie: **30/30 `MODEL_APPROVED`, 30/30 `FAIL_CONFLICT` dla celowo konfliktowych śladów, 30/30 `PASS_FINITE` dla śladów zgodnych, 120/120 dostarczonych w modelu wiadomości, 30/30 odrzuconych replay**. **0** faktycznie nadanych praw i **0** pomiarów natywnego IPC. Pełny JSON: [ONTOS_V63_V66_CAMPAIGN.json](ONTOS_V63_V66_CAMPAIGN.json), SHA-256 `1ceebe076a8a1c346d3ff46ad8ff05e1d0df4063788bc398b2079e95d8aeb764`.

Środowisko lokalne: Linux x86_64, Python 3.13.5, pytest 9.0.2, NumPy 2.3.5, SciPy 1.17.0. Dostępne poprzednie moduły odtworzono z dystrybuowanego ZIP v59–v62 i zweryfikowano `ontos_logic.py` Git blob `99f4d433bf6c64088426a4bfb652caa0072a2b54`. Pełny klon GitHub z lokalnego środowiska był niedostępny (DNS); nie wykonywano upstream suite 660 plików repozytorium. Rust, Cargo, Lean, Z3 CLI, WIT tooling i WASM tooling nie były dostępne; `libz3` systemowo istnieje, ale nie uruchomiono w tym przyroście backendu `bitproof`.

| Test ID | Faktyczna komenda | Wynik |
|---|---|---|
| V63-66-RED | `PYTHONPATH=. pytest -q tests/test_ontos_v63_v66.py` przed implementacją | ERROR: brak modułu `ontos_v63_interface`, exit 2 |
| V63-66-NEGATIVE | `PYTHONPATH=. pytest -q tests/test_ontos_v63_v66.py` po pierwszym GREEN | 22 PASS / 1 FAIL (niewłaściwe oczekiwanie testu: zero budżetu, brak porównywalnego śladu), poprawiony sam test |
| V63-66-GREEN | `PYTHONPATH=. pytest -q tests/test_ontos_v63_v66.py` | 36 PASS / 0 FAIL |
| V63-66-CAMPAIGN-RED | `PYTHONPATH=. pytest -q tests/test_ontos_v63_v66_campaign.py` | 2 FAIL: stary timestamp był odrzucany jako CLOCK_REGRESSION przed REPLAY |
| V63-66-CAMPAIGN-GREEN | identyczna komenda po poprawie czasu testu | 2 PASS / 0 FAIL |
| V63-66-REGRESSION | `OPENBLAS_NUM_THREADS=1 PYTHONPATH=. python -m pytest -q --strict-markers tests/test_ontos_v46_v48.py tests/test_ontos_v49_v51.py tests/test_ontos_v52_v54.py tests/test_ontos_v55_v58.py tests/test_ontos_v59_v62.py tests/test_ontos_phase0_diagnostics.py tests/test_ontos_extensions_docs.py tests/test_ontos_v63_v66.py tests/test_ontos_v63_v66_campaign.py` | **260/260 PASS**, 4.97 s, exit 0 |
| V63-66-COMPILE | `python -m compileall -q omega_x_evolution scripts tests` | PASS, exit 0 |
| V63-66-WIT | test obecności i kształtu tekstowego WIT | PASS statyczny, **NATIVE-BLOCKED** |

**Integralność uruchomienia:** lokalny log końcowy SHA-256 `154918881f0261314bf37640acb521d8e6a9b872e98dec4f60af4a9c76bb4ae8`. Wartości są dowodami dla **lokalnego wycinka**. Szczegółowy manifest SHA znajduje się w `V63_V66_SHA256SUMS`.

## Bramki odbiorowe

GATE-01/02 PASS dla zakresu modelowanego; GATE-03/04 PASS dla czterech kodów referencyjnych i testów; GATE-05 PASS jedynie dla modelowej integracji v63↔v66 oraz referencyjnej regresji; GATE-06 modelowe testy negatywne PASS, realny TCB/MCP/sieć i polityka OPEN; GATE-07 modelowe replay/timeout PASS, natywne recovery OPEN; GATE-08 dowody i SHA udokumentowane; GATE-09 **nie otrzymuje nowego PASS**. Historyczny ograniczony PASS pozostaje bez zmian, a v63–v66 w pełnej interpretacji Roadmapy pozostają OPEN.

**Dalsze obowiązki:** v67 RTL/DFX, v68–v71 energia i podłoża, rozszerzenia v81 (zewnętrzny TCB), v84 (adjunkcje), v86 (weryfikacja HyperLTL) i v87 (LEC/Z3), bez dostępu do hardware w tej sesji.
