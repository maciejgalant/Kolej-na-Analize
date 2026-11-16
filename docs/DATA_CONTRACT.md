# Kontrakt danych i migracje (v1.0, RSA-003)

Uszczegółowienie sekcji „Schematy PostGIS” z [ARCHITECTURE.md](ARCHITECTURE.md). Źródłem prawdy są migracje w `backend/migrations/versions/`; ten dokument opisuje reguły, których muszą się trzymać importy (RSA-004…009), analizy (RSA-010) i API (RSA-011).

## Reguły wspólne
1. **Układ współrzędnych:** każda geometria w EPSG:2180; baza odrzuca inny SRID.
2. **Brak danych to `NULL`, nie 0.** `0` oznacza potwierdzoną wartość zerową. Dotyczy m.in. `train_count`, `vehicles_count`, `rps`, `components.value`.
3. **Pochodzenie:** każdy rekord danych zewnętrznych ma `source_id` → `system.sources`, a źródło ma licencję w `system.licenses`. Pola `allows_storage` / `allows_derivatives` równe `NULL` znaczą „niezweryfikowane”, nie „dozwolone”.
4. **Dane demonstracyjne** pochodzą ze źródła z `is_demo = true` (a przebiegi analiz mają `analysis.runs.is_demo`), żeby UI mogło je jawnie oznaczyć.
5. **Duplikaty:** obiekty z importu są unikalne po `(source_id, source_object_id)`; zdarzenia kolejowe po `(source_id, source_train_id, service_date, sequence_no)`; pomiary drogowe po `(source_id, station_id, okres, direction)`.
6. **Czas:** `timestamptz`; okresy jako `period_start` (włącznie) i `period_end` (wyłącznie), `period_end > period_start`. Granice doby liczone w Europe/Warsaw po stronie importu.
7. **Jednostki** są zapisane w kolumnie `unit`; prędkość (`road.live_flow`, km/h) i natężenie (`road.measurements`, pojazdy/okres) to osobne tabele.

## Słowniki (wymuszane przez CHECK)
| Pole | Wartości |
|---|---|
| `spatial.crossings.verification_status` | `unverified`, `verified`, `rejected_grade_separated`, `rejected_other` |
| `spatial.crossings.category` | `A`–`F` lub `NULL` (nieznana) |
| `crossing_*_segments.match_method` | `manual`, `topology`, `proximity_candidate` |
| `rail.crossing_flow.evidence_type` | `planned`, `observed`, `modelled` |
| `rail.operation_events.status` | `on_time`, `delayed`, `cancelled`, `partial`, `unknown` |
| `quality_status` (pomiary, wyniki) | `ok`, `partial`, `modelled`, `unknown` |
| `safety.crossing_attributes.confidence_status` | `confirmed`, `probable`, `unknown` |
| `safety.incidents.location_confidence` | `exact`, `approximate`, `unknown` |
| `analysis.runs.status`, `system.import_jobs.status` | `running`, `completed`/`succeeded`, `failed` |
| `analysis.components.component` | `T`, `P`, `G`, `H` |
| `analysis.components.status` | `ok`, `modelled`, `unknown` |
| `road.crossing_stations.match_type` | `direct` (pomiar zastępuje model w RPS), `validation` (tylko porównanie), `intersection` (skrzyżowanie: karta i raport, bez wpływu na RPS) |

## Reguły wymuszane przez bazę
- Przejazd o statusie innym niż `unverified` musi mieć `verified_at`. API i ranking używają wyłącznie `verified`; skrzyżowania bezkolizyjne zostają w ewidencji jako `rejected_grade_separated`, żeby nie wracały przy kolejnym imporcie.
- Przejazd ↔ odcinek torów/drogi to relacje M:N z metodą i pewnością dopasowania; `proximity_candidate` nie jest potwierdzonym powiązaniem.
- `analysis.risk_scores`: bez `rps` nie ma pozycji `rank`. Ranking częściowy oznacza `is_partial = true` i `completeness_pct`.
- `analysis.components`: status `unknown` ⇔ `value IS NULL`. Waga jest zapisywana przy każdym składniku, więc przebieg jest odtwarzalny bez znajomości kodu.
- Przebieg `completed`/`failed` i zadanie importu `succeeded`/`failed` muszą mieć `finished_at`. UI czyta tylko ostatni przebieg `completed`.
- `road.live_flow.expires_at` jest obowiązkowe; usuwanie wygasłych rekordów to zadanie workera (RSA-008).

