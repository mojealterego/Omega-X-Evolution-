# ONTOS — moc szczytowa, moc wall-plug i energia epizodu

**Status: SPECYFIKACJA METROLOGII / model, nie pomiar sprzętowy.** Źródło scenariusza: „OMEGA-X ONTOS (Generacje L8–L12 / Ω∞)”, TOM VI, obciążenie 350 000 operacji. Wartości z dokumentu są **SOURCE-REPORTED / SIMULATED**, nie przebadane na rzeczywistym stanowisku w repozytorium.

## Metryki, których nie wolno utożsamiać

- `P_accelerator_peak_W` — chwilowa moc szczytowa modułu/akceleratora [W]; wymaga próbkowania o określonej częstotliwości i oknie agregacji.
- `P_system_wall_plug_W` — moc pobierana przez kompletny system z gniazdka [W], łącznie z CPU/sterowaniem, pamięcią, zasilaczem, ADC/DAC, siecią i chłodzeniem. Wariant AC ≠ pomiar mocy na magistrali DC.
- `E_core_J` — energia procesowania w rdzeniu [J]; nie zawiera narzutów w innych układach, chyba że źródło jawnie mówi inaczej.
- `E_system_wall_plug_J` = całka z P_system_wall_plug_W po czasie epizodu; energia ≠ moc, a brak czasu i profilu pracy uniemożliwia odtworzenie W z nJ.
- `E_Landauer_bound_J` = `k_B * T * ln(2) * liczba nieodwracalnie skasowanych bitów`; liczba FLOPs NIE jest liczbą wymazań, więc wyniki takie są tylko dolną granicą przy opisanych założeniach.

## Macierz wyników źródłowych — scenariusz 350 000 operacji

| Podłoże | P_accelerator_peak [W] | P_system_wall_plug [W] | E_core [nJ/epizod] | E_wall_plug [nJ/epizod] | Ograniczenie |
|---|---:|---:|---:|---:|---|
| H100 FP8 | UNKNOWN | UNKNOWN | UNKNOWN | **167,13** | Energia z modelu, nie z watomierza |
| RRAM/PCM | UNKNOWN | UNKNOWN | **28,21** | **347,92** | Dominujący ADC (źródło: ok. 85% narzutu mocy) |
| SOT-MRAM / Tiki-Taka | UNKNOWN | UNKNOWN | UNKNOWN | **11,69** | Trwałość, koszt zapisu, zarządzanie wagami |
| p-bity / s-MTJ | UNKNOWN | UNKNOWN | UNKNOWN | **1,14** | Sprzęt probabilistyczny, ograniczenia kalibracji |
| Silicon photonics CPO | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | Źródło podaje 1,9–4,6 pJ/**bit przesyłany**, nie epizod |
| Fault-tolerant QPU / qLDPC | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | Brak pomiaru przy uwzględnieniu kriostatu i transferów |

Nie przenosić wartości między kolumnami. `UNKNOWN` nie jest zerem ani szacunkiem. Nie obiecywać przewagi energetycznej na podstawie samej wartości rdzeniowej lub nominalnego TDP. W dokumentacji wartości niekrzemowe oraz daty dostępności podłoży to hipotezy/modelowe scenariusze, nie potwierdzone pomiary producenta.

## Spójna reguła rozliczania (v68–v71 / v83 / v85)

Jeżeli komponenty mocy są rozłączne:

\[
P_{wall} = (P_{core} + P_{memory} + P_{ADC} + P_{DAC} + P_{network} + P_{host})/\eta_{PSU} + P_{cooling} + P_{aux}
\]

\[
E_{wall}=\int_{t_0}^{t_1}P_{wall}(t)\,dt
\]

W każdej próbie wymagane: definicja granicy pomiarowej, numer urządzenia, okno czasu, częstotliwość próbkowania, powiązanie energii do konkretnej transakcji, jednostki SI, niepewność i identyfikacja podwójnego liczenia ADC/chłodzenia. Symulator musi modelować timeout i uszkodzone próbki; nie wolno przyznać `PASS` dla niezweryfikowanej kalibracji. Model allostatyczny nie może wykonywać realnej rekonfiguracji sprzętu bez osobnego zgody operatora.
