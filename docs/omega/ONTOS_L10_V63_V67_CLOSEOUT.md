# OMEGA-X ONTOS Ω∞ — L10 v63–v67: inżynieryjny odbiór ograniczony i pełna bramka

**Gałąź:** `main` wyłącznie. **Baza:** `c45323d58e12e5867cfceec37a90872554725544`. **Data:** 2026-11-21. **Wymagania:** `ONTOS_OMEGA_INFINITY_ROADMAP.md`, kanały A–E oraz rozszerzenia v81/v86/v87. **Tryb:** HYBRID — natywny proces Go, natywna biblioteka Z3, kompilowany C/WebAssembly i deterministyczny testbed Python; **nie** natywne Rust/Zenoh ani fizyczne FPGA.

## Decyzja GATE-09 i rozróżnienie statusów

| Przedmiot odbioru | Status | Uzasadnienie |
|---|---|---|
| Referencyjna generacja L10 — skończone właściwości modelowane | **PASS** | 303/303 PASS i 1 znany XFAIL w zamkniętym wycinku, Go `-race` PASS, oddzielny rzeczywisty solver Z3, Ed25519, modelowane błędy/kontrprzykłady, native C i WASM |
| Pełny system L10 zgodny z wszystkimi celami źródłowymi | **BLOCKED** | Brak natywnego Rust/Zenoh/WASI i WIT ABI, RTL HDL/CIRCT LEC, sprzętowej DFX, niecofalnego kotwiczenia, źródłowej Suite D i pomiarów fizycznych |
| PRODUCTION-VERIFIED | **BLOCKED** | Żadnego rzeczywistego FPGA/ICAP, trwałej niezależnej infrastruktury TCB lub wdrożonego runtime |
| Historyczny ograniczony GATE-09 PASS dla wcześniejszego wydania | **BEZ ZMIAN** | Nie zmienia zakresu, nie certyfikuje L10 |

Status pełnego L10 **nie jest PASS**. Deterministyczne symulacje są wiarygodnym odbiorem *zweryfikowanych właściwości*, ale nie można przedstawić implementacji Go jako skompilowanego Rust/Zenoh ani modelu Q16.16 jako rzeczywistego bitstreamu FPGA. Dlatego raport celowo pokazuje obie decyzje i bramkę pełną zamyka dopiero realnymi dowodami lub zgodnym, wystarczająco wiernym modelem wykonującym właściwy kod produkcyjny. Nie przyznaje się GATE-09 pełnemu L10 na podstawie tabelki.

## Wykonana implementacja

### v63 — pre-commit i A–E

Moduł `ontos_v63_interface.py` z poprzedniego commita wykonuje skończony, deterministyczny protokół A→B→C/D→E, nie rozszerza Caps, reaguje LOCKDOWN na alarm, timeout i weto. Nowy `ontos_l10_approval.py` wiąże podpisaną odpowiedź z **rzeczywistego procesu natywnego** z dokładnym nonce, numerem sekwencji, tenantem, statyczną powłoką i zatwierdzonym kandydatem, a następnie wydaje wyłącznie etykietę `MODEL_APPROVED`. Nie daje uprawnień OS ani sieci.

### v64 — formalna kontrola IR i Ed25519

`ontos_v67_dfx.py` wykonuje całodomenowe i4 (256 par) na istniejącym `PureIR` i osobnym interpreterze, po czym uruchamia libz3 przez **izolowany podproces z limitem czasu**. Zmodyfikowane IR, niepełny dowód, inne reguły niż i4, fałszywy certyfikat i niezgodność semantyki są odrzucane lub otrzymują UNKNOWN. Wystawione poświadczenia Ed25519 są wiązane z dokładnymi SHA statycznej powłoki i programu, tenantem, epoką, terminem ważności oraz wynikiem czterech testów przed zatwierdzeniem modelowym.

`ontos_l10_release.py` sprawdza cztery dowody *przed podpisaniem*: (1) 256-case i4 + Z3 inequivalence UNSAT; (2) symboliczną nieinterferencję i porównanie niskich śladów; (3) brak RAW/WAR/WAW we wszystkich dozwolonych przeplotach; (4) górną granicę szkody z LP Balke–Pearla (`scipy.optimize.linprog`), konserwatywnie poniżej 5%. Stary token zawierający tylko równoważność IR **nie przechodzi**.

