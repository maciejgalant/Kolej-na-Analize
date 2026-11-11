# RailSafe AI

**System analizy ekspozycji na ruch oraz priorytetów bezpieczeństwa przejazdów kolejowo-drogowych w Warszawie.**

Projekt edukacyjny przygotowywany do konkursu „Kolej na bezpieczeństwo”. Aplikacja lokalna (Docker Compose, FastAPI, PostGIS, Leaflet, Ollama/Qwen) ma łączyć dane kolejowe, drogowe i charakterystyki przejazdów, prezentować mapę, ranking oraz uzasadnienia wyników poprzez asystenta AI.

> Status: **projektowanie / specyfikacja, bez gotowej implementacji**. Nie traktować rankingów demonstracyjnych jako oficjalnych ocen ryzyka wypadku.

## Dokumentacja
- [Założenia i wymagania](docs/PROJECT_SPEC.md)
- [Architektura i model danych](docs/ARCHITECTURE.md)
- [Źródła danych, jakość i licencje](docs/DATA_SOURCES.md)
- [Metodyka oceny i walidacja](docs/ANALYSIS_METHOD.md)
- [Frontend i system wizualny](docs/FRONTEND_DESIGN.md)
- [Backlog i harmonogram](docs/BACKLOG.md)

## Planowane uruchomienie
`docker compose up -d --build` → `http://localhost:8080`.
To **kontrakt docelowy**, nie obecnie działające polecenie.

## Wykorzystanie istniejących projektów
- [GeoGraph Demo 3](https://github.com/maciejgalant/GeoGraph-demo-03): inspiracja dla FastAPI/PostGIS/Ollama, selektora analiz i Docker Compose.
- [PSIP MG L1](https://github.com/maciejgalant/PSIP_MG_L1): inspiracja dla importu BDOT10k oraz operacji przestrzennych.

Kod i dane są przenoszone wyłącznie po sprawdzeniu licencji, zależności i pochodzenia. Projekt nie jest oficjalną aplikacją PKP PLK ani PKP Intercity.

## Zakres MVP
Warszawa i 18 dzielnic; weryfikowane lokalizacje przejazdów; planowane i (gdy dostępne) potwierdzone przejazdy kolejowe; publiczne pomiary ruchu drogowego; licencjonowane źródła live jako opcjonalne; ranking **priorytetu do dalszej oceny**, mapa i asystent AI odpowiadający na podstawie danych z backendu.

**Data specyfikacji:** 2026-11-11.
