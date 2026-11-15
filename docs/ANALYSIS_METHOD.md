# Metodyka analizy Kolej na Analizę (v1.0, szkic do walidacji)

## 1. Dwie niezależne miary
A. **Ekspozycja na ruch**: liczba przejazdów pociągów przez konkretny przejazd w jednostce czasu oraz liczba pojazdów drogowych w zgodnym przedziale. Wskaźniki przechowywane osobno z jednostkami i niepewnością.
B. **Wskaźnik priorytetu do dalszej oceny (RPS)**: *autorski priorytet do dalszej kontroli*, nie prawdopodobieństwo wypadku, nie oficjalna kategoria przejazdu.

## 2. Iloczyn ruchu
Jeżeli dane i przedział spełniają wymogi odpowiedniej metodyki prawnej, można wyliczyć iloczyn ruchu zgodnie z aktualnym rozporządzeniem. Dla danych innych niż wymagane pomiarowo stosować wyłącznie etykietę **szacunkowy wskaźnik ekspozycji**, bez sugerowania urzędowej klasyfikacji. Zweryfikować aktualny tekst i wzory rozporządzenia przed implementacją.

## 3. Wersja robocza RPS
Grupy: T = ekspozycja na ruch; P = infrastruktura / zabezpieczenia; G = geometria / widoczność; H = historia zdarzeń. Po udokumentowanej normalizacji do [0,100], wynik przykładowy:
`RPS = 0.40*T + 0.30*P + 0.20*G + 0.10*H`.
**Wagi eksperymentalne, niezwalidowane.** Nie przyjmować ich jako normatywnych ani naukowo potwierdzonych. Wyższy wynik oznacza wyższy priorytet w przyjętej metodzie, a nie ilościowe ryzyko wypadku.

## 4. Braki danych
- `NULL` i jawny status `unknown` zamiast 0.
- Gdy brak kluczowej miary, nie nadawać pełnego rankingu RPS; można pokazać ranking częściowy z odrębną etykietą i kolumną kompletności.
- Nie przeskalowywać wag automatycznie bez informacji, bo rankingi z różnych zestawów cech byłyby nieporównywalne.
- Osobna analiza granic możliwych wyników przy brakach, jeśli potrzebna.

## 5. Powiązanie przejazd ↔ strumień ruchu
- Geometria: weryfikacja przecięcia jednopoziomowego; relacja M:N do odcinków.
- Kolej: przypisanie kursu tylko jeśli wiarygodnie znany przebieg przez odcinek i czas; deduplikacja (kurs, przejazd, okres); wyraźne rozróżnienie planu i wykonania.
- Droga: licznik do odcinka po topologii i kierunku; oddzielić dane bezpośrednie od modelowych.
- Okresy porównawcze muszą być zgodne i obejmować tę samą definicję dnia, godziny oraz czasu lokalnego (Europe/Warsaw, DST).

## 6. Testy metody
- Test podwójnego naliczania kursów oraz zerowych danych i NULL.
- Test stabilności rankingu na ±10/20% zmianie wag i zakłóceniach pomiaru.
- Test, czy wyniki skrajne wynikają z danych, a nie liczby brakujących pól.
- Test jakości map matchingu na ręcznie zweryfikowanej próbce.
- Ekspertowa interpretacja przejazdów o najwyższym i najniższym priorytecie.
- Porównanie z historią zdarzeń tylko przy zgodnej lokalizacji i okresie; bez wniosków o przyczynowości.

## 7. Przykładowa interpretacja dla użytkownika
„Przejazd X ma wysoki *priorytet do dalszej oceny* z powodu wysokiego oszacowanego ruchu pociągów i kategorii zabezpieczeń. Dane o ruchu samochodowym są modelowe, a brak zweryfikowanej widoczności ogranicza pewność porównania. To nie jest prognoza liczby wypadków”.

## 8. Implementacja `rps-0.5-exp` (RSA-010, 2026-11-12; pomiary ZDM od 2026-11-13)
Wersja eksperymentalna; wagi i tabele punktowe są założeniami autorskimi, niezwalidowanymi. Kod: `backend/app/analysis/rps.py`.

**Zakres.** Zweryfikowane przejazdy drogowe (kategorie A–D i F) w granicach Warszawy. Przejścia dla pieszych (kategoria E) są w ewidencji i na mapie, ale poza rankingiem.

