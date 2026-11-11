# RailSafe AI

**System analizy ekspozycji na ruch oraz priorytetów bezpieczeństwa przejazdów kolejowo-drogowych w Warszawie.**

Projekt edukacyjny przygotowywany do konkursu „Kolej na bezpieczeństwo”. Aplikacja lokalna (Docker Compose, FastAPI, PostGIS, Leaflet, Ollama/Qwen) ma łączyć dane kolejowe, drogowe i charakterystyki przejazdów, prezentować mapę, ranking oraz uzasadnienia wyników poprzez asystenta AI.

> Status: **szkielet infrastruktury (RSA-002), bez danych i analiz**. Nie traktować rankingów demonstracyjnych jako oficjalnych ocen ryzyka wypadku.

## Dokumentacja
- [Założenia i wymagania](docs/PROJECT_SPEC.md)
- [Architektura i model danych](docs/ARCHITECTURE.md)
- [Źródła danych, jakość i licencje](docs/DATA_SOURCES.md)
- [Metodyka oceny i walidacja](docs/ANALYSIS_METHOD.md)
- [Frontend i system wizualny](docs/FRONTEND_DESIGN.md)
- [Backlog i harmonogram](docs/BACKLOG.md)

## Uruchomienie lokalne
Wymagany Docker z Compose v2.

```bash
cp .env.example .env        # ustaw POSTGRES_PASSWORD
docker compose up -d --build
docker compose ps           # wszystkie usługi powinny być "healthy"
```

| Usługa | Adres (tylko 127.0.0.1) |
|---|---|
| Frontend | http://localhost:8080 |
| Backend, healthcheck | http://localhost:8765/api/v1/health |
| Backend, OpenAPI | http://localhost:8765/api/v1/docs |
| PostGIS | localhost:55432 (zmienna `POSTGIS_HOST_PORT`) |

Przy pierwszym uruchomieniu usługa `ollama-pull` pobiera model (`OLLAMA_MODEL`, kilka GB). Do tego czasu healthcheck zwraca `degraded`, a mapa i backend działają normalnie. Worker: `docker compose run --rm worker`.

Na tym etapie aplikacja pokazuje tylko mapę podkładową i stan usług — ewidencja przejazdów, ranking i asystent AI są w kolejnych zadaniach [backlogu](docs/BACKLOG.md).

### Praca nad kodem
- Backend: `cd backend && pip install -r requirements-dev.txt && ruff check . && pytest`
- Frontend: `cd frontend && npm ci && npm run dev` (proxy `/api` → `127.0.0.1:8765`)

## Wykorzystanie istniejących projektów
- [GeoGraph Demo 3](https://github.com/maciejgalant/GeoGraph-demo-03): inspiracja dla FastAPI/PostGIS/Ollama, selektora analiz i Docker Compose.
- [PSIP MG L1](https://github.com/maciejgalant/PSIP_MG_L1): inspiracja dla importu BDOT10k oraz operacji przestrzennych.

Kod i dane są przenoszone wyłącznie po sprawdzeniu licencji, zależności i pochodzenia. Projekt nie jest oficjalną aplikacją PKP PLK ani PKP Intercity.

## Zakres MVP
Warszawa i 18 dzielnic; weryfikowane lokalizacje przejazdów; planowane i (gdy dostępne) potwierdzone przejazdy kolejowe; publiczne pomiary ruchu drogowego; licencjonowane źródła live jako opcjonalne; ranking **priorytetu do dalszej oceny**, mapa i asystent AI odpowiadający na podstawie danych z backendu.

**Data specyfikacji:** 2026-11-11.
