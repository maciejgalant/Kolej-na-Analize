# Wydania

Numeracja według [Semantic Versioning](https://semver.org/lang/pl/): `MAJOR.MINOR.PATCH`.
Numer wersji jest w trzech miejscach i musi się zgadzać z tagiem:

| Miejsce | Pole |
|---|---|
| `backend/app/config.py` | `APP_VERSION` (zwracane przez `/api/v1/health`) |
| `frontend/package.json` i `package-lock.json` | `version` (`npm version X.Y.Z --no-git-tag-version`) |
| `CHANGELOG.md` | sekcja `## [X.Y.Z] - RRRR-MM-DD` |

Workflow `.github/workflows/release.yml` po wypchnięciu tagu `vX.Y.Z` sprawdza zgodność wersji i tworzy wydanie na GitHubie z notatkami z sekcji `CHANGELOG.md`.

## Lista kontrolna

1. Gałąź `release/vX.Y.Z` z `main`: podbicie wersji, przeniesienie wpisów z `[Unreleased]` do nowej sekcji, data, linki porównania na końcu `CHANGELOG.md`.
2. PR do `main`, zielone CI (backend z PostGIS, frontend z Playwright, stos Compose z zestawem demo), merge.
3. Sprawdzenie na czystej instalacji (osobny projekt Compose, żeby nie ruszać danych roboczych):
   ```bash
   docker compose -p kna-release up -d --build
   docker compose -p kna-release run --rm worker python -m app.worker load-demo
   curl -s http://localhost:8765/api/v1/health   # "version":"X.Y.Z", baza "ok", demo_data true
   docker compose -p kna-release down -v
   ```
   Przy zajętych portach ustaw inne `POSTGIS_HOST_PORT`, `BACKEND_HOST_PORT` i `FRONTEND_HOST_PORT` w `.env` tylko na czas testu.
4. Tag na zmergowanym commicie `main`:
   ```bash
   git switch main && git pull --ff-only
   git tag -a vX.Y.Z -m "Kolej na Analizę vX.Y.Z"
   git push origin vX.Y.Z
   ```
5. Sprawdzenie wydania w zakładce Releases (notatki, archiwa źródeł).

## Poprawki po wydaniu
Błąd w wydanej wersji: gałąź `fix/...`, wpis w `[Unreleased]` w sekcji „Naprawiono”, potem wydanie `X.Y.(Z+1)` według tej samej listy. Tagów nie przesuwamy ani nie nadpisujemy.
