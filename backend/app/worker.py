"""Worker importu i analiz.

docker compose run --rm worker                                        # test połączenia
docker compose run --rm worker python -m app.worker import-crossings  # RSA-004
"""

import argparse
import sys
from pathlib import Path

import httpx
import psycopg

from app.api.health import check_database
from app.config import get_settings

# Warszawa z niewielkim marginesem, EPSG:2180: E_min, N_min, E_max, N_max.
WARSAW_BBOX = (625500.0, 470500.0, 656500.0, 503500.0)


def status() -> int:
    database = check_database(get_settings())
    if database.status != "ok":
        print("worker: baza PostGIS niedostępna", file=sys.stderr)
        return 1
    print(
        f"worker: PostGIS {database.postgis_version}, schemat {database.schema_revision}; "
        "dostępne zadania: import-crossings"
    )
    return 0


def import_crossings_command(args: argparse.Namespace) -> int:
    from app.etl.crossing_import import bbox_to_wgs84, import_crossings
    from app.etl.crossing_report import build_report
    from app.etl.crossing_scan import Bbox, scan_crossings
    from app.etl.overpass import fetch_osm_crossings
    from app.etl.utk_wms import UtkWmsClient

    def log(message: str) -> None:
        print(f"import-crossings: {message}", file=sys.stderr, flush=True)

    bbox = Bbox(*args.bbox)
    with psycopg.connect(**get_settings().database_connect_kwargs) as conn:
        wms = UtkWmsClient()
        try:
            scan = scan_crossings(wms, bbox, log)
        finally:
            wms.close()
        log(f"odczytano {len(scan.crossings)} obiektów, zapytań WMS: {wms.requests_made}")

        osm = None
        if not args.skip_osm:
            try:
                osm = fetch_osm_crossings(*bbox_to_wgs84(conn, bbox))
                log(f"OSM: {len(osm)} punktów")
            except (httpx.HTTPError, ValueError) as error:
                log(f"OSM niedostępne ({error}); import bez kontroli krzyżowej")

        summary = import_crossings(conn, scan, osm, bbox, wms.requests_made)
        report = build_report(conn, scan, summary)
    try:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report, encoding="utf-8")
        log(f"raport zapisany: {args.report}")
    except OSError as error:
        log(f"nie udało się zapisać raportu ({error}); wypisuję na standardowe wyjście")
        print(report)
    log(f"zapisano {summary.written} przejazdów, potwierdzonych w OSM: {summary.matched}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.worker")
    commands = parser.add_subparsers(dest="command")
    crossings = commands.add_parser("import-crossings", help="ewidencja przejazdów (RSA-004)")
    crossings.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        default=WARSAW_BBOX,
        metavar=("E_MIN", "N_MIN", "E_MAX", "N_MAX"),
        help="obszar w EPSG:2180",
    )
    crossings.add_argument("--skip-osm", action="store_true", help="bez kontroli w OSM")
    crossings.add_argument(
        "--report",
        type=Path,
        default=Path("/reports/DATA_AUDIT_crossings.md"),
        help="ścieżka raportu Markdown",
    )
    args = parser.parse_args(argv)
    if args.command == "import-crossings":
        return import_crossings_command(args)
    return status()


if __name__ == "__main__":
    raise SystemExit(main())
