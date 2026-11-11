# RailSafe AI — specyfikacja projektu (v1.0)
Data: 2026-11-11. Status: projekt; decyzje techniczne do weryfikacji w spike'ach danych.

## 1. Cel i problem
Aplikacja identyfikuje przejazdy kolejowo-drogowe na terenie m.st. Warszawy wymagające **dalszej oceny bezpieczeństwa** na podstawie ekspozycji na ruch kolejowy i drogowy oraz dostępnych informacji o infrastrukturze. Nie prognozuje bez walidacji prawdopodobieństwa wypadku. Nie stanowi urzędowej klasyfikacji przejazdów.

## 2. Użytkownicy i przypadki użycia
- Analityk: wybiera dzielnicę, okres, rodzaj danych i przegląda ranking oraz mapę.
- Badacz: wyświetla składniki wskaźnika, pochodzenie i kompletność danych, porównuje okresy.
- Jury konkursowe: uruchamia demonstrację w localhost i wykonuje przygotowany scenariusz.
- Użytkownik AI: pyta „Pokaż przejazdy o najwyższym priorytecie na Woli”, „Porównaj Wolę z Bemowem” lub „Wyjaśnij wynik tego przejazdu”.

## 3. Zakres MVP
1. Docker Compose: frontend, backend, PostGIS, Ollama i zadania importu.
2. 18 dzielnic Warszawy; ewidencja przejazdów ze statusem weryfikacji, bez mylenia skrzyżowań bezkolizyjnych z przejazdami.
3. Import rozkładowych i, gdy możliwe, wykonanych kursów pasażerskich; status danych i czas odświeżenia.
4. Import pomiarów drogowych (publicznych); adapter ruchu live wyłącznie przy zgodnej licencji.
5. Powiązanie danych ruchu z konkretnym przejazdem, identyfikowalne metody dopasowania i poziom pewności.
6. Ranking priorytetu do dalszej oceny, mapa, karta przejazdu, wykresy i filtry.
7. AI wywołuje *dozwolone funkcje*, nie generuje i nie uruchamia dowolnego SQL; odpowiedzi tylko z wyników backendu.
8. Zapis wyników autorskich analiz i dozwolonych metadanych; retencja danych zewnętrznych zgodna z umową.

## 4. Poza MVP
Predykcja wypadków, pełna historia ruchu live, wszystkie pociągi towarowe, komercyjny routing, automatyczna klasyfikacja prawna, oficjalne zalecenia modernizacji, analiza sygnału CCTV.

## 5. Wymagania niefunkcjonalne
- Usługi HTTP i baza na 127.0.0.1; kontenery w prywatnej sieci; klucze tylko w .env/secrets; bez commitowania sekretów.
- Samodzielne uruchomienie demonstracyjne przy wyłączonych dostawcach API z jawnie oznaczonymi danymi demonstracyjnymi.
- Wyniki deterministyczne i wersjonowane: data, okres, algorytm, wersja wsadu, jednostka, źródło.
- Mapy i API odrzucają niefiltrowane operacje masowe, zabezpieczają parametry i wykluczają SQL z LLM.
- Brak danych ≠ zero ruchu i brak zagrożenia; informacja o pokryciu obowiązkowa.
- Przyjazność klawiaturze, kontrast, odpowiedni układ na ekranie laptopa.

## 6. Kryteria akceptacji MVP
- `docker compose up -d --build` uruchamia pełne demo; healthchecki działają.
- Dane mają geometrię w EPSG:2180, unikalne identyfikatory i kontrolę duplikatów.
- Filtrowanie Woli zwraca tylko zweryfikowane obiekty w obrębie dzielnicy; rekordy na granicy mają jednoznaczną regułę przypisania.
- Każdy wynik rankingu zawiera źródło, datę, wersję algorytmu i status jakości.
- AI odpowiada na ranking, filtr, porównanie, wyjaśnienie i wybrane okresy; potrafi przyznać brak danych.
- Brak dostępu do komercyjnego API nie blokuje mapy ani zestawu demonstracyjnego.

## 7. Ryzyka i punkty decyzyjne
- Niezweryfikowana kompletność rejestru przejazdów i kategorii w Warszawie.
- Rozkład/realizacja pasażerska nie reprezentuje całego ruchu (zwłaszcza towarowego).
- Przypisanie publicznego licznika drogowego do przejazdu wymaga walidacji odcinka; sama bliskość geometryczna nie wystarcza.
- API prędkości nie jest licznikiem pojazdów na godzinę.
- Prawa do cache'owania i pochodnych analiz Traffic API trzeba potwierdzić dla konkretnych usług i planu.
- Termin konkursu: zweryfikować aktualne wymagania, załączniki i terminy przed zgłoszeniem.

## 8. Wykorzystane projekty
GeoGraph Demo 3: wzorce Docker/PostGIS/FastAPI/Ollama i katalogu analiz. PSIP MG L1: wzorce importu BDOT10k i analiz przestrzennych. Nowe repo nie narusza źródłowych projektów.
