# Metodyka analizy RailSafe AI (v1.0, szkic do walidacji)

## 1. Dwie niezależne miary
A. **Ekspozycja na ruch**: liczba przejazdów pociągów przez konkretny przejazd w jednostce czasu oraz liczba pojazdów drogowych w zgodnym przedziale. Wskaźniki przechowywane osobno z jednostkami i niepewnością.
B. **RailSafe Priority Score (RPS)**: *autorski priorytet do dalszej kontroli*, nie prawdopodobieństwo wypadku, nie oficjalna kategoria przejazdu.

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