### v65 — nieinterferencja i skończone HyperLTL-style

`ontos_l10_formal.py` wykonuje natywne zapytania Z3 QF_BV, wykazując w zadeklarowanych skończonych domenach: parowanie śladów z różnym sekretem i równym publicznym wejściem, monotoniczność 3-bitowych Caps, stałość 256-bitowego digest powłoki i zgodność *signed Q16.16 arithmetic shift* z niezależną regułą floor-division, łącznie z ujemnymi wartościami. Mutanty wykonują SAT i ujawniają realne kontrprzykłady. **Nie** jest to nieograniczony formalny certyfikat HYPERLTL / HyperLTL ani dowód wszystkich operacji FPGA.

### v66 — natywny proces i izolacja komunikatów

`native/ontos-l10-gateway` to prawdziwy, kompilowany w Go 1.23.2 proces **osobny od Python**. Komunikuje się przez Unix domain socket, dekoduje dokładny kanoniczny format IPC z v66 (nieznane klucze i niekanoniczne bajty powodują odmowę), weryfikuje Ed25519 wobec zadanego publicznego klucza, chroni logiczne nonce/sequence i tenant, odmawia klientowi wysłania własnego `E:allow`. Serializowany checkpoint ma podpis i osobny, również podpisany, hash-anchor. Po restarcie normalnym Caps i nonce nie wracają do poprzedniego stanu. Uszkodzony checkpoint uniemożliwia start. Naprawiono wyścig pamięci wykryty `go test -race`; po poprawce ten sam race detector ma wynik PASS.

**NATIVE-BLOCKED:** Go Unix socket nie jest Rust, Zenoh ani WASI. Zapisany wcześniej WIT stanowi projekt, nie skompilowany kontrakt ABI. Źródłowy cel IPC `<1 ms` nie został przetestowany; czas w modelu to liczniki zdarzeń, nie latencja end-to-end.

### v67 — DFX/static shell i Q16.16

`ontos_v67_dfx.py` wykonuje model IDLE→PREPARED→ACTIVE/LOCKDOWN, podpisy i wymuszony anchor SHA256 powłoki, reset przywraca tylko złoty, niezmienny model partycji, timeout kończy się blokadą. Bez podpisu wymaganych czterech dowodów przejście `prepare` jest niedostępne. `hardware/rtl/ontos_q16_core_v67.sv` i `ontos_static_shell_v67.sv` to rzeczywiste pliki SystemVerilog, ale **nie uruchomiono** ich w symulatorze/syntezie HDL (narzędzia niedostępne). Alternatywne odwzorowanie obliczeń testowane na niezależnym natywnym C oraz w kompilowanym WebAssembly w Node.js obejmuje 1000 losowych wektorów plus graniczne. Z3 niezależnie sprawdza prawo obcięcia Q16.16 na 64-bitach, ale nie zastępuje pełnego HDL LEC ani pomiaru ICAP `≤2,5 ms`.

## Niezamknięte ryzyko: pełny rollback stanu i kotwicy

Wcześniejsza poprawka wykrywa zmianę **tylko checkpointu** przy niezmienionym pliku `.anchor` oraz nieautoryzowaną podmianę podpisu. Test `test_native_dual_file_rollback_requires_protected_external_anchor` świadomie **XFAIL**: aktor zdolny nadpisać *oba* starsze podpisane pliki może przywrócić wcześniejszy stan (`rollback`) i identyfikatory nonce. Same podpisy kryptograficzne nie gwarantują świeżości. Wymagana jest niezależna, monotoniczna kotwica po stronie właściwego TCB (np. odseparowany chroniony dziennik, TPM, KMS ze stanem, wiarygodna usługa licznika). Nie wolno oznaczać kontroli fizycznego anti-rollback jako PASS. Nie wystarczy przesunięcie drugiego pliku do sąsiedniego katalogu na tym samym, równie zapisywalnym nośniku.

## Testy RED/GREEN, środowisko i dowody

