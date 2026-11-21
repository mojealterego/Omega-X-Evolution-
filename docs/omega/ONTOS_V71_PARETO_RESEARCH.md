# ONTOS L11 v71 — porównanie energetyczne Pareto (model badawczy)

**Data:** 2026-11-21. **Zakres:** czyste, ograniczone obliczenia Python na istniejącym `ontos_v69_substrate.py`; brak fizycznego sprzętu, kalibracji i promocji zmian produkcyjnych. **Wynik lokalny:** 74/74 PASS wraz z dotychczasowymi testami v69/v70, 0 FAIL, `compileall` PASS. **Pełny L11 GATE-09: OPEN.**

## Granica dowodu

Nowy `omega_x_evolution/ontos_v71_energy_pareto.py` nie nadaje statusu wdrożenia. Odczytuje `SubstrateScenario` z v69 i **wymaga** kompletnego, jawnego rachunku energii całego systemu (core/memory/ADC/DAC/network/host/PSU/cooling/aux). Nie wolno mylić zużycia samego rdzenia [J] z wartością wall-plug [J]. Nie wolno przypisywać zasilania RAMXEED `FeRAMSupplyScenario` do wall-plug bez uwzględnienia regulatora/hosta.

Kontrakt `Workload` wiąże kandydatów tym samym SHA-256 obciążenia i dokładnie tą samą liczbą operacji. `Interval` przechowuje założony przedział poprawności, nie wyliczoną statystycznie niepewność. Model porównuje energię [J], opóźnienie [s] i poprawność w [0,1], z kontrolą wymaganej jakości. Wprowadzona przez operatora czułość/wrażliwość energetyczna i czasowa także **nie jest** przedziałem ufności.

**Silna dominacja konserwatywna:** A dominuje B tylko jeżeli górna granica energii A <= dolna B, górna latencji A <= dolna B i dolna poprawności A >= górna B, oraz przynajmniej jedna nierówność jest ostra. Nakładając się przedziały, nie wolno deklarować jednoznacznej przewagi. Brak liczby lub niepodany przedział czułości ⇒ `UNKNOWN`, bez podmieniania na zero. Dane wejściowe pozostają wyłącznie scenariuszami operatora; `physical_measurement_verified = false`, `release_authorized = false`.

Próg z materiału źródłowego **15 nJ / 350 000 operacji** jest kwalifikowany jedynie wewnątrz jawnego scenariusza: `PASS_SCENARIO` jeśli najwyższa energia jest <= 15 nJ, `FAIL_SCENARIO` jeśli najniższa > 15 nJ, inaczej `UNKNOWN`. Nie oznacza to osiągnięcia fizycznego wyniku. Operacje nie są utożsamiane z bitami wymazanymi w v68.

## Zastosowanie nowego porównania MRAM vs FeRAM

17-stronicowy „Next-Generation Memory Selection in Practice: A Comprehensive MRAM vs. FeRAM Comparison Guide”, SHA-256 `b8e0aa79cd5a9e845d2a58d5c32bab3e8f2849e81f038e2e2da14286e4ca7573`, szczególnie s. 11 i 14–17, wskazuje:

- FeRAM może wymagać destrukcyjnego odczytu z automatycznym odtworzeniem; liczba odczytów może zużywać budżet trwałości **zależnie od produktu**. W istniejącym v70 przyjęto konserwatywną rejestrację odczytu i zapisu jako cyklu.
- MRAM stosuje nieniszczący odczyt; kwalifikacja trwałości i zachowania w polu magnetycznym wymaga **konkretnego SKU**, nie ogólnych wartości z marketingowej tabeli.
- W przewodniku zakres prądu FeRAM jest opisany jako dziesiątki µA–1 mA na s. 9 i do 3 mA na s. 14. Nie są to dane dla konkretnego MB85RQ8MX. **Nie zastępować** nimi jego maksymalnych 18 mA przy aktywnym Quad I/O 108 MHz ani z nich szacować fizycznej oszczędności.
- MRAM i FeRAM mają inne pojemności oraz interfejsy; pełne porównanie wymaga takiego samego workload, poziomu ochrony danych, hosta i warunków zasilania.

Parametry do prawdziwego modelu MRAM należy dopiero pozyskać z kart produktu: aktywne/przechodnie prądy, sekwencje read/write, profil wrażliwości na pole magnetyczne, endurance/retention w temperaturze, overhead sterownika, czas bootstrap i dane niezawodności. Bez tych danych **nie** oznaczamy MRAM jako zwycięzcy ani jako „nieskończenie trwałej”.

## Przetestowane niezmienniki (TDD)

Testy: `tests/test_ontos_v71_energy_pareto.py`. Komenda: `PYTHONPATH=. python -m pytest -q tests/test_ontos_v71_energy_pareto.py tests/test_ontos_v69_v70_ramxeed.py`. Kryteria: dokładna tożsamość zadania, odrzucenie niedopasowanej liczby operacji, brak dominacji przy przecięciu przedziałów, wielokryterialny trade-off, trójwartościowy próg energii i poprawności, brak domyślnego uzupełniania UNKNOWN, oszczędne limity 64 kandydatów, walidacja NaN/Inf/10**400 i przesuniętych danych, niezmienność kolejności wyników przy 50 permutacjach z seedem 71 oraz niepowoływanie się na pomiary fizyczne.

Zależności `v68/v69/v70` pozostają niezmienione. Nie uruchomiono pełnego `pytest` całego repozytorium, natywnych układów FeRAM/MRAM, FPGA, QPU, fotoniki ani prawdziwego metrologicznego benchmarku. `v71` jest **TESTED dla modelu scenariuszowego**, natomiast pełny poziom L11 i `GATE-09` **OPEN**. Inicjalne RED było błędem importu brakującego modułu; GREEN to testy rzeczywistego kodu produkcyjnego, bez atrap zwracających wynik.

## Dowody

`docs/omega/V71_EVIDENCE.json` podaje źródła, komendy, środowisko, SHA-256, wynik testów i ograniczenia. `docs/omega/V71_GREEN.log` i `docs/omega/V71_RED.log` zawierają zarejestrowane wyjście. Materiały zewnętrzne są **research optional**, nie niezależnymi wymaganiami wdrożenia.
