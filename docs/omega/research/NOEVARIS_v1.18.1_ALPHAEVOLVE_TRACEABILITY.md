# NOEVARIS Ω v1.18.1 — AlphaEvolve: implementacja i weryfikacja

## Główne źródła

1. *AlphaEvolve: A coding agent for scientific and algorithmic discovery*, 2025, 44 strony (dołączony PDF).
2. Oficjalny kod `google-deepmind/alphaevolve`, `src/`, commit
   `c42694909d50f92cb01c2d50916f022b1c7e74d1` (11 listopada 2026),
   https://github.com/google-deepmind/alphaevolve/tree/c42694909d50f92cb01c2d50916f022b1c7e74d1/src.
   Repozytorium oficjalnie opisuje `/src` jako **minimalną** implementację
   z lokalną ewaluacją. Jest udostępnione na licencji Apache-2.0.
   Kod oficjalny nie jest kopiowany do tej paczki; jego wykonanie nie zostało
   zweryfikowane w tym środowisku. Do uruchomienia przykładu wydawca wymaga
   m.in. Dockera, zależności oraz klucza API Gemini.

## Wymagania i stan faktyczny

| Zakres publikacji | NOEVARIS | Status weryfikacji |
|---|---|---|
| §2.1 Zadania z automatycznym `evaluate` | Publiczne metryki MSE, AST; dodatkowa niezależna weryfikacja Q[x] | Lokalnie |
| §2.2 Prompt sampler | Kontekst z archiwum, ślady promptów SHA-256, istniejąca ewolucja meta-promptów | Lokalnie |
| §2.3 Kodowanie propozycji | Zmiany `SEARCH/REPLACE` wewnątrz oznaczonych bloków | Lokalnie; tylko bounded AST |
| §2.3 Ensemble LLM | Transport API OpenAI-compatible, routing i kontrola kosztów | Testy localhost; **bez prawdziwego LLM** |
| §2.4 Kaskadowa ocena | Publiczne etapy, niezależny holdout, dokładny dowód Q[x] | Lokalnie |
| §2.4 Niezaufany kod | Interpreter o ograniczonej gramatyce; interfejs gVisor OCI | Interpreter zweryfikowany; **runsc E2E niewykonany** |
| §2.5 Baza populacji | SQLite, genealogia, Pareto, wyspy, MAP-Elites-inspired | Lokalnie |
| §2.6 Pętla autonomiczna | **NOWE**: generator mutacji AST → prompt → patch → ocena → rejestr → selekcja | **Pełny lokalny cykl**, bez LLM i obcego kodu |
| §2.6 Recovery | **NOWE**: atomowy zapis potomka, zdarzenia i checkpointu w jednej transakcji SQLite | Test restartu i zgodności wyniku |
| §3–4 Wyniki naukowe Google | Dokumentacja i weryfikacja bounded Q[x] | **Nieodtworzone** |
| Oficjalne `google-deepmind/alphaevolve/src` | Wskazany SHA upstream, gotowa ścieżka włączenia w odrębnym środowisku | **Niepobrany lokalnie, nieuruchomiony** |

## Eksperyment wykonany lokalnie

Uruchomienie nowej komendy (bez API i bez wykonania wygenerowanego kodu):

```bash
python -m noevaris.cli alpha-autonomous \
  --db experiment.sqlite \
  --program-file examples/alpha_program.json --entry solver.py \
  --campaign alpha-local-v1 --seed 2 --steps 192 \
  --problem quadratic \
  --holdout-file examples/alpha_final_holdout.json \
  --holdout-max-mse 1e-9 \
  --proof-reference 'x*x+1'
```

Odtworzony wynik: 192 iteracje, 33 zapisane programy,
MSE publiczne 41.0 → 0.0, holdout `passed=true`,
matematyczna tożsamość w Q[x] `verified=true`.
To dowód poprawności lokalnej **symbolicznej regresji kwadratowej**,
nie osiągnięć Google DeepMind, nie świadomości AGI i nie bezpieczeństwa
niezaufanego Pythona w sandboxie.

### Bezpieczeństwo i ograniczenia

- Wygenerowany kod nie jest wykonywany: AST interpreter ma gramatykę ograniczoną
  do `x`, liczb, `+`, `-`, `*`, `/` z limitami zasobów.
- `holdout` jest wyłącznie oceną końcową, jednokrotną na kampanię. Przy braku
  separacji procesów nie jest to gwarancja kryptograficznej tajności danych.
- Checkpoint ma status po ostatniej **zatwierdzonej** transakcji. Podczas restartu
  wymagana jest zgodność seed, budżetu, polityki i pełnych danych publicznych.
- Archiwum i jego SHA-256 wykrywają przypadkową korupcję, lecz nie zapewniają
  niemodyfikowalności wobec administratora hosta.
- Nie wykonano pracy na fizycznych układach neuromorficznych, z prawdziwym
  `runsc`, z Gemini ani reprodukcji odkryć 4×4/48 mnożeń z publikacji.

## Bramka zamknięcia pełnej reprodukcji oryginalnego systemu

**OTWARTA**: wykonanie oficjalnego kodu na rzeczywistym środowisku Docker,
wywołania modelu Gemini, niezależna weryfikacja opublikowanych danych
matematycznych i wieloetapowych eksperymentów oraz porównanie parametrów
z publikacją. Nie są to funkcje, których ukończenie może potwierdzić lokalny
symulator bez powyższych zasobów.

### Niezależny replay zapisanej kampanii

Po rozpakowaniu ZIP, w katalogu głównym projektu:

```bash
python -m noevaris.cli alpha-replay-audit \
  --db evidence/alpha_quadratic.sqlite \
  --program-file examples/alpha_program.json --entry solver.py \
  --campaign alpha-local-v1 --seed 2 --steps 192 --problem quadratic
```

Audyt przebudowuje drugą bazę od zera i porównuje wszystkie programy,
zdarzenia i prompty. Oczekiwane: `events_verified=192`,
`programs_verified=33`, `matches=true`. Raporty:
`docs/ALPHAEVOLVE_V1181_EXPERIMENT.json` oraz
`docs/ALPHAEVOLVE_V1181_REPLAY_AUDIT.json`.

### Pobranie opublikowanego oficjalnego źródła (poza bieżącym środowiskiem)

```bash
python -m tools.official_alphaevolve \
  --destination ./official-alphaevolve-src \
  --allow-network
```

Importer jest przypięty do wyżej wymienionego commita i wymaga jawnej
zgody na sieć, weryfikuje ścieżki archiwum, blokuje symlinki, limity rozmiarów
i nie nadpisuje istniejących danych. Sam import **nie uruchamia kodu**.
Dalsze uruchomienie oficjalnych przykładów wymaga przygotowania odizolowanego
środowiska według README wydawcy, zależności i dostępu do modeli. Nie należy
wykonywać propozycji LLM na hoście bez izolacji.

### Aktualna baza dowodowa

- `python -m unittest discover -s tests -q`: **207 testów PASS** (2026-11-12).
- `python -m compileall -q noevaris omega_x_mind_engine tools tests`: PASS.
- `tests/test_autonomous_alpha.py`: TDD, checkpoint/restart,
  prewencja włączenia holdout do feedbacku, CLI, niezależny replay.
- `tests/test_official_upstream.py`: kontrakty importu, ZIP traversal, symlink.
