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

## Ewidencja przejazdów — ustalenia RSA-004 (2026-11-11)
**BDOT10k nie zawiera przejazdów.** W sieci komunikacyjnej nie ma klasy przejazdu ani atrybutów kategorii czy zabezpieczeń; OT_OIKM_P obejmuje tylko stacje/przystanki i przejścia graniczne. Przydatne są tory (OT_SKTR_L: numer linii, liczba torów, położenie względem gruntu) i drogi.

**Źródło podstawowe: warstwa „Przejazdy kolejowe” UTK w Geoportalu.** Dane zarządców infrastruktury przekazywane przez UTK do GUGiK; usługa WMS `https://mapy.geoportal.gov.pl/wss/service/sdi/Przejazdy/get`.
- Dostępne atrybuty: numer identyfikacyjny (z żółtej naklejki), kategoria A–F, typ szlakowy/stacyjny, zarządca, telefony.
- Usługa to wyłącznie WMS: nie zwraca współrzędnych. Import odczytuje położenie ze środka symbolu na obrazie 1 m/px (dokładność rzędu kilku metrów), a atrybuty z GetFeatureInfo w tym punkcie.
- Brak szczegółów urządzeń, widoczności i pomiarów ruchu — te są w metryce przejazdu u zarządcy (niepublikowanej).
- Usługa nie deklaruje warunków ponownego wykorzystania; w `system.licenses` pozostaje to oznaczone jako niezweryfikowane. Danych z usługi nie commitujemy do repozytorium.
- Znane osobliwości: kategoria bywa zapisana małą literą; dla niektórych prostokątów serwer zwraca wyjątek zamiast obrazu (import przesuwa okno o kilka metrów).

**Kontrola krzyżowa: OpenStreetMap (Overpass API).** Punkty `railway=level_crossing` i `railway=crossing` leżące na torach kolejowych. Dają niezależne potwierdzenie, że w danym miejscu jest skrzyżowanie w poziomie szyn, oraz tagi urządzeń (`crossing:barrier`, `crossing:light`, `crossing:bell`) tam, gdzie je wprowadzono. Licencja ODbL, wymagana atrybucja.

**Reguła weryfikacji.** Obiekt z rejestru UTK dostaje status `verified`, gdy jego wzajemnie najbliższy punkt OSM leży nie dalej niż 40 m. Pozostałe zostają `unverified` z flagą `no_osm_confirmation` do ręcznego przeglądu. Statusów `rejected_*` nadanych ręcznie import nie nadpisuje. Przejścia kategorii E są importowane jak pozostałe; o ich udziale w rankingu zdecyduje metoda (RSA-010).

**Zakres przestrzenny.** Import obejmuje prostokąt wokół Warszawy; przypisanie do dzielnic i odcięcie obiektów spoza miasta należy do RSA-005.

Uruchomienie i raport: `docker compose run --rm worker python -m app.worker import-crossings` → `reports/DATA_AUDIT_crossings.md`.

## Dzielnice, tory i drogi — ustalenia RSA-005 (2026-11-11)
**Dzielnice: Państwowy Rejestr Granic (PRG), WFS GUGiK.** Warstwa `A05_Granice_jednostek_ewidencyjnych`; dzielnice Warszawy to jednostki o kodach `1465xx_8`. Usługa deklaruje brak opłat. Współrzędne przychodzą w kolejności północ–wschód i są zamieniane przy imporcie.

**Tory i jezdnie: BDOT10k, paczka GML powiatu 1465.** `https://opendata.geoportal.gov.pl/bdot10k/schemat2021/14/1465_GML.zip` (ok. 90 MB). Import czyta z archiwum tylko dwa pliki przez zapytania o zakres bajtów:
- `OT_SKTR_L` — tory; brane są tylko obiekty `rodzajPojazduSzynowego = kolej` (bez tramwaju i metra), z położeniem względem gruntu, stanem (eksploatowany/nieczynny), funkcją toru i numerem linii, jeśli jest podany;
- `OT_SKJZ_L` — jezdnie; zapisywane są tylko odcinki w pobliżu przejazdów (do ok. 100 m), z klasą drogi, kategorią zarządzania, nazwą ulicy i położeniem.

**Reguła weryfikacji przejazdu (zastępuje kontrolę w OSM jako podstawową).** Obiekt z rejestru UTK leżący w granicach dzielnic dostaje status `verified`, gdy do 15 m jest tor kolejowy na poziomie gruntu, a dla kategorii innych niż E także jezdnia na poziomie gruntu do 30 m. Gdy najbliższy tor lub jezdnia leży poza poziomem gruntu, obiekt dostaje flagę `grade_separation_suspected` i zostaje do ręcznego przeglądu. Import tylko podnosi status `unverified` → `verified`. Kontrola w OSM pozostaje dodatkowym potwierdzeniem i źródłem tagów urządzeń.

**Reguła dzielnicy.** Punkt w poligonie; punkt dokładnie na granicy trafia do dzielnicy o niższym kodzie TERYT; obiekty bliżej niż 10 m od granicy mają flagę `near_district_boundary`. Obiekty poza granicami dzielnic zostają w ewidencji bez dzielnicy (flaga `outside_warsaw`) i nie wchodzą do analiz.

