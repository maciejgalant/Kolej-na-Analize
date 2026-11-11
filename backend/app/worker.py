"""Worker importu i analiz — punkt wejścia (RSA-002: tylko szkielet).

Potoki ETL dojdą w RSA-004…RSA-010. Uruchomienie:
    docker compose run --rm worker
"""

import sys

from app.api.health import check_database
from app.config import get_settings


def main() -> int:
    database = check_database(get_settings())
    if database.status != "ok":
        print("worker: baza PostGIS niedostępna", file=sys.stderr)
        return 1
    print(f"worker: połączono z PostGIS {database.postgis_version}; brak zdefiniowanych zadań")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
