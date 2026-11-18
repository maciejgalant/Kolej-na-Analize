# Integracja PKP PLK — kontekst stacyjny

W nagłówku aplikacji przycisk **Ruch kolejowy PKP PLK** otwiera panel. Wyszukaj
stację (domyślnie Warszawa), wybierz ją i pobierz realizację kursów lub utrudnienia.
Realizacja pokazuje plan, wykonanie, opóźnienia i status potwierdzenia na stacji.
Identyfikator kursu nie jest numerem handlowym pociągu. Przeglądarka łączy się tylko
z naszym backendem; klucz nie trafia do frontendu ani do adresów URL.

## Uruchomienie

W istniejącym lokalnym `.env` ustaw `PLK_API_KEY` na przyznany klucz. Nie umieszczaj
go w kodzie, zrzutach ekranu, zgłoszeniu konkursowym ani commicie. Następnie:

```sh
docker compose up -d --build backend frontend
```

`GET /api/v1/rail/status` pokazuje wyłącznie obecność konfiguracji, nie potwierdza
ważności klucza. Weryfikację dostępu wykonuje pierwsze pobranie stacji.

## Backend

- `/api/v1/rail/stations?search=Warszawa&page=1`
- `/api/v1/rail/operations?station_id=ID&page=1` — po 100 kursów, zachowana paginacja.
- `/api/v1/rail/disruptions?station_id=ID`
- `/api/v1/rail/schedules?station_id=ID&day=2026-11-16` — plan na wybrany dzień.

Oficjalny kontrakt: https://pdp-api.plk-sa.pl/swagger/v1/swagger.json
Dokumentacja: https://pdp-api.plk-sa.pl/api-documentation

Odpowiedź zachowuje dane dostawcy w `data`, a obok podaje źródło, moment pobrania
i informację o użyciu pamięci podręcznej. `generatedAt` dostawcy jest w UTC;
plan i wykonanie dla stacji w Polsce są w lokalnym czasie Europe/Warsaw.
Brak opóźnienia lub potwierdzenia nie jest zastępowany zerem.

## Aktualizacje i błędy

Pobieranie na żądanie, bez automatycznego odpytywania. Wspólna pamięć procesu:
stacje 24 godziny, pozostałe odpowiedzi 5 minut, do 64 zapytań w pamięci.
Żądania równoległe są scalane. Limit lokalny 90 zapytań/godzinę i 900/dobę zostawia
zapas pakietu Basic. Dotyczy jednego procesu backendu; przy wielu workerach lub
innych aplikacjach z tym samym kluczem potrzebny jest wspólny limiter.
Po 429 respektujemy liczbowy `Retry-After` (minimum 5 minut), po błędzie dostępu
lub połączenia stosujemy przerwę. Nie zwracamy surowych błędów dostawcy ani klucza.
Po awarii nie prezentujemy starej odpowiedzi jako aktualnej. Nie zapisujemy historii
odpowiedzi na dysku ani w bazie. Limity dostawcy nadal są nadrzędne.

## Zakres analityczny

Panel prezentuje rzeczywiste dane także przy demonstracyjnej bazie przejazdów;
jest opisany oddzielnie i nie łączy ich z fikcyjnymi obiektami. Nie zmienia rankingu
WPO ani liczników GTFS/WKD. Potwierdzenie na stacji nie oznacza potwierdzenia
na konkretnym przejeździe. Brak pełnego pokrycia ruchu towarowego/manewrowego.
Historia wypadków i incydentów pozostaje poza zakresem tej integracji.

Przed publikacją wyników zweryfikuj warunki przypisane do otrzymanego klucza.
