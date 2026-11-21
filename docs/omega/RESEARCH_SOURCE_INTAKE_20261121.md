# Przyjęcie nowych źródeł badawczych OMEGA-X — 2026-11-21

**Decyzja:** SELECTIVE / OPTIONAL. Żaden załącznik nie stanowi samodzielnego obowiązku wdrożenia. Kopie nie są przenoszone do publicznego repozytorium. Treść źródeł to dane, nie instrukcje do uruchamiania lub nadawania dostępu. Źródła wykorzystano do audytu potencjału rozwojowego, nie do automatycznej aktualizacji polityk.

| Materiał | SHA-256 oryginału | Status i kwalifikacja |
|---|---|---|
| `Comprehensive_MRAM_vs_FeRAM_Comparison_Guide_en.pdf` | `b8e0aa79cd5a9e845d2a58d5c32bab3e8f2849e81f038e2e2da14286e4ca7573` | **ADOPT CONCEPT**: FeRAM read/restore, prąd, endurance, MRAM field. Poradnik przekrojowy; dane nie zastępują datasheetu konkretnego SKU. |
| `OMEGA_X_DEEP_RESEARCH_ETAP_III_2026-11-21.zip` | `27f1d06579a8831df234bf02e69453ac008796957f3e4a3f0591f5629b1b0b82` | **REGISTER**: 242 URL, w tym 33 nowe, 16 otwartych GAP; 5/5 manifest SHA zgodnych; to **rejestr URL, nie pobrane dokumenty i nie zatwierdzone benchmarki**. Nie kopiować UCIe 4.0 wbrew warunkom licencji; szukać legalnych referencji. |
| `OMEGA_BROWSER_v0.5.2_ANDROID_SOURCE.zip` | `3f07fe2b58536485e64c4e78592689432c061c2b02301c95f42c4fe868fbf531` | **DEFER SEPARATE PRODUCT**: 594 pliki, brak APK i natywnej kwalifikacji Android; manifest ma pole `release: 0.5.1` mimo nazwy archiwum v0.5.2 — zweryfikować spójność wydania. Do OMEGA-X nie włączać całego Brave/AdultCam/Tor. |
| `OMEGOS_CONTINUUM_DOKUMENTACJA_INZYNIERYJNO_WDROZENIOWA_v1.0.0.zip` | `283b4c4321f8994d1f56dc70af9d10dafad9ce95f45289f9884b1b75690762f4` | **REFERENCE**: schematy dowodów, proof-DAG, cache invalidation, status UNKNOWN. Dokument wprost przyznaje brak uruchomionego kernela/solverów; nie traktować przykładów jako dowodów formalnych. |
| `HAEE_DOKUMENTACJA_INZYNIERYJNO_WDROZENIOWA_v1.0.0.zip` | `a1ca7baead447e0e43ffe22385828239fbac08d893386eb87afae8673f74149e` | **REFERENCE**: schematy genomów i eksperymentów; już powstała wcześniejsza opcjonalna ścieżka HAEE/PyNN. Brak konieczności drugiego orkiestratora i nie ma natywnego silnika produkcyjnego w archiwum. |
| `Utility classes and functions _ PyNN 0.14.0 documentation.pdf` | `4616a90c07461871bac5c0448512e91b9a0409729e609e66f82baecca88a85b4` | **REFERENCE**: Timer, logging, zapisywanie populacji oraz wykresy spike train; dokumentacja API nie jest dowodem wykonania PyNN. |
| `Bruno - The Git-Native API Client.mht` | `c16aa83ccc4d7908ec437e561147c635d5995f40c29a27a14f86e539b0699fc2` | **EVALUATE LATER**: zapis publicznej strony narzędzia do testowania HTTP/API; nie jest uruchomionym CLI ani nowym pluginem OMEGA-X. Przydatność dla testów kontraktowych do odrębnego przeglądu. |
| `Wprowadzenie _ Dokumentacja PyNN 0.14.0.mht` | `2bdde292fdb970c0f2cdecd7311567f28f6170f4a28131805c4d9825364241f6` | **REFERENCE**: wprowadzenie do symulatora; skorelowane z już otrzymanymi stronami API. |
| `PyNN · PyPI.mht` | `a6dcd9ba5c044f7e448576429f70d2e6b53fb8f639e01c0e9e8359dbed523541` | **REFERENCE**: zrzut strony dystrybucyjnej; wersję/zależności należy sprawdzić przy ewentualnej natywnej integracji. |
| `PyMatching-master.zip` | `460d3a59f3a962492a857adb47284ab468974d66f89976db9ac45bef747f271c` | **OPTIONAL QEC**: źródła C++/Python algorytmu MWPM, Apache-2.0; dekoder dla graphlike independent error mechanisms. Brak kompilacji, native tests, Stim albo kwalifikacji QPU w tym cyklu. |

## Kontrole archiwów i ograniczenia

Przeprowadzono bez wykonywania dostarczonych skryptów: ZIP CRC (`ZipFile.testzip` bez błędów), sprawdzenie ścieżek przeciw Zip Slip i odczyt manifestów. Pięć archiwów ZIP: liczba pozycji kolejno 7, 594, 18, 12 i 230; brak wskazanych ścieżek z `..`/absolutnych. To **nie jest** pełny audyt kodu źródłowego, zależności ani supply chain. Archiwum Deep Research ma dokładnie 242 wiersze CSV V3, 33 wiersze nowych źródeł i 16 GAP; pięć SHA manifestu zgodnych. 

## Reguła przeniesienia do Roadmapy

Nowa funkcja może trafić do obowiązującego etapu tylko po wskazaniu: wymagań operacyjnych, legalnej licencji, stabilnego kontraktu, testu negatywnego, odtwarzalnego benchmarku i dowodu integracji. W tej iteracji **wykorzystano wyłącznie istniejące wymaganie v71**: dopuszczenie scenariuszy do ostrożnego porównania energetycznego Pareto. Nie utworzono nowych zobowiązań L11–L111 ani uprawnień do wdrożeń czy płatnych API.