## Decyzje do potwierdzenia
Poniższe szczegóły nie wynikały wprost z dokumentacji i zostały przyjęte przy implementacji:
- ~~Kategorie przejazdów `A`–`F`~~ — potwierdzone w RSA-004: rozporządzenie z 20.10.2015 r. (§ 5) i rejestr UTK używają dokładnie tych liter.
- `safety.crossing_attributes` w układzie klucz–wartość (`attribute_code`, `value_text`/`value_num`), bo lista cech zabezpieczeń nie jest jeszcze znana.
- `rail.*_events` wskazują stację tekstem (`station_ref`) i opcjonalnie odcinek; osobna tabela stacji powstanie, jeśli okaże się potrzebna w RSA-006.
- ~~Reguła przypisania przejazdu na granicy dzielnic~~ — ustalona w RSA-005: punkt w poligonie, na granicy niższy kod TERYT, flaga do 10 m od granicy (szczegóły w DATA_SOURCES.md).

## Migracje
- Narzędzie: Alembic, migracje pisane jawnie w SQL, bez autogeneracji.
- `docker compose up` uruchamia tylko `alembic upgrade head` (usługa `migrate`). Cofanie jest wyłącznie ręczne: `docker compose run --rm migrate alembic downgrade -1`.
- Każda migracja ma działający `downgrade`; CI sprawdza na PostGIS pełny cykl `upgrade → downgrade → upgrade` oraz odwracalność każdego kroku.
- `downgrade` usuwa schematy razem z danymi. Przed cofnięciem na bazie z danymi rzeczywistymi zrobić zrzut.
- Rozszerzenie `postgis` nie jest usuwane przy cofaniu.

| Rewizja | Zakres |
|---|---|
| 0001 | `system`: licenses, sources, import_jobs, quality_flags |
| 0002 | `spatial`: districts, crossings, rail/road_segments, relacje M:N |
| 0003 | `rail`: schedule_events, operation_events, crossing_flow; `road`: measurements, live_flow |
| 0004 | `safety`: crossing_attributes, incidents; `analysis`: runs, risk_scores, components |
| 0005 | `spatial.rail_segments` / `road_segments`: położenie względem gruntu, stan, funkcja toru, liczba torów, kategoria zarządzania, numer drogi |
| 0006 | `analysis.risk_scores`: rank_best, rank_worst (analiza wrażliwości wag) |
| 0007 | `road`: stations (punkty pomiarowe), crossing_stations (przejazd ↔ punkt, `direct`/`validation`); `road.measurements`: `day_type`, `hourly_profile` (24 wartości), `days_count` |
| 0008 | `road.measurements`: `composition` (pojazdy według rodzaju), `pedestrians`, `cyclists`; `road.crossing_stations.match_type` + `intersection` |
| 0009 | `rail.crossing_flow`: `hourly_profile` (24 wartości, dzień kalendarzowy przejazdu), `hourly_unplaced` |


## Kontrakt rozmowy i wyników UI (2026-11-15)
`POST /api/v1/assistant/chat` przyjmuje `message` (1–500 znaków), `history` (maks. 8 pozycji `user`/`assistant`, każda do 2000 znaków) i opcjonalny `crossing_id` (dodatnia liczba całkowita lub null). Dołączony przejazd jest odczytywany przez backend po ID; brak obiektu w obszarze analizy daje 404. Model nie otrzymuje uprawnień zapisu.

Odpowiedź zachowuje `answer`, `model`, `grounded`, `tool_calls`, `disclaimer` i dodaje `evidence`:

| Pole | Zawartość |
|---|---|
| `cards` | `crossing_id`, `title`, `district`, `category`, `rps`, `rank`, `trains` |
| `tables` | `title`, `columns`, `rows` (komórka: tekst/liczba/null) |
| `charts` | `title`, `unit`, `points`: `label`, `value` (liczba/null), `status` |
| `sources` | Nazwy i atrybucje źródeł pobrane z bazy |
| `notes` | Wyjaśnienia, okresy, kompletność i ograniczenia |
| `map_ids` | Dodatnie ID przejazdów z udanych odczytów, bez duplikatów, maks. 60 |

Status punktu wykresu: `ok`, `modelled`, `unknown`, `planned`, `measured`. Wartości liczbowe muszą być skończone. Null zachowuje znaczenie braku danych. Nie ma pola pozwalającego modelowi przesłać HTML, kod ani dowolne instrukcje do wykonania. Dane tworzy `assistant/presentation.py` z udanych odczytów narzędzi, a nie z parsowania tekstu LLM. Stare odpowiedzi tekstowe bez `evidence` pozostają obsługiwane przez frontend.

Format przeglądarkowy ma `version: 1`, `active` i listę `conversations`. Rozmowa zawiera metadane, wiadomości z `id`/`parent`, `leaf`, szkic, opcjonalny kontekst i stan mapy. Odpowiedzi z `evidence` są zapisywane przy wiadomościach, więc przyciski starszych wyników działają po odświeżeniu. Ten zapis nie jest synchronizowany między urządzeniami ani kontami. Nie wymaga migracji PostGIS.