**Składniki (0–100).**
- **T — ekspozycja:** `100 · log10(1 + pociągi × pojazdy) / log10(1 + 12 000 000)`, obcięte do 100. Pociągi: średnia planowa liczba kursów pasażerskich w dzień roboczy (`rail.crossing_flow`). Pojazdy: średnia dobowa z pomiaru ZDM (APR, dni miarodajne), gdy punkt pomiarowy leży na ulicy przejazdu do 300 m od niego (`rps-0.5-exp`; dopasowanie opisane w DATA_SOURCES.md, metoda `zdm-street-1`) — wtedy status `ok`, a szczegóły zawierają punkt, ulicę, odległość, okres i dla porównania szacunek z modelu. W pozostałych przypadkach szacunek z klasy drogi BDOT10k (tabela niżej), status `modelled`. Poziom odniesienia 12 mln = 400 pociągów × 30 000 pojazdów.
- **P — zabezpieczenia:** z kategorii przejazdu: A 15, B 30, C 55, D 100, F 60. Status `ok`.
- **G — geometria:** `0,6 · tory + 0,4 · kąt`. Tory liczone na 30-metrowym przekroju prostopadłym do najbliższego toru (1 → 0, 2 → 40, 3 → 70, ≥4 → 100). Kąt ostry między osią jezdni a torem: ≥75° → 0, ≤30° → 100, liniowo pomiędzy. Status `modelled`; widoczność nie jest oceniana.
- **H — historia zdarzeń:** brak danych, `unknown` dla wszystkich obiektów.

**Szacunek ruchu drogowego z klasy drogi [pojazdy/dobę]:** wewnętrzna 300, dojazdowa 800, lokalna 2 500, zbiorcza 8 000, główna 18 000, główna ruchu przyśpieszonego 30 000. Brana jest jezdnia o najwyższej klasie do 15 m od punktu przejazdu. Jeżeli w 15 m nie ma żadnej jezdni (szeroki przejazd, punkt w osi torowiska), brana jest najbliższa do 30 m, ale tylko taka, która przecina tor przy przejeździe — ulica biegnąca równolegle do torów nie jest ulicą przejazdu. Kąt skrzyżowania nie jest wtedy wyznaczany, a szczegóły składnika T zawierają odległość i adnotację. Przejazd kategorii F bez jezdni w danych dostaje klasę „droga wewnętrzna”, bo ta kategoria z definicji dotyczy dróg wewnętrznych. W pozostałych przypadkach brak jezdni oznacza brak pozycji (od wersji `rps-0.4-exp`; wersja 0.3 brała dowolną jezdnię do 30 m i na danych rzeczywistych przypisała dwóm przejazdom równoległą drogę główną). To założenie zastępcze dla przejazdów bez pomiaru: system ZDM (APR, 128 punktów) ma punkt na tej samej ulicy do 1,5 km tylko dla trzech obiektów (Radzymińska 75 m, Wydawnicza 1,0 km, Łodygowa 1,2 km). Pierwszy pomiar (Radzymińska, droga zbiorcza: ok. 35 000 pojazdów/dobę wobec 8 000 w modelu) pokazuje, że tabela może zaniżać natężenie na ulicach o dużym ruchu; porównanie dla wszystkich dopasowanych punktów jest w `reports/DATA_AUDIT_road.md`. Kilka punktów nie wystarcza do nowej kalibracji, więc tabela pozostaje bez zmian i nadal wymaga weryfikacji.

**Wynik i braki.**
- `RPS` to średnia ważona po dostępnych składnikach; `completeness_pct` to suma wag dostępnych składników (90% = brak tylko H).
- Bez T lub P obiekt nie dostaje wyniku ani pozycji (`rps = NULL`, `quality_status = partial`). T jest nieznane, gdy rozkład nie ma kursów pasażerskich — ruch towarowy i manewrowy jest wtedy nieznany, a nie zerowy.
- Skoro H brakuje wszystkim, wyniki są między sobą porównywalne, ale cały ranking ma status częściowego.

**Analiza wrażliwości.** Każda waga jest osobno zmieniana o ±20% (z normalizacją pozostałych); `rank_best` i `rank_worst` to skrajne pozycje w tych ośmiu wariantach.

**Każdy przebieg** zapisuje wersję metody, wagi, tabele, okres danych i liczbę obiektów w `analysis.runs`; API i interfejs pokazują ostatni zakończony przebieg.

**Czego ta wersja nie robi:** nie liczy urzędowego iloczynu ruchu, nie używa wykonania kursów ani danych o zdarzeniach, nie ocenia widoczności. Pomiary drogowe ZDM wchodzą tylko dla przejazdów z punktem na tej samej ulicy do 300 m; profil godzinowy jest zapisywany, ale jeszcze nie wpływa na wynik.

