# Backlog i plan MVP konkursowego (v1.1)
Data odniesienia: 2026-11-11. Termin zgłoszenia: 22.11.2026 do końca dnia, e-mail konkurs-studenci@plk-sa.pl (regulamin z 16.11.2026, §6). Podstawowa forma: prezentacja PPTX/PDF do 20 slajdów lub dokument DOCX/PDF do 15 stron; kod źródłowy i link do demo jako materiały uzupełniające (§5).

| ID | Zadanie | Zależności | Priorytet | Kryterium zakończenia | Stan |
|---|---|---|---|---|---|
| RSA-001 | Repo, README, docs, zasady Git | — | P0 | Struktura i dokumentacja wersjonowana | zrobione |
| RSA-002 | Docker, FastAPI, PostGIS, frontend, Ollama | 001 | P0 | Healthcheck + localhost | zrobione |
| RSA-003 | Migracje, schematy i kontrakt danych | 001 | P0 | Test migracji i rollbacku | zrobione |
| RSA-004 | Inwentaryzacja zweryfikowanych przejazdów | 003 | P0 | Audyt pokrycia, przejazdy bezkolizyjne wykluczone | zrobione |
| RSA-005 | Dzielnice, drogi, tory i topologia | 003 | P0 | Geometrie EPSG:2180, relacje M:N | zrobione |
| RSA-006 | Adapter PKP PLK, plan i wykonanie | 002,003 | P0 | Test limitu i przykładowego kursu | częściowo: plan z GTFS; wykonanie czeka na klucz API PKP PLK |
| RSA-007 | Dane ZDM i jakość dopasowania do odcinków | 003,005 | P0 | Raport stanowisk i zasięgu | zrobione (APR, #23) |
| RSA-008 | Licencja i próbny adapter Traffic API | 002 | P1 | GO/NO-GO z udokumentowanymi prawami | zamknięte: NO-GO (TomTom, HERE) |
| RSA-009 | Matchowanie kursów i ruchu do przejazdu | 004–007 | P0 | Testy topologii, czasu i deduplikacji | zrobione (plan) |
| RSA-010 | RPS, brakujące dane i analiza wrażliwości | 009 | P0 | Wersja metody i walidacja | zrobione (rps-0.5-exp) |
| RSA-011 | API dla przejazdów i rankingów | 003,010 | P0 | Kontrakt OpenAPI i testy | zrobione |
| RSA-012 | Interfejs analityczny w stylistyce kolejowej | 011 | P0 | Mapa, filtry, karty i wykresy | rozszerzony o interfejs rozmów; porównanie dzielnic w tabeli, osobny dashboard porównawczy poza tym etapem |
| RSA-013 | Qwen: wybór bezpiecznych funkcji i wyjaśnienia | 011 | P0 | Test 5 intencji i odmowy przy brakach | zrobione |
| RSA-014 | Testy integracyjne, syntetyczny demo-set | 010–013 | P0 | Uruchomienie bez kluczy API | zrobione |
| RSA-015 | Dokumentacja konkursowa i prezentacja | 010–014 | P0 | Jasne źródła, ograniczenia, wpływ na bezpieczeństwo | do zrobienia |
| RSA-016 | Scenariusz demo i zgłoszenie | 014,015 | P0 | Kompletny pakiet do wysyłki | do zrobienia |
| RSA-REL | Wydanie v1.0.0 | 014 | P0 | Licencja, CHANGELOG, zgodne wersje, tag i wydanie na GitHubie | w toku (PR release/v1.0.0) |

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


## Etap interfejsu rozmów — 2026-11-15
| ID | Zakres | Kryterium |
|---|---|---|
| RSA-CHAT-01 | Układ rozmów i kolejowa stylistyka | Historia po lewej, czat po prawej, powitanie, szkic i kopiowanie |
| RSA-CHAT-02 | Historia i gałęzie | Zapis po odświeżeniu, zmiana tytułu, wyszukiwanie, przypinanie, usuwanie, edycja i ponawianie bez utraty poprzednich wersji |
| RSA-CHAT-03 | Mapa modalna i kontekst | Ręczne otwarcie, filtry, podkłady, szczegóły, dołączenie przejazdu bez automatycznej wysyłki, stan mapy per rozmowa |
| RSA-CHAT-04 | Wyniki asystenta | Walidowany kontrakt kart/tabel/wykresów/źródeł i ID mapy wyłącznie z danych backendu |
| RSA-CHAT-05 | Weryfikacja i dokumentacja | Testy logiki historii, kontraktu backendu, scenariusze Playwright i build w CI |

Zakres wyłączony z tego etapu: konta, synchronizacja historii, wersja mobilna, eksporty, strumieniowanie i gwarantowane anulowanie inferencji w Ollamie.
