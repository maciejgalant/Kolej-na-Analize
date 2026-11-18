# Asystent AI

Stan na wersję 1.0.0. Asystent działa na lokalnym modelu (Ollama, domyślnie `qwen3:4b-instruct`) i odpowiada wyłącznie na podstawie danych aplikacji. Implementacja i API: [ARCHITECTURE.md](ARCHITECTURE.md#asystent-ai).

## Zasady
- Każda liczba, pozycja i cecha przejazdu pochodzi z funkcji odczytu; model nie pisze SQL i nie ma dostępu do bazy.
- Brak danych albo błąd funkcji jest mówiony wprost; model niczego nie uzupełnia z własnej wiedzy.
- RPS to eksperymentalny priorytet do dalszej oceny, nie prognoza ani prawdopodobieństwo wypadku i nie urzędowa klasyfikacja. Asystent nie nazywa przejazdów niebezpiecznymi.
- Ruch drogowy jest opisywany jako pomiar ZDM (z ulicą i okresem) albo szacunek z klasy drogi; ruch kolejowy jako rozkład planowy.
- Pytania spoza przejazdów w Warszawie są odrzucane; tekst użytkownika nie zmienia zasad.
- Interfejs pokazuje, które dane zostały sprawdzone. Odpowiedź bez udanego odczytu (`grounded = false`) ma ostrzeżenie.

## Funkcje odczytu
| Funkcja | Zakres |
|---|---|
| `get_ranking` | ranking przejazdów drogowych według RPS, opcjonalnie w jednej dzielnicy; 1–15 pozycji, domyślnie 5 |
| `get_crossing` | szczegóły przejazdu: kategoria, dzielnica, pociągi, RPS, składniki, ostrzeżenia |
| `compare_crossings` | porównanie dwóch przejazdów |
| `get_data_quality` | kompletność RPS, modelowane składniki i źródło ruchu dla przejazdu, dzielnicy albo całej Warszawy; 1–15 pozycji |
| `list_districts` | dzielnice z liczbą przejazdów i przejść oraz najwyższą pozycją w rankingu |
| `get_method` | wzór RPS, składniki, wagi, okres danych i ograniczenia |

Nazwy dzielnic można podawać w dowolnej odmianie („na Woli”, „Targówka”). Wszystkie funkcje czytają ostatni zakończony przebieg analizy.

## Co potrafi
**Ranking.** „Pokaż przejazdy o najwyższym priorytecie na Woli”. Odpowiedź to krótka lista pięciu pozycji (pozycja, numer, dzielnica, kategoria, RPS) z pytaniem o szczegóły. Tekst listy składa backend z wyniku funkcji, więc liczby nie zależą od modelu.

**Szczegóły i kontekst rozmowy.** Prośba „pokaż szczegóły”, „wyjaśnij”, „tak, poproszę” dotyczy przejazdów z ostatniej analizy w tej rozmowie albo dołączonego przejazdu. Backend odczytuje je ponownie i sam składa odpowiedź, bez modelu; wcześniejszy tekst odpowiedzi nie jest źródłem danych. Podanie innego numeru w pytaniu kieruje je do modelu.

**Porównanie dwóch przejazdów.** Przycisk „Porównaj przejazdy” albo pytanie z dwoma numerami. Aplikacja liczy różnicę RPS jako A minus B, różnice i wkłady składników z normalizacją po dostępnych wagach oraz pokazuje kompletność i źródło ruchu obu obiektów. Gdy jeden przejazd jest poza rankingiem, różnica RPS nie jest podawana. Ten sam obiekt dwa razy albo niejednoznaczny numer daje prośbę o doprecyzowanie.

**Jakość danych.** „Które przejazdy w Wawrze mają niepełne dane?”, „Co jest pomiarem, a co szacunkiem dla tego przejazdu?”. Lista zaczyna się od przejazdów bez analizy lub z najniższą kompletnością. Kategoria E (przejścia dla pieszych) nie podlega rankingowi i nie trafia na tę listę, ale konkretny numer można sprawdzić. Kompletność oznacza dostępność składników RPS, a nie pewność, aktualność ani poziom bezpieczeństwa.

**Rekomendacje do audytu.** Prośba o rekomendacje dla dołączonego przejazdu albo ostatniej analizy daje propozycje rzeczy do sprawdzenia podczas audytu, powiązane z dostępnymi danymi. Odpowiedź składa backend z danych. Propozycje nie potwierdzają usterek i nie zastępują decyzji zarządcy.

**Prostsze wyjaśnienie.** „Wyjaśnij prościej” prowadzi do ponownego odczytu danych lub opisu metody i krótkiej odpowiedzi bez żargonu.

**Krótka rozmowa.** Powitania, podziękowania, pożegnania, „Co potrafisz?” i „Jak się masz?” dostają odpowiedź bez wywołania modelu i bez danych. Dopasowanie obejmuje całą wiadomość, więc „Cześć, pokaż ranking” trafia do modelu.

**Asystent na mapie.** Na mapie można zapytać o wybrany przejazd w osobnej, tymczasowej rozmowie ([FRONTEND_DESIGN.md](FRONTEND_DESIGN.md#okno-mapy)).

## Ograniczenia
- Mały model (4 mld parametrów) może źle dobrać funkcję albo niedokładnie streścić wynik; liczby w kartach i tabelach pochodzą zawsze z danych.
- Bez karty graficznej odpowiedź trwa minuty; limit czasu to 240 s. Kartę NVIDIA włącza `docker-compose.gpu.yml`.
- Gdy model jest niedostępny, analityczne pytania nie działają; mapa, karty i ranking działają dalej.
- Nie ma symulacji inwestycji, analizy otoczenia szkół ani prognoz godzinowych: wymagałyby osobnych danych i walidacji.
