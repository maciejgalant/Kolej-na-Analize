# Frontend Kolej na Analizę

Stan na wersję 1.0.0. Interfejs to aplikacja rozmów z asystentem; mapa i karty przejazdów są otwierane z rozmowy.

## Układ i stylistyka
- Po lewej zwijany granatowy panel historii z przyciskiem „Mapa przejazdów”; gdy panel jest zwinięty, przycisk mapy zostaje w nagłówku. Po prawej aktywna rozmowa z polem pytania przy dolnej krawędzi.
- Kolory: granat `#102b4e`, pomarańcz `#d9570b`, biel ([BRANDING.md](BRANDING.md)). Oznaczenie danych demonstracyjnych jest bursztynowe i widoczne w aplikacji oraz w oknie mapy.
- Układ dla komputera od 820 px szerokości; osobnego układu na telefon nie ma.
- Asystenta oznacza piktogram postaci ze słuchawką i podpis „Asystent AI”. Podczas oczekiwania na model i ładowania mapy pulsują światła sygnalizacji przejazdu; to nie jest procentowy postęp.
- Przejścia trwają 180 ms; `prefers-reduced-motion` wyłącza animacje, także okna mapy i przycisków.
- Przyciski z ikonami mają nazwy dostępności i podpowiedzi.

## Historia i gałęzie rozmów
- Nowa rozmowa, automatyczny tytuł z pierwszego pytania, zmiana nazwy, wyszukiwanie po tytułach i treści, przypinanie i usuwanie z potwierdzeniem. Lista jest pogrupowana: przypięte, dzisiaj, wczoraj, starsze.
- Zapis tylko w `localStorage`, klucz `railsafe.chat.v1`. Nie ma kont ani zapisu na serwerze; wyczyszczenie danych witryny usuwa historię.
- Wiadomości tworzą drzewo (`id`, `parent`), `leaf` wskazuje aktywną gałąź. Edycja pytania i ponowienie odpowiedzi tworzą alternatywy; poprzednie wersje i ich dalszy ciąg zostają. Przełącznik wersji otwiera wybraną alternatywę.
- Do modelu trafia tylko historia aktywnej gałęzi, najwyżej 8 wiadomości, oraz identyfikatory przejazdów z ostatniej analizy w tej gałęzi. Prośba o szczegóły odczytuje ponownie te same przejazdy; jawnie dołączony przejazd ma pierwszeństwo.
- Szkic pytania, dołączony przejazd i stan mapy są zapisywane osobno dla każdej rozmowy.
- Uszkodzona lub nieznana historia nie jest nadpisywana: użytkownik widzi komunikat, a sesja działa bez zapisu. Błąd zapisu (np. brak miejsca) też jest sygnalizowany.

## Rozmowa z modelem
- Enter wysyła, Shift+Enter dodaje wiersz. Kopiowanie wiadomości (z potwierdzeniem „Skopiowano”), edycja, ponowienie, licznik czasu oczekiwania i przycisk zatrzymania.
- Jedna rozmowa ma najwyżej jedno aktywne żądanie; wynik trafia do swojej rozmowy i wiadomości także po przełączeniu wątku.
- Zatrzymanie przerywa oczekiwanie i ignoruje spóźniony wynik; interfejs mówi wprost, że model mógł jeszcze liczyć. Po odświeżeniu strony niedokończona wiadomość ma status przerwanej i można ją ponowić. Odpowiedzi nie są strumieniowane.
- Nowy wątek pokazuje powitanie, przykładowe pytania i przycisk mapy. Pod ostatnią odpowiedzią są propozycje dalszych pytań. „Porównaj przejazdy” otwiera wybór dwóch obiektów z ewidencji i wysyła pytanie z ich numerami.

## Wyniki w odpowiedzi
Odpowiedź to tekst i opcjonalny obiekt `evidence`, budowany przez backend z wyników funkcji odczytu. Interfejs nie wyciąga liczb ani identyfikatorów z tekstu modelu.

