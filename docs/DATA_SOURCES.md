# Źródła danych, pokrycie, licencje i retencja (v1.0)

## Macierz danych
| Zbiór | Cel | Kandydat | Krytyczne sprawdzenie |
|---|---|---|---|
| Przejazdy w poziomie szyn | Centralna ewidencja | PLK / OSM + kontrola | Kompletność, rodzaj przejazdu, geometria, identyfikator |
| Kategoria i zabezpieczenia | Czynniki ryzyka | PLK / oficjalne metryki | Dostępność na poziomie konkretnego obiektu |
| Dzielnice | Filtrowanie | PRG / miasto Warszawa | Wersja granic i reguła przydziału granicznego |
| Linie i drogi | Map matching | OSM / BDOT10k | Topologia, aktualność, prawo wykorzystania |
| Rozkład pociągów | Kursy planowane | PDP API PKP PLK | Zakres, limit, identyfikacja odcinków |
| Wykonanie pociągów | Porównanie z planem | PDP API PKP PLK | Semantyka zdarzeń, brak pełnego GPS, opóźnienia |
| Ruch drogowy (liczba pojazdów) | Ekspozycja drogowa | APR / pomiary ZDM Warszawa | Zasięg liczników, okres, kierunek, warunki ponownego użycia |
| Bieżąca prędkość / korki | Warstwa warunków ruchu | TomTom / HERE | Koszt, licencja, buforowanie, użycie jako wejście obliczeń |
| Pociągi towarowe | Kompletność ruchu | Dane zarządcy | Brak potwierdzonego pełnego publicznego API |
| Incydenty i wypadki | Walidacja ryzyka | PKBWK / PLK / SEWiK | Dokładna lokalizacja, definicja zdarzenia, zgodność czasowa |

## Zasady jakości
1. Nie zakładać, że przecięcie linii na mapie jest przejazdem w jednym poziomie.
2. Nie utożsamiać liczby rozkładowych pociągów z faktycznie zrealizowanymi wszystkimi kursami; towarowe mogą nie być pokryte.
3. Nie wyliczać liczby pojazdów/h z samej prędkości Traffic API. Model szacunkowy wymaga osobnej metody i oznaczenia.
4. Przypisanie pomiaru do przejazdu wymaga zgodności topologicznej, kierunku i czasu; odległość euklidesowa jest tylko wstępnym kandydatem.
5. Zawsze zachować metadane źródła, licencję, zakres terytorialny, okres, moment importu i status walidacji.
6. Nie wypełniać braków danymi 0.

## Reguły licencyjne
- Dane publiczne: sprawdzić warunki ponownego wykorzystania, wymagane oznaczenie i ewentualne ograniczenia zbioru.
- OSM: przestrzegać ODbL i atrybucji; zweryfikować obowiązki przy bazach pochodnych.
- TomTom / HERE: prawo do prezentacji warstwy, map matching, własnego scoringu, cache i retencji należy sprawdzić **oddzielnie** w aktualnym planie. Nie umieszczać w repo treści pobranych z płatnego API.
- PKP PLK: sprawdzić warunki klucza, licencji, limitów i przypisania źródła.
- Dane zewnętrzne w PostGIS: przechowywać tylko dozwolony zakres i TTL; własne wyniki pochodne też mogą podlegać ograniczeniom.
- Branding: RailSafe AI jest niezależnym projektem; nie umieszczać logotypów ani znaków PKP Intercity jako własnych.

## Pierwszy eksperyment danych (spike)
**Cel:** zbudować tabelę 10–20 ręcznie zweryfikowanych przejazdów w Warszawie i wykazać, dla ilu jest dostępna miara kolejowa, drogowa i infrastrukturalna. Raport `docs/DATA_AUDIT.md` powinien zawierać liczbę obiektów w każdej kategorii, przykłady błędów map matching, licencje, statystyki kompletności i decyzję GO/NO-GO dla rankingu.

## Linki
- https://pdp-api.plk-sa.pl/api-documentation
- https://zdm.waw.pl/dzialania/badania-i-analizy/analiza-ruchu-na-drogach/
- https://docs.tomtom.com/traffic-api/
- https://docs.here.com/traffic-api/
- https://www.openstreetmap.org/copyright
Linki wskazują kandydatów i dokumentację, nie potwierdzają automatycznie licencji wszystkich zastosowań.
