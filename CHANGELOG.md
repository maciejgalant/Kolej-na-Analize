# Historia zmian

Format według [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/), numeracja według [Semantic Versioning](https://semver.org/lang/pl/).
Sekcja wersji jest treścią wydania na GitHubie (workflow `release.yml`).

## [Unreleased]

### Usunięto
- Nieużywane komponenty `FloatingWindow` i `RailPanel` po przebudowie interfejsu oraz około 1100 linii martwych reguł CSS i nieużywanych animacji.

### Zmieniono
- Logo zmniejszone do 1100×367 px (214 KB zamiast 760 KB), bez utraty kolorów.

## [1.0.0] - 2026-11-17

Pierwsze wydanie: wersja zgłoszeniowa do konkursu PKP PLK „Kolej na bezpieczeństwo” (II edycja).
Ranking RPS jest eksperymentalnym priorytetem do dalszej oceny, a nie oficjalną oceną ryzyka wypadku.

### Dodano
- Środowisko lokalne Docker Compose: PostGIS, FastAPI, frontend (nginx), Ollama; porty tylko na 127.0.0.1, healthcheck `/api/v1/health` (RSA-002).
- Migracje Alembic 0001–0010 z kontraktem danych i testami migracji (RSA-003).
- Ewidencja przejazdów z warstwy UTK w Geoportalu z kontrolą krzyżową w OpenStreetMap i raportem audytu (RSA-004).
- Dzielnice z PRG, tory i jezdnie z BDOT10k, weryfikacja geometryczna przejazdów (RSA-005).
- Planowy ruch pociągów z otwartego GTFS (z WKD) i rozkład pociągów w ciągu doby (RSA-006/009, RSA-018).
- Pomiary ruchu drogowego ZDM: punkty APR (RSA-007) i pomiary na skrzyżowaniach (RSA-017).
- Eksperymentalny wskaźnik priorytetu RPS `rps-0.5-exp` z analizą wrażliwości i raportem (RSA-010).
- API przejazdów, dzielnic, rankingu, kolei i incydentów z kontraktem OpenAPI (RSA-011).
- Interfejs rozmów z historią i gałęziami, mapa modalna z filtrami i podkładami, karta przejazdu z wykresami (RSA-012, RSA-CHAT-01…05).
- Asystent AI na lokalnym modelu Qwen (Ollama) z sześcioma funkcjami tylko do odczytu i odmową przy brakach danych (RSA-013); opcjonalna karta NVIDIA (`docker-compose.gpu.yml`).
- Zestaw demonstracyjny bez internetu i kluczy API (`load-demo`), oznaczony w interfejsie i API (RSA-014).
- Integracja z API PKP PLK (klucz tylko w backendzie, adapter wyłączony bez klucza).
- Częściowa historia zdarzeń SEWiK (20 rekordów) z dopasowaniem do przejazdów po ulicy.
- Identyfikacja wizualna „Kolej na Analizę” (logo, kolory, ikona).
- CI: lint i testy backendu z PostGIS, testy i build frontendu, testy Playwright, uruchomienie stosu Compose z zestawem demo.
- Licencja MIT, historia zmian i proces wydania (`docs/RELEASE.md`).

### Znane ograniczenia
- Rzeczywiste wykonanie rozkładu czeka na klucz API PKP PLK; ranking używa ruchu planowego (RSA-006).
- Punkt pomiarowy ZDM na tej samej ulicy mają tylko 3 z 36 przejazdów drogowych; pozostałe korzystają z szacunku z klasy drogi.
- Historia zdarzeń SEWiK jest częściowa i nie wpływa na RPS (składnik H nieznany).
- Warunki ponownego wykorzystania części danych (GTFS PLK/KM, ZDM) są oznaczone jako niepotwierdzone, zob. `docs/DATA_SOURCES.md`.
- Bez karty graficznej odpowiedź asystenta trwa minuty.

[Unreleased]: https://github.com/maciejgalant/Kolej-na-Analize/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/maciejgalant/Kolej-na-Analize/releases/tag/v1.0.0
