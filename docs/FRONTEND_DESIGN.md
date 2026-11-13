# Frontend RailSafe AI — wytyczne UI/UX (v1.0)

## Inspiracja wizualna
Referencja wskazana przez autora: https://www.intercity.pl/pl/ . Strona źródłowa może blokować automatyczny podgląd, dlatego poniżej zapisano **autorski kierunek inspirowany** czytelną estetyką kolejową: granat, biel, jasne tła, czerwone akcenty, prosta nawigacja i duże obszary informacji. Nie jest to pixel-perfect kopia. Nie używać logo, zdjęć, tekstów ani znaków towarowych PKP Intercity bez odrębnych uprawnień. Nagłówek musi oznaczać produkt jako „RailSafe AI — projekt edukacyjny, niezależny”.

## Tokeny design systemu (propozycja, do weryfikacji w przeglądarce)
| Token | Kolor | Rola |
|---|---|---|
| navy-900 | #102B4E | nagłówek i główny tekst |
| navy-700 | #174A7E | nawigacja, aktywne kontrolki |
| blue-500 | #287BC1 | linki i stany focus |
| red-600 | #C73A43 | CTA, akcent, nie domyślny znacznik ryzyka |
| white | #FFFFFF | karty |
| surface | #F3F6FA | tło aplikacji |
| slate-600 | #526476 | tekst pomocniczy |
| border | #D8E2EC | linie i obrysy |

Typografia: font systemowy Inter/Arial fallback; H1 ~28–32px, sekcje 18–22px, body 14–16px. Siatka 8px, karty zaokrąglone 8–12px, subtelne obrysy, mało cieni. WCAG AA dla kontrastów. Nie wyróżniać ryzyka samym kolorem.

## Główny ekran desktop
```
┌──────────────────────────────────────────────────────────────────────────┐
│ RailSafe AI    Analiza przejazdów | Porównania | O projekcie   ● Dane    │
├──────────────────────────────────────────────────────────────────────────┤
│ Warszawa  > Wola      [Okres ▼] [Źródła ▼] [Aktualizuj]                   │
├───────────────────────┬────────────────────────────────┬─────────────────┤
│ FILTRY I RANKING      │ MAPA LEAFLET                   │ SZCZEGÓŁY       │
│ 18 dzielnic           │ Punkty przejazdów              │ Przejazd X      │
│ Status danych         │ Linie drogowe i kolejowe       │ RPS, składniki  │
│ 1. Przejazd A         │ Granica dzielnicy              │ wykresy         │
│ 2. Przejazd B         │ Interakcja z rankingiem        │ wiarygodność    │
│ ...                   │                                │ źródła          │
├───────────────────────┴────────────────────────────────┴─────────────────┤
│ Asystent AI: [Pokaż przejazdy o najwyższym priorytecie na Woli ...] [→] │
└──────────────────────────────────────────────────────────────────────────┘
```
Makieta tekstowa obrazuje relacje, nie docelowe proporcje. W ekranach węższych karta szczegółów i czat jako drawer/panel, a ranking jako zakładka.

## Interakcje
- Kliknięcie punktu mapy podświetla wiersz rankingu i otwiera kartę przejazdu.
- Wybór dzielnicy aktualizuje mapę, dane tabeli i wykresy.
- Filtry: obszar, okres, plan/wykonanie, typ pomiaru, status jakości, dostępność cech.
- Legenda oddziela **priorytet RPS** od **kompletności danych**. Punkty bez rankingu mają własny neutralny symbol.
- Panel szczegółów: nazwa/ID przejazdu, kategoria i źródło, cztery komponenty RPS, ruch drogowy/kolejowy z jednostkami, czas aktualizacji, ostrzeżenia, pochodzenie.
- AI: odpowiedź tekstowa plus obiekty `map_action` i `chart_action`; zawsze istnieją odpowiedniki manualne.
- Tryb demo offline: widoczny pasek „Dane demonstracyjne”; nigdy nie przedstawiać fikcyjnych danych jako rzeczywistych.

## Ekrany
1. Dashboard analityczny (główny).
2. Karta przejazdu (panel boczny).
3. Porównania dzielnic i okresów.
4. Źródła, jakość danych, metodologia.
5. Informacje o projekcie, autorstwie i zastrzeżeniach.

## Dostępność i technologia
React + TypeScript + Vite + Leaflet; wykresy np. Recharts; komponenty autorskie lub biblioteka z licencją zgodną z repo. Focus visible, sterowanie klawiaturą, etykiety formularzy, aria-live dla wyników AI, przyjazne stany loading/empty/error. UI nie zakłada pełnych danych dla wszystkich przejazdów.

## Stan wdrożenia (v1.1, listopad 2026)
Układ odbiega od makiety powyżej na rzecz przejrzystości:
- **Asystent AI** to okrągły przycisk w prawym dolnym rogu; rozmowa otwiera się w oknie-dymku (Esc zamyka, kropka sygnalizuje nową odpowiedź). W trakcie odpowiedzi widać animację i licznik sekund.
- **Szczegóły przejazdu** pojawiają się jako wysuwany panel dopiero po wyborze obiektu. Na wierzchu jest wynik i pozycja; reszta (ruch kolejowy, droga i tory, dane ewidencyjne, źródła) w zwijanych sekcjach, których nagłówek pokazuje najważniejszą wartość.
- **Filtry i kolejność**, **legenda** i **stan usług** są zwinięte; **opis danych, metody i ograniczeń** otwiera się w oknie „O danych i metodzie”.
- **Ładowanie**: szkielety listy i karty, nakładka z kołem postępu na mapie. Przy `prefers-reduced-motion` animacje są wyłączone.
- Pasek „DANE DEMONSTRACYJNE” pozostaje zawsze widoczny; nie wolno go chować w oknie.