**Powiązania przejazd ↔ odcinek** zapisywane są jako `proximity_candidate` z pewnością malejącą z odległością — to kandydaci z geometrii, nie potwierdzona topologia.

**Sprawdzenie metody.** Dla sześciu przejazdów z rejestru UTK położenie odczytane z symbolu WMS leżało 0–3 m od osi toru w BDOT10k.

Uruchomienie (po `import-crossings`): `docker compose run --rm worker python -m app.worker import-topology` → `reports/DATA_AUDIT_topology.md`.

## Planowy ruch pociągów — ustalenia RSA-006/009 (2026-11-12)
**Źródło: Polish Trains GTFS** (`https://mkuran.pl/gtfs/polish_trains.zip`, ok. 26 MB, aktualizowany codziennie). Zbiór opracowany przez M. Kuranowskiego na podstawie otwartych danych PKP PLK i Kolei Mazowieckich; nie wymaga klucza. Obejmuje pociągi pasażerskie wszystkich przewoźników, z geometrią tras (`shapes.txt`) i kalendarzem w `calendar_dates.txt`. Licencja: warunki ponownego wykorzystywania informacji sektora publicznego PLK i KM — do przeczytania i potwierdzenia (w `system.licenses` oznaczone jako niezweryfikowane).

**Drugi zbiór: WKD GTFS** (`https://mkuran.pl/gtfs/wkd.zip`, licencja CC0 według autora). Warszawska Kolej Dojazdowa nie korzysta z sieci PKP PLK i nie występuje w zbiorze ogólnopolskim; bez tego zbioru przejazdy na linii WKD miałyby błędne zero. Oba zbiory są łączone, a tydzień odniesienia musi mieścić się we wspólnym zakresie dat.

**Metoda (`gtfs-shape-2`).**
1. *Zbiór według zarządcy.* Obiekty PKP PLK są liczone tylko z rozkładu ogólnopolskiego, obiekty WKD tylko z rozkładu WKD; bocznice innych zarządców nie mają kursów pasażerskich. Rejestr UTK dzieli jedno fizyczne skrzyżowanie na osobne obiekty zarządców (np. `447 004 508` PLK i `WK 0474050` WKD przy ul. Mszczonowskiej), więc pociągów jednego zarządcy nie wolno doliczać obiektowi drugiego.
2. *Próg podstawowy.* Kurs kolejowy (`route_type = 2`) jest liczony, gdy geometria jego trasy przebiega do 20 m od punktu przejazdu.
3. *Próg rozszerzony 50 m* stosuje się (a) dla obiektów WKD — to jedna linia, a położenie obiektu bywa wspólne z sąsiednim obiektem PLK — oraz (b) dla obiektów PLK, których punkt leży na torach innej linii niż wynika z numeru przejazdu i które przy 20 m nie mają żadnego kursu (np. `007 012 635` leży na torach linii 506, a pociągi linii 7 jadą 27 m obok). Każde takie rozszerzenie ma flagę `train_count_extended`.
4. *Wynik:* liczba kursów na każdy dzień tygodnia odniesienia (najbliższy pełny tydzień pon.–niedz. we wspólnym zakresie zbiorów), zapisana w `rail.crossing_flow` jako `evidence_type = planned`, jednostka `passenger_trains/day`.

**Kontrola wrażliwości.** Jeśli do 50 m przebiega ponad 10% więcej kursów niż przyjęto, obiekt dostaje flagę `train_count_sensitive` (możliwa linia równoległa); raport pokazuje liczby dla progów 10/20/50 m.

**Przebiegi z 2026-11-12 (metoda `gtfs-shape-1`).** 62 przejazdy w Warszawie, 38 z kursami pasażerskimi. Ujawniły trzy wady metody, poprawione w `gtfs-shape-2`: przejazdy WKD bez rozkładu WKD miały zero; `WK 0474050` miał zero, bo trasa WKD biegnie 20–50 m od wspólnego punktu z obiektem PLK; `007 012 635` miał zero przy trasie odległej o 27 m.

**Sprawdzenie metody.** Dla ośmiu przejazdów z rejestru UTK trasy z GTFS przebiegały 2–8 m od punktu przejazdu, a liczba kursów była identyczna dla progów 10–50 m. Przejazdy na liniach bez ruchu pasażerskiego (linia 503, bocznice) miały zero tras w promieniu 200 m.

**Ograniczenia.** Tylko pociągi pasażerskie: ruch towarowy, służbowy i manewry nie są ujęte, więc `0` oznacza brak kursów pasażerskich, a nie brak ruchu na torze. To plan, nie wykonanie — odwołania i opóźnienia wymagają klucza do API PKP PLK (wniosek złożony 2026-11-11). Kursy liczone są według dnia kursowania z rozkładu.

**API PKP PLK (po uzyskaniu klucza).** Dokumentacja: `https://pdp-api.plk-sa.pl/api-documentation`. Rozkład `/api/v1/schedules`, wykonanie `/api/v1/operations` (z `withPlanned` i przyrostowym `since`), słownik stacji ze współrzędnymi, nagłówek `X-API-Key`, limity Basic 100/h, Standard 500/h, Premium 2000/h.

Uruchomienie (po `import-topology`): `docker compose run --rm worker python -m app.worker import-schedule` → `reports/DATA_AUDIT_trains.md`.

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