- Python 3.13.5, pytest 9.0.2, NumPy 2.3.5, SciPy 1.17.0, cryptography 46.0.4, Linux x86_64. Natywna libz3.so.4 przez ctypes; Go 1.23.2, gcc 14.2, clang 17, Node 22.
- `L10-TDD-Q16-RED`: brak `prove_q16_floor_shift`, **2 FAIL** zgodnie z oczekiwaniem. [Log](L10_Q16_RED.log), SHA-256 ewidencjonowany w [maszynowym rejestrze](ONTOS_L10_V63_V67_GATES.json).
- `L10-TDD-Q16-GREEN`: po wdrożeniu właściwego warunku signed floor-shift **2 PASS**, błędne obcięcie toward-zero wykazuje SAT.
- `L10-REGRESSION`: `OPENBLAS_NUM_THREADS=1 PYTHONPATH=. python -m pytest -q --strict-markers tests/test_ontos_v46_v48.py ... tests/test_ontos_l10_native_math.py` — **303/303 PASS, 1 oczekiwany XFAIL**, kod wyjścia 0, [log](L10_PYTEST_FULL.log), bez SKIP w tej kampanii.
- `L10-GO-RACE`: `GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off CGO_ENABLED=1 go test -race -count=1 ./...` w katalogu Go — **PASS**, [log](L10_GO_RACE.log).
- `L10-COMPILE`: `python -m compileall -q omega_x_evolution scripts tests` — **PASS**.
- `L10-NEGATIVE-ROLLBACK`: podwójny przywrócony komplet plików, jeden przypadek **ściśle oczekiwanego XFAIL** (odtworzony, nie przeliczany do PASS), [log](L10_DUAL_ROLLBACK_XFAIL.log).
- `L10-NATIVE-C/WASM`: `cc -std=c11 -O2 -Wall -Wextra -Werror -shared -fPIC` oraz `clang --target=wasm32 -nostdlib ...`, Node WebAssembly Instantiate — PASS w regresji.
- `L10-Z3`: UNSAT dla pełnodomenowych założeń, SAT dla jawnych mutantów; świadectwo dotyczy dokładnego SMT QF_BV, nie uruchomienia Lean/CIRCT/RTL.
- `L10-GATE`: [wykonywalny, ponawialny verifier](../../scripts/verify_ontos_l10.py) odtwarza testy i Go race, zwraca `PASS` tylko w modelowym podzbiorze oraz `BLOCKED` przy żądaniu pełnego odbioru.

Szczegółowe checksumy każdego nowego pliku i logu, środowisko, źródła oraz powiązania *requirement → implementation → test* zawiera [ONTOS_L10_V63_V67_GATES.json](ONTOS_L10_V63_V67_GATES.json). Bazowy main i SHA artifactów są rejestrowane bez fabrykowania commitów. Testy upstream całego repozytorium poza odtworzonym wycinkiem nie zostały uruchomione.

## Bramki 01–09 i wymagania pozostałe

| Bramka | Modelowy zakres | Cały L10 |
|---|---|---|
| GATE-01: wymagania | PASS | PASS |
| GATE-02: architektura | PASS | PASS |
| GATE-03: implementacja | PASS finite reference | BLOCKED native Rust/Zenoh/WASI and HDL |
| GATE-04: testy deterministyczne | PASS scoped | BLOCKED total target suite |
| GATE-05: integracja/E2E | PASS Python↔Go Unix IPC | BLOCKED native Zenoh/WASI/FPGA |
| GATE-06: bezpieczeństwo | PASS negative cases scoped | BLOCKED independent immutable TCB |
| GATE-07: reliability/rollback | PASS single-file tamper/reset | BLOCKED paired rollback/XFAIL |
| GATE-08: dokumentacja | PASS | PASS scoped evidence only |
| GATE-09: końcowy odbiór | **PASS for modeled properties only** | **BLOCKED** |

Zadania zależne v67/v81/v86/v87 nie są domknięte w pierwotnym, fizycznym/natywnym znaczeniu. **Odbiór modelowy nie implikuje DEPLOYED ani PRODUCTION-VERIFIED**; uczciwy rejestr długu jest częścią kryterium bezpieczeństwa. Po uzupełnieniu brakujących natywnych dowodów pełne GATE-09 będzie podlegało ponownej ocenie, bez przepisywania historycznych wyników.
