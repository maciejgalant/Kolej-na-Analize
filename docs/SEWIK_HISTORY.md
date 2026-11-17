# Historia zdarzeń SEWiK

Źródło: https://sewik.pl/ — zrzut listy przekazany przez użytkownika 16.11.2026.
Przepisano wyłącznie 20 widocznych rekordów; nie pobrano pełnego eksportu ani
szczegółów zdarzeń. Kryterium związku z pociągami pochodzi od użytkownika;
parametry formularza nie były widoczne na zrzucie. Nie należy deklarować pełnego
pokrycia Warszawy ani wszystkich kolizji z pociągami.

CSV: `backend/migrations/data/sewik_warsaw_user_snapshot.csv`.
Migracja 0010 zapisuje rekordy w `safety.incidents`, z identyfikatorami SEWiK,
datą, lokalną godziną (Europe/Warsaw), adresem i oryginalnym opisem miejsca.
Ostatni widoczny wpis jest z 18.11.2025; zakres deklarowany na stronie głównej
serwisu nie zastępuje dat przepisanych z listy. 14 wpisów opisano jako przejazd
kolejowy, 6 jako jezdnię. W trzech wpisach wykazano łącznie 5 rannych.
Puste skutki przechowujemy jako NULL, nigdy jako zero. Kategorie miejsca
„strzeżony/niestrzeżony” nie są automatycznie mapowane na kategorie A–F.

## Interfejs i przypisanie

- `GET /api/v1/incidents` — cały częściowy wykaz.
- `GET /api/v1/incidents?crossing_id=…` — wskazówki dopasowane po nazwie ulicy
  z powiązanych odcinków BDOT10k. To nie jest historia potwierdzona dla punktu.
- W karcie przejazdu wykaz jest pod składnikiem H, w „Jak obliczono RPS”.
  Przycisk „Historia zdarzeń · SEWiK” na mapie otwiera wykaz całego miasta.
- Zgodność ulicy nie zapisuje `crossing_id`, geometrii, `confirmed` ani pewności
  lokalizacji. Dotyczy to szczególnie różnych przejazdów i bocznic przy
  Chłopickiego. Wpisy „jezdnia” wymagają oddzielnej weryfikacji.
- H pozostaje unknown, waga nominalna 10%; wartości RPS i kompletność nie zmieniają się.
  Nawet brak dopasowanych wpisów nie dowodzi zerowej liczby wypadków.

Przed punktacją H trzeba odczytać szczegóły rekordów, zweryfikować współrzędne,
rodzaj pojazdu szynowego, konkretny przejazd i jednolity okres obserwacji.

## Uruchomienie

```powershell
docker compose build backend frontend
docker compose run --rm migrate
docker compose up -d backend frontend
```

Usługa `migrate` uruchamia `alembic upgrade head`.
Nie jest potrzebny osobny import ani dostęp do sieci. Dane syntetycznych
przejazdów DEMO nie otrzymują wskazówek z rzeczywistego wykazu Warszawy.
