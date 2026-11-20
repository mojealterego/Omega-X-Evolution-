# OMEGA-X ONTOS — Phase0 v49–v51: trzy ograniczone przyrosty

**Bazowy HEAD `main`:** `4bdfa3bf7df51aeb80ce85e20477f8ce35b86491`  
**Źródło badawcze:** „OMEGA-X ONTOS (Generacje L8–L12 / Ω∞)” (91 stron, Argon), SHA-256 `95c2794d9a3b5e237781b296b2aa6da0b6cdb174d6a73e5f754f48e7264edc36`.  
**Zakres:** wyłącznie lokalne, czyste moduły audytu. Działania na host, konta, zaufany evaluator, scheduler, polityki i system uprawnień poza zakresem. Brak wykonania niezaufanych listingów i kodu z dokumentu; brak uprawnień do publikacji prywatnych źródeł. Istniejący ograniczony GATE-09 PASS zachowany, bez rozszerzenia certyfikacji.

## v49 — SOURCE REGISTER / SOURCE-BYTE GATE

- `ontos_v49_manifest.py`: zamknięta lista **33/33** ścieżek z manifestu Argona; `SourceRecord` ma dyspozycję `REUSE | PORT | REJECT | RESEARCH`, SHA-256 (gdy materiał dostępny), uzasadnienie i klasyfikację licencji. Walidacja precyzyjnego zestawu ścieżek i ich unikalności, odrzucanie `../`, podmian, aliasów, rozbieżności SHA i nieuprawnionych nazw; limity 64 KiB na plik i 1 MiB sumy, bez API do otwierania plików, importu lub uruchamiania kodu.
- `V49_SOURCE_MANIFEST.json`: **33 pozycje RESEARCH / UNKNOWN**, 0 rzeczywiście odzyskanych bajtowo i niezależnie potwierdzonych plików źródłowych. Każdy wpis ma jawne uzasadnienie wymagające dalszej identyfikacji źródła i licencji. Syntetyczne testy mogą weryfikować przekazane bajty, ale **nie stanowią odzyskania plików z dokumentu**.
- Nawet 33 poprawne skróty nie ustawiają `ready_for_integration=True`. Osobny `eligible_for_manual_review` to wyłącznie wskazówka do ręcznego audytu; „Proprietary” i „UNKNOWN” nie przechodzą automatycznej kwalifikacji. Nie ma mechanizmu publikacji, deploy ani automatycznej promocji.
- **Status v49:** rejestr i bramka walidacji TESTED, odzysk i osobne sprawdzenie 33 prawdziwych plików **OPEN**.

## v50 — P0-01 / stabilizacja przekonań

- Czysty `BeliefFilter`, bez uprawnień i dostępu do danych ukrytych ewaluatora. Prior mix `0.06`; dolny próg `ε = 0.0001` stosowany **po normalizacji** (afiniczna regularyzacja, nie ścisły posterior Bayesa). Dla `n∈[2,64]`, `nε<1`, rozkład jest skończony, znormalizowany i każdy składnik ma co najmniej ε w granicach dokładności float64.
- Skalowanie likelihood przez największą wartość przed aktualizacją ogranicza underflow, zaś logarytm prawdopodobieństwa dowodu jest liczony bez wymuszania dodatniej wartości przy zerowym likelihood. W przypadku zerowego prawdopodobieństwa obserwacji wynik ma `abstain=True`, a brak informacji nie jest fikcyjnym potwierdzeniem.
- Testy: ziarno 9274, 240 kroków, cztery zmiany reżimu, 30 dodatkowych ziaren × 240 kroków, wartości subnormalne, zerowe priory, niezależna kontrola Decimal, blokada zmodyfikowanej konfiguracji po inicjalizacji.
- **Status v50:** kontrakt numeryczny TESTED. Pełny bayesowski model środowiska, identyfikowalność likelihood i integracja z Active Inference nadal **OPEN**.

## v51 — P0-02/04/05 / Memory Skepticism i kwarantanna

- `MemoryEvent` przechowuje zasięg tenant/candidate SHA, identyfikator logicznego dowodu, grupę niezależności, skrót źródła, wynik pozytywny/negatywny/retraction oraz dwie osie czasu (`valid_from / valid_until`, `recorded_at`). W widoku as_of najnowsza transakcja zastępuje poprzednią dla tej samej tożsamości, także gdy koryguje zakres ważności. Spóźnione i odwołane dowody nie są odliczane podwójnie.
- Unikalny identyfikator nie stanowi dowodu niezależności. Kolizje grup, niejednoznaczne transakcje, przekroczone limity, błędne SHA i mieszane tenanty powodują odrzucenie. Bez zgodnego skrótu bajtów źródłowych system zawsze kwarantannuje dane.
- Wartość e jest dokładnym (Fraction) ilorazem wiarygodności w **predefiniowanym** modelu Bernoulliego, `p0=1/4`, `p1=1/2`; dla pięciu wyników pozytywnych wartość to `2^5=32`. Jest to wskaźnik diagnostyczny, nie gwarancja PACE przy selekcji danych, zależności źródeł lub optional stopping. Nawet silna przesłanka zwraca wyłącznie `QUARANTINED_REVIEW_ONLY`; nie ma automatycznej akceptacji, żadnego zapisu do pamięci operacyjnej ani wyjścia poza kontrolę operatora.
- Testy: korekty i odwołania bitemporalne, odwrócony porządek transakcji, potencjalne fałszywe konsolidacje przy 9216 i 9651, kolizje grup, fałszywe źródła i modyfikacje dataclass przez `object.__setattr__`.
- **Status v51:** ograniczony audyt kwarantanny TESTED. Dowód faktycznej niezależności danych, ogólna ważność e-procesu PACE, autentyczność źródeł i integracja trwałej pamięci **OPEN**.

