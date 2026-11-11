# Backlog i plan MVP konkursowego (v1.0)
Data odniesienia: 2026-11-11. Zakładany termin zgłoszenia: 2026-11-22 (potwierdzić w oficjalnym regulaminie tuż przed wysyłką).

| ID | Zadanie | Zależności | Priorytet | Kryterium zakończenia |
|---|---|---|---|---|
| RSA-001 | Repo, README, docs, zasady Git | — | P0 | Struktura i dokumentacja wersjonowana |
| RSA-002 | Docker, FastAPI, PostGIS, frontend, Ollama | 001 | P0 | Healthcheck + localhost |
| RSA-003 | Migracje, schematy i kontrakt danych | 001 | P0 | Test migracji i rollbacku |
| RSA-004 | Inwentaryzacja zweryfikowanych przejazdów | 003 | P0 | Audyt pokrycia, przejazdy bezkolizyjne wykluczone |
| RSA-005 | Dzielnice, drogi, tory i topologia | 003 | P0 | Geometrie EPSG:2180, relacje M:N |
| RSA-006 | Adapter PKP PLK, plan i wykonanie | 002,003 | P0 | Test limitu i przykładowego kursu |
| RSA-007 | Dane ZDM i jakość dopasowania do odcinków | 003,005 | P0 | Raport stanowisk i zasięgu |
| RSA-008 | Licencja i próbny adapter Traffic API | 002 | P1 | GO/NO-GO z udokumentowanymi prawami |
| RSA-009 | Matchowanie kursów i ruchu do przejazdu | 004–007 | P0 | Testy topologii, czasu i deduplikacji |
| RSA-010 | RPS, brakujące dane i analiza wrażliwości | 009 | P0 | Wersja metody i walidacja |
| RSA-011 | API dla przejazdów i rankingów | 003,010 | P0 | Kontrakt OpenAPI i testy |
| RSA-012 | Dashboard w stylistyce kolejowej | 011 | P0 | Mapa, filtry, karty i wykresy |
| RSA-013 | Qwen: wybór bezpiecznych funkcji i wyjaśnienia | 011 | P0 | Test 5 intencji i odmowy przy brakach |
| RSA-014 | Testy integracyjne, syntetyczny demo-set | 010–013 | P0 | Uruchomienie bez kluczy API |
| RSA-015 | Dokumentacja konkursowa i prezentacja | 010–014 | P0 | Jasne źródła, ograniczenia, wpływ na bezpieczeństwo |
| RSA-016 | Scenariusz demo i zgłoszenie | 014,015 | P0 | Kompletny pakiet do wysyłki |

## Harmonogram
11–12 XI: infrastruktura, dane i rozpoznanie licencji.
13–14 XI: ewidencja przejazdów, granice, geometrie.
15–16 XI: kolej i drogi, raport pokrycia.
17–18 XI: dopasowanie, wskaźnik i API/mapa.
19 XI: asystent AI i wykresy.
20 XI: testy/QA.
21 XI: dokumentacja konkursowa, nagranie demonstracyjne.
22 XI: finalne zgłoszenie.

## Krytyczna ścieżka
003 → 004/005/007 + 006 → 009 → 010 → 011 → 012/013 → 014 → 016.
Jeśli danych brakuje, ograniczyć wiarygodny zakres analizowanych obiektów, zachowując mapę Warszawy i działający scenariusz demo.

## Reuse
- GeoGraph-demo-03: infrastruktura, katalog analiz, backend i mechanizm Qwen jako wzorce.
- PSIP_MG_L1: import BDOT10k i analizy przestrzenne jako wzorce.
- Kopiować moduły dopiero po audycie licencji, zależności, testów i wersji.

## Zasady pracy
Osobne branche `feature/RSA-###-opis`, PR + CI, brak bezpośrednich edycji main bez review; jawne migracje; niedestrukcyjne testy; dla danych realnych snapshoty z metadanymi i licencją; bez sekretów w Git. Zmiany kontraktów API i schematów wymagają uzgodnienia przed równoległą implementacją.
