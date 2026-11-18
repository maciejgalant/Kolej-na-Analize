# Kolej na Analizę — nazwa i identyfikacja

Nazwa aplikacji i projektu: **Kolej na Analizę**.
Repozytorium: `maciejgalant/Kolej-na-Analize`.

Zaakceptowane logo łączy motyw nowoczesnego pociągu, podniesionej rogatki i wykresu. Wersja PNG z przezroczystością, 1100×367 px: `frontend/public/brand/kolej-na-analize-logo.png`. Pełny znak jest używany na jasnym tle w panelu rozmów, na ekranie powitalnym i w README. Mała ikona karty przeglądarki jest uproszczonym znakiem rogatki i wykresu. Kolory: granat `#102b4e`, pomarańcz `#d9570b`, biel.

Nazwa nie oznacza oficjalnego produktu PKP ani PKP Intercity. RPS pozostaje nazwą techniczną eksperymentalnego wskaźnika priorytetu do dalszej oceny; nie zmienia się metodyka ani jej wersja.

## Zgodność istniejących instalacji

| Identyfikator | Powód zachowania |
|---|---|
| `COMPOSE_PROJECT_NAME=railsafe` i nazwy sieci/obrazów | Zachowanie powiązań usług i istniejących wolumenów danych |
| Baza i użytkownik `railsafe` | Brak konieczności migracji danych lub zmiany uprawnień |
| `RAILSAFE_TEST_DB` | Zgodność konfiguracji testów i CI |
| `railsafe.chat.v1`, `railsafe.basemap`, `railsafe.window.*` | Zachowanie zapisanych rozmów i preferencji w tej samej przeglądarce i pod tym samym adresem aplikacji |

To historyczne identyfikatory wewnętrzne, a nie nazwa widoczna dla użytkownika. Nie należy zmieniać ich wyłącznie z powodu nowego brandingu. Zmiana hosta lub portu aplikacji tworzy inną przestrzeń `localStorage`; sama zmiana nazwy repozytorium jej nie przenosi ani nie usuwa.