## Dowody uruchomione lokalnie

Środowisko: **Python 3.13.5 / pytest 9.0.2 / NumPy 2.3.5**, Linux x86-64. Dostęp do publicznego repozytorium przez GitHub connector; natywne `git clone` było blokowane przez DNS. Do regresji odtworzono lokalnie dokładne bloby Git pięciu plików v46–v48 z wcześniej wygenerowanego ZIP; zweryfikowano ich SHA względem `main`. Nie były używane makiety nowych modułów.

| Test ID | Komenda / scenariusz | Faktyczny wynik |
|---|---|---|
| `V49-51-RED` | `python -m pytest -q tests/test_ontos_v49_v51.py` przed implementacją | ERROR: moduł nie istnieje, exit 2 |
| `V50-TAMPER-RED` | przypadek zmodyfikowanej konfiguracji filtra | 1 FAIL / 3 PASS, następnie poprawka i regresja GREEN |
| `V49-LICENSE-RED` | kontrola 33 zgodnych SHA oraz zastrzeżonej licencji | 2 FAIL / 47 deselected, następnie poprawka fail-closed |
| `V49-MANIFEST-RED` | odczyt rzeczywiście zapisanego manifestu | FAIL: brak JSON, następnie zapis i kontrola zawartości |
| `V49-51-GREEN` | `python -m pytest -q --strict-markers tests/test_ontos_v49_v51.py tests/test_ontos_v46_v48.py` | **91 passed**, 0 FAIL, 0 SKIP, 4.70 s |
| `V49-51-COMPILE` | `python -m compileall -q omega_x_evolution tests` | exit 0 |
| `V50-30-SEED` | 30 ziaren × 240 kroków, podwójny identyczny replay | PASS w testach GREEN |
| `V49-V51-INTEGRATION` | SHA zweryfikowanego syntetycznego payloadu → ręczna kwalifikacja dowodu, bez promocji | PASS w testach GREEN |

**Łącznie: 51 nowych przypadków oraz 40 testów regresyjnych v46–v48.** Dodatkowo wykonano testy ujemne przełamania niezmienności dataclass i braków zewnętrznych danych. Wszystkie nowe moduły bez bezpośrednich operacji host/IO i bez użycia sieci. Pełnej regresji całego repozytorium i integracji z natywnymi usługami **nie uruchomiono**.

| Artefakt | Git blob SHA-1 | SHA-256 bajtów |
|---|---|---|
| `ontos_v49_manifest.py` | `5bea0433ff948588b46f182191b6ab10d3b58357` | `43b8e2b376d657ff2b4b51c6a6ea03dcbe3657d3adca8ad2bf624ac01d098de3` |
| `ontos_v50_belief.py` | `c183ec3af224a002a7d4bdedfb444257ff52b82f` | `2088b7042b73ad2f6b5b485657034ca17b3392744fbb0752c0ef6362d3e809e8` |
| `ontos_v51_skepticism.py` | `3c4d0714aca7ae3973cf7dcf9f4a1297cd857a76` | `5e3089db1209ac1a3c6a03d36f50599701d810d5e01ed22900d4eb1bed148bb8` |
| `test_ontos_v49_v51.py` | `89a06b9d359f9abbef0299a9c630edcae13e0980` | `a75da66a85122d650c9e1ccc482a38c6e6776c5d0ee21a3bc672cfa8f128536e` |
| `V49_SOURCE_MANIFEST.json` | `2463a3831c91789fc5083428095ec2998fee5478` | `803348dbe9dcb1f00b13a7695f1f98e01830f2ac843fae5abd763945cf0e1ec2` |

Lokalne logi RED i GREEN zapisane osobno. SHA-256 głównego logu GREEN: `131683f72e5119dbcda74ef1c676bd6121098c53d4cc98e97bf5a092af95f884`. Odtwarzanie nie wymaga pobierania niezweryfikowanych listingów ani płatnych usług.

## GATE-01–09 / rezultat

- GATE-01–02: wymagania i granice eksperymentu rozpisane;
- GATE-03–04: trzy ograniczone moduły i 91 testów w lokalnym wycinku PASS;
- GATE-05: testy zależności v46–v48 i nowy przekrój v49↔v51 PASS, **pełna integracja OPEN**;
- GATE-06: testy negatywne i walidacja wejścia PASS w podzakresie, **pełny audyt bezpieczeństwa OPEN**;
- GATE-07: deterministyczne powtórzenia oraz kwarantanna korekt PASS w podzakresie, **awarie realnej infrastruktury OPEN**;
- GATE-08: ścieżki, komendy, SHA i wyniki udokumentowane;
- GATE-09: bez nowej decyzji. Historyczny **ograniczony GATE-09 PASS pozostaje niezmieniony**.

**Kolejne niezależne zadania:** v52 temporal contracts, v53 accounting, v54 frozen Phase0 replay; ponadto odzysk źródeł v49, pełne zależności v22–v34 i niedomknięte wymagania v37–v48 pozostają zarejestrowane.