- Pierwszy akapit odpowiedzi jest wyróżniony. Ranking domyślnie pokazuje pięć pozycji.
- Karty przejazdów pokazują RPS jako priorytet do dalszej oceny, pozycję w rankingu i ruch pasażerski; kliknięcie otwiera szczegóły w oknie mapy.
- Tabele: ranking, porównanie, liczby przejazdów w dzielnicach.
- Wykresy: planowy ruch pasażerski, składniki RPS, natężenie drogowe, dzień roboczy/sobota/niedziela. Brak wartości to „Brak danych”, nie zero; wartości modelowane są opisane i kreskowane. Każdy wykres ma opis dla czytnika ekranu i rozwijaną tabelę wartości.
- Karty, wykresy, źródła, okresy i ograniczenia są w sekcjach rozwijanych; przycisk „Pokaż na mapie” jest widoczny od razu.
- Tekst modelu jest wyświetlany przez React bez surowego HTML; obsługiwane są akapity, nowe wiersze i pogrubienie.
- Eksportu CSV/PNG oraz importu i eksportu historii nie ma; wystarcza kopiowanie.

## Okno mapy
- Natywny `dialog`: modalność, Escape, ograniczenie fokusu, animacja otwarcia i zamknięcia. Ręczne otwarcie przywraca widok, podkład i filtry zapisane w rozmowie.
- „Pokaż na mapie” nie otwiera mapy samoczynnie. Pokazuje tylko obiekty z danej odpowiedzi, dopasowuje do nich widok i zeruje filtry; „Pokaż wszystkie przejazdy” zdejmuje to ograniczenie. Numer etykiety odpowiada kolejności w odpowiedzi.
- Filtry: dzielnica i kategoria A–F. Podkłady: kolorowy (domyślny), szary i ortofotomapa. Piktogramy kategorii i legenda.
- Kliknięcie punktu otwiera kartę przejazdu w bocznej części okna: wskaźnik RPS, kompletność składników, miniwykresy składników, ruch kolejowy i drogowy, rozkład w ciągu doby oraz historia zdarzeń SEWiK przy wykresach RPS. Wagi, źródła i szczegóły techniczne są rozwijane.
- „Zapytaj o ten przejazd” zamyka mapę, dołącza usuwalną etykietę przejazdu do pola pytania i ustawia fokus, bez wysyłania.
- Asystent na mapie: kliknięcie przejazdu pokazuje propozycję pomocy, bez zapytania do modelu. Po otwarciu panelu pytania idą przez to samo API z `crossing_id`. Ta rozmowa jest tylko w pamięci: zamknięcie mapy albo wybór innego przejazdu ją usuwa i przerywa żądanie; zwinięcie panelu ją zachowuje.
- Gdy obiekt ze starszej odpowiedzi nie jest już w ewidencji, pojawia się informacja o brakujących obiektach.
- Przy niedostępnym modelu mapa i karty działają; stany braku danych, błędu i ponowienia są widoczne.

## Kod
| Plik | Rola |
|---|---|
| `App.tsx` | połączenie widoków, stan usług, pobieranie ewidencji |
| `Assistant.tsx` | rozmowa, edycja, wersje, pole pytania |
| `chat/model.ts`, `chat/useConversations.ts` | drzewo wiadomości, walidacja, zapis, żądania |
| `chat/ConversationList.tsx`, `chat/AnswerContent.tsx`, `chat/AnalysisShortcuts.tsx` | historia, wyniki odpowiedzi, porównanie przejazdów |
| `MapExplorer.tsx`, `MapView.tsx`, `MapAssistant.tsx` | okno mapy, warstwy Leaflet, asystent na mapie |
| `CrossingCard.tsx`, `PriorityChart.tsx`, `IncidentHistory.tsx` | karta przejazdu, składniki RPS, historia SEWiK |
| `Dialog.tsx`, `IconButton.tsx`, `UiIcons.tsx`, `CategoryPin.tsx`, `pictograms.ts` | wspólne elementy i ikony |
| `api.ts`, `basemaps.ts`, `labels.ts`, `brand.ts` | typy i wywołania API, podkłady, etykiety, nazwa i logo |
| `styles.css`, `chat.css`, `presentation.css` | style bazowe i mapy, rozmowy, kart i wykresów |

## Testy
- `npm test`: logika i trwałość historii.
- `npm run build`: typy i kompilacja.
- `npm run test:e2e`: scenariusze Playwright z kontrolowanym API i fikcyjnymi danymi (bez prawdziwego modelu i serwerów podkładów). Pierwsze uruchomienie: `npx playwright install chromium`; opcjonalnie `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` wskazuje istniejącą przeglądarkę. Testy działają też w CI.
