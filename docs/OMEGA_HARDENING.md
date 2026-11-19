# ShinkaEvolve — OMEGA Runtime Hardening (2026-11-15)

## Zakres i status

Modyfikacja kodu źródłowego **ShinkaEvolve 0.0.7** na podstawie przesłanego
archiwum ZIP. Nie zmienia modelu ewolucyjnego ani publicznego numeru wersji.
Dostarcza poprawki w wykonywaniu zadań, bezpieczeństwie powłoki,
spójności wyników i odporności procesów lokalnych/SLURM.

| Komponent | Implementacja | Kontrakt |
| --- | --- | --- |
| `shinka/launch/local.py` | Grupy procesów, kill tree, reaping, status zakończenia | Timeout i anulowanie nie mogą pozostawić działającego procesu głównego; na POSIX obejmują procesy w tej samej grupie |
| `shinka/launch/scheduler.py` | Timeout w trybie synchronicznym, bezpieczne cytowanie ścieżek aktywacji, anulowanie | Nie uznaj zakończonej błędem ewaluacji za poprawną |
| `shinka/launch/slurm.py` | Bezpieczne argumenty shell, walidacja dyrektyw, oczyszczanie `sbatch`, ograniczone błędy odpytywania, CPU-only bez `nvidia-smi` | Dane konfiguracyjne nie są kodem powłoki; stan queued != completed |
| `shinka/utils/general.py` | Walidacja pól JSON, limity danych, bounded log tail, poprawny czas | Poprawność wyłącznie typu `bool`; dane z ewaluatora są niezaufane |

## Gwarancje funkcjonalne

1. `submit()` usuwa zastane pliki `metrics.json` i `correct.json` przed nową próbą. Nie należy współdzielić jednego katalogu wyników przez równolegle wykonywane zadania.
2. `monitor()` ustawia `execution_status`: `completed`, `timed_out`, `cancelled` albo `failed`, i dopisuje `return_code`.
3. Gdy zakończenie jest inne niż `completed`, ustawia `correct = {"correct": false}` oraz `metrics = {}` — niezależnie od zawartości plików wygenerowanych przez proces.
4. Timeout używa zegara monotonicznego. Anulowanie rejestruje przyczynę i kończy proces; na POSIX tworzona jest osobna sesja i zabijana jej grupa procesów. Na Windows wykorzystywany jest `psutil`.
5. Ładowanie logów w pamięci domyślnie ograniczono do **ostatnich 4 MiB na plik**; log na dysku pozostaje pełny. Rozmiar pojedynczego pliku JSON ograniczono do **8 MiB**. `load_results()` umożliwia zmianę limitów parametrami `max_log_bytes` i `max_json_bytes`.
6. `correct.json` wymaga obiektu zawierającego pole `correct` o rzeczywistym typie JSON boolean; `metrics.json` musi być obiektem. Uszkodzone lub zbyt duże pliki są odrzucane (fail-closed).
7. Skrypty SLURM cytują argumenty, flagi i eksportowane zmienne. Podstawienia `$(...)`, backticki, separator `;` i nowe linie nie mogą samodzielnie wprowadzać poleceń przez obsługiwane pola. Po wywołaniu `sbatch` tymczasowy skrypt jest usuwany także po nieudanym zgłoszeniu; zawartość skryptu nie jest wypisywana do logów podczas błędu.
8. Lokalny tryb SLURM z `gpus=0` uruchamia zadanie bez wywołania `nvidia-smi`; żądanie GPU nadal wymaga narzędzi NVIDIA, a obecny wybór na podstawie `memory.used=0` nie jest pełnoprawnym arbitrem zasobów.
9. `slurm.monitor()` kończy pracę błędem po pięciu kolejnych nieudanych próbach odczytu statusu (konfigurowalne `max_status_errors`), zamiast zapętlać się bez końca.

## Testowanie

W środowisku z pełnymi zależnościami:

```bash
python -m pytest -q -m "not requires_secrets and not models_dev_live"
```

Lekkie testy regresyjne bez kluczy, SLURM ani GPU:

```bash
python scripts/verify_hardening.py
```

Ten drugi runner wymaga tylko `pytest` i `psutil`, izoluje zależności importowe `shinka.utils`, ale wykonuje **rzeczywisty kod modułów** z repozytorium. Nie zastępuje pełnej weryfikacji integracyjnej.

### Status weryfikacji wykonania

- Regresje napisano przed poprawkami i odtworzono w lokalnym środowisku.
- Testy kontrolne/bezpieczeństwa: **38/38 zaliczone** (15.11.2026, lokalny runner).
- Składnia pakietu: weryfikacja `compileall`.
- Pełny zestaw testów: **niepotwierdzony** w tej sesji z powodu brakujących zależności projektu i braku dostępu do instalacji sieciowej.
- Testy na faktycznym klastrze SLURM, GPU, Androidzie, Windows i produkcji: **nieprzeprowadzone**.
- Żadnego kodu nie wdrożono ani nie wysłano do zdalnego repozytorium.

## Granice bezpieczeństwa

**To nie jest piaskownica bezpieczeństwa.** Ewaluatory wykonują dowolny kod użytkownika,
a sam proces grupowy nie gwarantuje zatrzymania potomków, które opuściły grupę lub sesję.
Nieznane lub wrogie programy należy wykonywać w odizolowanych kontenerach albo VM
z ograniczeniem uprawnień, cgroups, filesystem, sieci i sekretów. Środowisko potomne
nadal dziedziczy zmienne środowiskowe nadrzędnego procesu; tokeny należy usuwać
przed uruchomieniem niezaufanych ewaluatorów. Ta poprawka nie dowodzi odporności
na celowe obejście izolacji.

## Kompatybilność

Dodatkowe klucze `execution_status` i `return_code` są wstecznie kompatybilne z
konsumentami używającymi `correct` / `metrics`. Zmiana polityki fail-closed
może zmienić rozstrzygnięcia wcześniejszych eksperymentów, które akceptowały
nieprawidłowy JSON albo metryki po błędzie procesu. Domyślnie długie logi
są obcięte *w pamięci*, nie na dysku. Wszystkie zmiany wymagają regresji
pełnego projektu przed wydaniem produkcyjnym.
