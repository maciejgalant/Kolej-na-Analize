# Kolej na Analizę — specyfikacja projektu

Stan na wersję 1.0.0 (17.11.2026). Zmiany: [CHANGELOG.md](../CHANGELOG.md), zadania: [BACKLOG.md](BACKLOG.md).

## Cel i problem
Aplikacja wskazuje przejazdy kolejowo-drogowe w m.st. Warszawie, które wymagają **dalszej oceny bezpieczeństwa**. Podstawą jest ekspozycja na ruch kolejowy i drogowy oraz dostępne informacje o infrastrukturze. Aplikacja nie prognozuje prawdopodobieństwa wypadku i nie jest urzędową klasyfikacją przejazdów.

Projekt powstał na konkurs PKP PLK „Kolej na bezpieczeństwo” (II edycja).

## Użytkownicy i przypadki użycia
- **Analityk**: przegląda ranking i mapę, filtruje po dzielnicy i kategorii, otwiera kartę przejazdu.
- **Badacz**: sprawdza składniki wskaźnika, pochodzenie i kompletność danych oraz analizę wrażliwości wag.
- **Jury konkursowe**: uruchamia aplikację lokalnie na zestawie demonstracyjnym, bez internetu i kluczy API.
- **Użytkownik asystenta AI**: pyta np. „Pokaż przejazdy o najwyższym priorytecie na Woli”, „Porównaj dwa przejazdy”, „Które przejazdy w Wawrze mają niepełne dane?”.

## Zakres wersji 1.0.0
1. Lokalny stos Docker Compose: PostGIS, FastAPI, frontend, Ollama, zadania importu i analizy.
2. 18 dzielnic Warszawy; ewidencja przejazdów z warstwy UTK z kontrolą w OpenStreetMap i statusem weryfikacji; skrzyżowania bezkolizyjne odrzucone, ale zachowane w ewidencji.
3. Planowy ruch pasażerski z otwartego GTFS, także rozkład w ciągu doby. Rzeczywiste wykonanie rozkładu (API PKP PLK) jest podłączone w backendzie, ale nie zasila rankingu.
4. Publiczne pomiary ruchu drogowego ZDM (punkty APR i skrzyżowania), dopasowane do przejazdów z jawną metodą dopasowania; bez pomiaru szacunek z klasy drogi.
5. Eksperymentalny Wskaźnik Priorytetu Oceny (WPO) z rankingiem, analizą wrażliwości wag i kompletnością składników ([ANALYSIS_METHOD.md](ANALYSIS_METHOD.md)).
6. Interfejs rozmów z historią, mapą w oknie modalnym, kartą przejazdu i wykresami ([FRONTEND_DESIGN.md](FRONTEND_DESIGN.md)).
7. Asystent AI na lokalnym modelu, który wywołuje wyłącznie dozwolone funkcje odczytu i odpowiada tylko na podstawie ich wyników ([ASSISTANT_CAPABILITIES.md](ASSISTANT_CAPABILITIES.md)).
8. Częściowa historia zdarzeń SEWiK przy przejazdach, bez wpływu na WPO ([SEWIK_HISTORY.md](SEWIK_HISTORY.md)).
9. Zestaw demonstracyjny, jawnie oznaczony w interfejsie i API.

## Poza zakresem
Predykcja wypadków, ruch towarowy, ruch drogowy na żywo (zrezygnowano z TomTom na rzecz pomiarów ZDM), automatyczna klasyfikacja prawna, zalecenia modernizacji, analiza obrazu z kamer, układ na telefon, konta użytkowników i zapis rozmów na serwerze.

## Wymagania niefunkcjonalne
- Usługi HTTP i baza nasłuchują tylko na 127.0.0.1; Ollama nie ma portu na hoście. Klucze wyłącznie w `.env`, nigdy we frontendzie ani w repozytorium.
- Aplikacja działa bez dostawców zewnętrznych na zestawie demonstracyjnym.
- Wyniki są odtwarzalne: każdy przebieg analizy zapisuje okres, wersję metody, wagi, źródła i status jakości.
- Model językowy nie pisze SQL i nie ma dostępu do bazy; API waliduje parametry i ogranicza wielkość odpowiedzi.
- Brak danych nie oznacza zera ruchu ani braku zagrożenia; kompletność jest zawsze pokazana.
- Obsługa klawiaturą, kontrast, ograniczenie animacji (`prefers-reduced-motion`), układ dla laptopa od 820 px szerokości.

## Kryteria akceptacji
Sprawdzane automatycznie w CI (backend z PostGIS, frontend z Playwright, stos Compose z zestawem demo):
- `docker compose up -d --build` uruchamia aplikację, a `/api/v1/health` raportuje stan bazy, modelu i zestawu danych.
- Geometrie w EPSG:2180, unikalne identyfikatory i kontrola duplikatów wymuszane przez bazę ([DATA_CONTRACT.md](DATA_CONTRACT.md)).
- Filtr dzielnicy zwraca tylko zweryfikowane przejazdy w jej granicach; przejazd na granicy ma jednoznaczną regułę przypisania.
- Każdy wynik rankingu ma źródło, okres, wersję metody i status jakości.
- Asystent obsługuje ranking, szczegóły, porównanie, jakość danych, metodę i listę dzielnic; przyznaje brak danych i odmawia pytań spoza zakresu.
- Brak klucza API PKP PLK i niedostępność modelu nie blokują mapy ani rankingu.

## Ograniczenia i ryzyka
- Kompletność ewidencji zależy od rejestru UTK; rozbieżności z OSM są raportowane, nie poprawiane automatycznie.
- Ruch kolejowy obejmuje tylko plan pasażerski.
- Punkt pomiarowy ZDM na tej samej ulicy mają tylko 3 z 36 przejazdów drogowych; pozostałe korzystają z szacunku.
- Warunki ponownego wykorzystania części danych (GTFS, ZDM) nie są potwierdzone ([DATA_SOURCES.md](DATA_SOURCES.md)).
- Mały lokalny model (4 mld parametrów) może źle dobrać funkcję; bez karty graficznej odpowiedź trwa minuty.
