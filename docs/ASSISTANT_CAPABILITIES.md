# Rozszerzenia asystenta: porównanie, jakość danych i rozmowa

## Porównanie dwóch przejazdów

Przycisk „Porównaj przejazdy” otwiera wybór dwóch różnych obiektów z ewidencji.
Po zatwierdzeniu wysyłane jest pytanie zawierające ich numery. Można także wpisać
numery samodzielnie. Model wybiera funkcję `compare_crossings`; aplikacja oblicza
różnicę RPS A−B, różnice składników i ich wkłady z normalizacją po dostępnych wagach.
Braki pozostają brakami, a nie zerowymi ocenami. Jeśli jeden obiekt jest poza
rankingiem, nie przedstawiamy różnicy RPS jako porównania liczbowego.

Tabele i przycisk mapy pochodzą z odczytanych rekordów. Porównanie pokazuje także
kompletność i źródło ruchu drogowego obu przejazdów. Powtórzenie tego samego obiektu
lub niejednoznaczny numer powoduje błąd z prośbą o doprecyzowanie.

## Jakość danych

Funkcja `get_data_quality` przyjmuje numer przejazdu albo dzielnicę oraz limit 1–15.
Lista obejmuje zweryfikowane przejazdy drogowe i zaczyna od braku analizy albo
najniższej kompletności składników, a następnie większej liczby składników modelowanych.
Kategoria E jest wyłączona z tej listy, ponieważ z założenia nie podlega rankingowi;
można jednak sprawdzić konkretny numer przejścia.

Odpowiedź rozróżnia pomiar, model i brak ruchu drogowego w danych, wskazuje brakujące
oraz modelowane składniki. Kompletność dotyczy dostępności składników RPS, nie
statystycznej pewności, aktualności ani poziomu bezpieczeństwa. Okresy należy
sprawdzać w źródłach. Nie tworzymy nowego, arbitralnego wskaźnika „wiarygodności”.

Przykłady: „Które przejazdy w Wawrze mają niepełne dane?”, „Co jest pomiarem, a co
szacunkiem dla tego przejazdu?”, „Sprawdź jakość danych przejazdu [numer]”.

## Krótkie odpowiedzi i prostsze wyjaśnienia

Dokładne powitania, podziękowania, pożegnania oraz pytania „Co potrafisz?” i „Jak się
masz?” otrzymują krótką odpowiedź bez wywołania Ollamy. Nie zawierają liczb ani cech
konkretnego obiektu, nie są oznaczane jako odczyt danych. Dopasowanie obejmuje całą
wiadomość: „Cześć, pokaż ranking” nadal trafia do modelu z funkcjami odczytu.
Dotychczasowe zależności API od bazy oraz sprawdzanie dostępności modelu w interfejsie
pozostają w mocy; nie jest to pełny tryb pracy offline.

Prośba „Wyjaśnij prościej ten wynik” kieruje model do ponownego odczytu danych lub
opisu metody i krótkiego wyjaśnienia bez żargonu. Wcześniejszy tekst odpowiedzi nie
zastępuje źródła danych. Odpowiedzi analityczne nadal wymagają lokalnego modelu.

## Granice tego etapu

Nie dodano symulacji inwestycji, analizy otoczenia szkół ani prognoz godzinowych.
Wymagają osobnych założeń, danych i walidacji. Wyniki obecnych funkcji są wynikami
eksperymentalnej metody RPS, a nie przewidywaniem wypadków.
