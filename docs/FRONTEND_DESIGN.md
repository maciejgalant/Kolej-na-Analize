# Frontend RailSafe AI — aplikacja rozmów (v2, 2026-11-15)

## Układ i stylistyka
Głównym ekranem jest rozmowa. Po lewej znajduje się zwijany panel historii, a po prawej aktywny wątek. Mapa nie jest tłem aplikacji: użytkownik otwiera ją w dużym oknie modalnym nad rozmową. Projekt obejmuje obecnie komputer, od szerokości 820 px; osobny układ telefonu pozostaje poza tym etapem.

Granat `#102b4e`, biel i pomarańcz `#d9570b`, jasne obrysy i czytelna typografia. Pytania użytkownika znajdują się w dymkach po prawej, a odpowiedzi asystenta zajmują kolumnę wiadomości. Pole pytania jest przy dolnej krawędzi obszaru rozmowy. Nowy wątek pokazuje powitanie, trzy przykładowe pytania i przycisk „Otwórz mapę”. Aplikacja zachowuje oznaczenie niezależnego projektu edukacyjnego.

## Historia i gałęzie
- Nowa rozmowa, automatyczny tytuł z pierwszego pytania, ręczna zmiana nazwy, wyszukiwanie po tytułach i wiadomościach, przypinanie oraz usuwanie po potwierdzeniu.
- Historia jest zapisywana tylko w `localStorage`, pod kluczem `railsafe.chat.v1`. Nie ma kont ani zapisu rozmów po stronie serwera. Wyczyszczenie danych witryny usuwa historię.
- Wiadomości tworzą drzewo (`id`, `parent`), a `leaf` wskazuje aktywną gałąź. Edycja pytania dodaje alternatywę z tym samym rodzicem. Ponowienie odpowiedzi dodaje alternatywną odpowiedź pod tym samym pytaniem. Poprzednie wiadomości i ich dalszy ciąg zostają zachowane.
- Przełącznik wersji przy wiadomości otwiera wybraną alternatywę i jej najnowszą kontynuację. Do modelu trafia wyłącznie historia aktywnej gałęzi, ograniczona do ośmiu wiadomości zgodnie z API.
- Szkic pytania, dołączony przejazd i stan mapy są zapisywane osobno dla każdej rozmowy.
- Uszkodzony lub nieznany format historii nie jest nadpisywany. Użytkownik widzi komunikat, a bieżąca sesja działa bez zapisu. Błąd zapisu, np. przekroczenie pojemności przeglądarki, również jest sygnalizowany.

## Rozmowa z modelem
Kopiowanie odpowiedzi, edycja pytania, ponowienie, informacja o oczekiwaniu z licznikiem oraz przycisk zatrzymania. Enter wysyła wiadomość, Shift+Enter dodaje wiersz. Błąd odpowiedzi można ponowić. Jedna rozmowa może mieć jedno aktywne żądanie; inne rozmowy działają niezależnie. Wynik jest przypisywany do identyfikatora rozmowy i wiadomości, także po przełączeniu wątku.

Zatrzymanie anuluje żądanie klienta i ignoruje późniejszy wynik. Synchroniczny backend/Ollama może jeszcze kończyć inferencję — interfejs mówi wprost o przerwaniu oczekiwania. Po odświeżeniu niedokończona wiadomość otrzymuje status przerwanej i może zostać ponowiona. Nie wprowadzono strumieniowania odpowiedzi.

## Karty, tabele, wykresy i źródła
Odpowiedź zawiera tekst oraz opcjonalny, walidowany obiekt `evidence`, budowany przez backend z wyników bezpiecznych funkcji. Interfejs nie wyciąga identyfikatorów ani liczb z tekstu modelu.

- Klikalne karty przejazdów otwierają szczegóły w oknie mapy.
- Tabele pokazują odczytane przejazdy, ranking/porównanie lub liczby przejazdów w dzielnicach.
- Wykresy pokazują planowy ruch pasażerski, a przy pytaniu o konkretny przejazd również składniki RPS, dostępne natężenie drogowe i rozkład dzień roboczy/sobota/niedziela.
- Brak wartości to „Brak danych”, a nie zero. Dane planowe, pomiary i wartości modelowane mają opisy; wartości modelowane dodatkowo kreskowanie. Wykres ma opis dla czytnika ekranu i rozwijaną tabelę wartości.
- Źródła, okresy, wyjaśnienia, kompletność i ograniczenia znajdują się w rozwijanej sekcji. RPS nie jest przedstawiany jako prawdopodobieństwo wypadku.
- Tekst modelu jest escapowany przez React; obsługiwane są akapity, nowe wiersze i pogrubienie. Surowy HTML nie jest renderowany.

Na tym etapie wystarcza kopiowanie tekstu: brak eksportów CSV/PNG i importu/eksportu historii.

## Okno mapy
- Ręczne otwarcie przywraca centrum, przybliżenie, podkład, dzielnicę i kategorię zapisane w tej rozmowie.
- „Pokaż na mapie” jest propozycją działania. Mapa nie otwiera się automatycznie. Przycisk pokazuje tylko obiekty odczytane dla konkretnej odpowiedzi i dopasowuje do nich widok. Resetuje filtry dzielnicy i kategorii, aby nie ukryły tych obiektów.
- W takim widoku przycisk „Pokaż wszystkie przejazdy” usuwa ograniczenie do obiektów odpowiedzi; pozostałe filtry nadal działają.
- Filtry: dzielnica i kategoria A–F. Podkłady: szary, kolorowy i ortofotomapa. Zachowane są piktogramy kategorii, legenda i informacje o jakości.
- Kliknięcie punktu otwiera szczegóły w bocznej części tego samego okna.
- „Zapytaj o ten przejazd” zamyka mapę, dołącza usuwalną etykietę przejazdu do pola pytania i ustawia fokus. Nie wysyła pytania samoczynnie.
- Mapa wykorzystuje aktualną ewidencję. Gdy obiekt ze starszej odpowiedzi nie jest już dostępny, pojawia się informacja o brakujących obiektach.
- Natywny `dialog` zapewnia modalność, obsługę Escape i ograniczenie fokusu. Po zmianie rozmiaru Leaflet przelicza kontener.

Pasek danych demonstracyjnych jest widoczny w aplikacji i w oknie mapy. Przy niedostępnym modelu można nadal korzystać z mapy i kart przejazdów. Stany braku danych, błędu pobierania i ponowienia są widoczne.

## Podział kodu i sprawdzanie
- `App.tsx`: połączenie widoków, stan usług i pobieranie ewidencji.
- `Assistant.tsx`: rozmowa, edycja, wersje i pole pytania.
- `chat/model.ts`, `chat/useConversations.ts`: drzewo, walidacja, zapis i żądania.
- `chat/ConversationList.tsx`, `chat/AnswerContent.tsx`: historia i wyniki.
- `MapExplorer.tsx`, `MapView.tsx`, `CrossingCard.tsx`: mapa i szczegóły.
- `chat.css`: wygląd nowego obszaru rozmów; wspólne style mapy/kart pozostają w `styles.css`.

`npm test` sprawdza logikę i trwałość historii. `npm run build` sprawdza typy i kompilację. `npm run test:e2e` uruchamia scenariusze Playwright z kontrolowanym API i fikcyjnymi danymi; nie jest to test prawdziwego modelu ani serwerów podkładów. Przy pierwszym uruchomieniu: `npx playwright install chromium`. Opcjonalnie `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` wskazuje istniejącą przeglądarkę. Testy działają również w CI.
