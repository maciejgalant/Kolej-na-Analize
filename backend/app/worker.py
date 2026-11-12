"""Worker importu i analiz.

docker compose run --rm worker                                        # test połączenia
docker compose run --rm worker python -m app.worker import-crossings  # RSA-004
"""

import argparse
import json
import sys
from pathlib import Path

import psycopg

from app.api.health import check_database
from app.config import get_settings

# Warszawa z niewielkim marginesem, EPSG:2180: E_min, N_min, E_max, N_max.
WARSAW_BBOX = (625500.0, 470500.0, 656500.0, 503500.0)


def _iso_date(text: str):
    from datetime import date

    value = date.fromisoformat(text)
    if value.weekday() != 0:
        raise argparse.ArgumentTypeError("tydzień odniesienia musi zaczynać się w poniedziałek")
    return value


def status() -> int:
    database = check_database(get_settings())
    if database.status != "ok":
        print("worker: baza PostGIS niedostępna", file=sys.stderr)
        return 1
    print(
        f"worker: PostGIS {database.postgis_version}, schemat {database.schema_revision}; "
        "dostępne zadania: import-crossings, import-topology, import-schedule, run-analysis"
    )
    return 0


def import_crossings_command(args: argparse.Namespace) -> int:
    from app.etl.crossing_import import bbox_to_wgs84, import_crossings
    from app.etl.crossing_report import build_report
    from app.etl.crossing_scan import Bbox, scan_crossings
    from app.etl.overpass import (
        OverpassUnavailable,
        build_query,
        fetch_osm_crossings,
        parse_overpass,
    )
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
        if args.osm_file is not None:
            osm = parse_overpass(json.loads(args.osm_file.read_text(encoding="utf-8")))
            log(f"OSM z pliku {args.osm_file}: {len(osm)} punktów")
        elif not args.skip_osm:
            area = bbox_to_wgs84(conn, bbox)
            try:
                osm = fetch_osm_crossings(*area)
                log(f"OSM: {len(osm)} punktów")
            except OverpassUnavailable as error:
                log(f"OSM niedostępne; import bez kontroli krzyżowej. Szczegóły: {error}")
                log(
                    "Obejście: wykonaj poniższe zapytanie na https://overpass-turbo.eu "
                    "(Eksport -> surowe dane OSM/JSON), zapisz jako reports/osm.json i uruchom "
                    "import z opcją --osm-file /reports/osm.json"
                )
                print(build_query(*area), file=sys.stderr)

        summary = import_crossings(conn, scan, osm, bbox, wms.requests_made)
        report = build_report(conn, scan, summary)
    _write_report(report, args.report, log)
    log(f"zapisano {summary.written} przejazdów, potwierdzonych w OSM: {summary.matched}")
    return 0


def _write_report(report: str, path: Path, log) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")
        log(f"raport zapisany: {path}")
    except OSError as error:
        log(f"nie udało się zapisać raportu ({error}); wypisuję na standardowe wyjście")
        print(report)


def import_topology_command(args: argparse.Namespace) -> int:
    import httpx

    from app.etl import topology_import as topo
    from app.etl.bdot10k import (
        BDOT_URL,
        RAILWAY_VEHICLE,
        find_member,
        iter_segments,
        near_any_point,
    )
    from app.etl.prg import fetch_districts
    from app.etl.remote_zip import open_remote_zip
    from app.etl.topology_report import build_topology_report
    from app.etl.utk_wms import USER_AGENT

    def log(message: str) -> None:
        print(f"import-topology: {message}", file=sys.stderr, flush=True)

    e_min, n_min, e_max, n_max = args.bbox
    with (
        psycopg.connect(**get_settings().database_connect_kwargs) as conn,
        httpx.Client(timeout=180.0, headers={"User-Agent": USER_AGENT}) as http,
    ):
        points = topo.crossing_points(conn)
        if not points:
            log("brak przejazdów w bazie — najpierw uruchom import-crossings")
            return 1
        districts = fetch_districts(e_min, n_min, e_max, n_max, http)
        log(f"PRG: {len(districts)} dzielnic")
        archive, raw = open_remote_zip(http, BDOT_URL)
        names = archive.namelist()
        with archive.open(find_member(names, "OT_SKTR_L.xml")) as stream:
            rails = [
                s
                for s in iter_segments(stream, "OT_SKTR_L")
                if s.attributes.get("rodzajPojazduSzynowego") == RAILWAY_VEHICLE
            ]
        log(f"BDOT10k: {len(rails)} odcinków torów kolejowych")
        near = near_any_point(points, topo.ROAD_PREFILTER_M)
        with archive.open(find_member(names, "OT_SKJZ_L.xml")) as stream:
            roads = [s for s in iter_segments(stream, "OT_SKJZ_L") if near(s)]
        log(
            f"BDOT10k: {len(roads)} odcinków jezdni przy przejazdach "
            f"(zapytań HTTP: {raw.requests_made}, wydanie paczki: {raw.last_modified})"
        )

        with conn.transaction():
            prg_id, bdot_id = topo.ensure_sources(conn)
            summary = topo.TopologySummary(
                job_id=topo.start_job(
                    conn,
                    bdot_id,
                    {
                        "bbox_2180": list(args.bbox),
                        "bdot_last_modified": raw.last_modified,
                        "rail_radius_m": topo.RAIL_RADIUS_M,
                        "road_radius_m": topo.ROAD_RADIUS_M,
                    },
                )
            )
            summary.districts = topo.load_districts(conn, districts, prg_id)
            summary.rail_segments = topo.load_rail_segments(conn, rails, bdot_id)
            summary.road_segments = topo.load_road_segments(conn, roads, bdot_id)
            topo.verify_crossings(conn, summary)
            topo.finish_job(conn, summary)
        report = build_topology_report(conn, summary)
    _write_report(report, args.report, log)
    log(f"nowo zweryfikowanych przejazdów: {summary.newly_verified}; flagi: {summary.flags}")
    return 0


def import_schedule_command(args: argparse.Namespace) -> int:
    from datetime import date, timedelta

    import httpx

    from app.etl.crossing_import import bbox_to_wgs84
    from app.etl.crossing_scan import Bbox
    from app.etl.gtfs import GTFS_URL, WKD_GTFS_URL, merge_feeds, read_feed, reference_week
    from app.etl.remote_zip import open_remote_zip
    from app.etl.train_flow import build_flow_report, import_train_flow
    from app.etl.utk_wms import USER_AGENT

    def log(message: str) -> None:
        print(f"import-schedule: {message}", file=sys.stderr, flush=True)

    with (
        psycopg.connect(**get_settings().database_connect_kwargs) as conn,
        httpx.Client(timeout=180.0, headers={"User-Agent": USER_AGENT}) as http,
    ):
        in_city = conn.execute(
            "SELECT count(*) FROM spatial.crossings WHERE district_id IS NOT NULL"
        ).fetchone()[0]
        if in_city == 0:
            log("brak przejazdów z dzielnicą — najpierw import-crossings i import-topology")
            return 1
        south, west, north, east = bbox_to_wgs84(conn, Bbox(*args.bbox))
        feeds, modified = {}, {}
        for name, url in (("PL", GTFS_URL), ("WKD", WKD_GTFS_URL)):
            archive, raw = open_remote_zip(http, url)
            feeds[name] = read_feed(archive, west, south, east, north)
            modified[name] = raw.last_modified
            log(
                f"GTFS {name} {feeds[name].version}: {len(feeds[name].shapes)} tras kolejowych "
                f"w obszarze, {feeds[name].rail_trips} kursów, zakres {feeds[name].start} – "
                f"{feeds[name].end} (zapytań HTTP: {raw.requests_made})"
            )
        feed = merge_feeds(feeds)
        week = (
            [args.week_start + timedelta(days=i) for i in range(7)]
            if args.week_start
            else reference_week(feed, date.today())
        )
        log(f"tydzień odniesienia: {week[0]} – {week[-1]}")
        summary = import_train_flow(conn, feed, week, json.dumps(modified))
        report = build_flow_report(conn, feed, summary)
    _write_report(report, args.report, log)
    log(
        f"przejazdów: {summary.crossings}, z kursami pasażerskimi: {summary.with_trains}, "
        f"z progiem rozszerzonym: {summary.extended}, wrażliwych: {summary.sensitive}"
    )
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
        "--osm-file", type=Path, default=None, help="odpowiedź Overpass (JSON) pobrana ręcznie"
    )
    crossings.add_argument(
        "--report",
        type=Path,
        default=Path("/reports/DATA_AUDIT_crossings.md"),
        help="ścieżka raportu Markdown",
    )
    topology = commands.add_parser("import-topology", help="dzielnice, tory, drogi (RSA-005)")
    topology.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        default=WARSAW_BBOX,
        metavar=("E_MIN", "N_MIN", "E_MAX", "N_MAX"),
        help="obszar w EPSG:2180",
    )
    topology.add_argument(
        "--report",
        type=Path,
        default=Path("/reports/DATA_AUDIT_topology.md"),
        help="ścieżka raportu Markdown",
    )
    schedule = commands.add_parser("import-schedule", help="planowe pociągi z GTFS (RSA-006)")
    schedule.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        default=WARSAW_BBOX,
        metavar=("E_MIN", "N_MIN", "E_MAX", "N_MAX"),
        help="obszar w EPSG:2180",
    )
    schedule.add_argument(
        "--week-start",
        type=_iso_date,
        default=None,
        help="poniedziałek tygodnia odniesienia (RRRR-MM-DD); domyślnie najbliższy pełny tydzień",
    )
    schedule.add_argument(
        "--report",
        type=Path,
        default=Path("/reports/DATA_AUDIT_trains.md"),
        help="ścieżka raportu Markdown",
    )
    analysis = commands.add_parser("run-analysis", help="wskaźnik RPS i ranking (RSA-010)")
    analysis.add_argument(
        "--report",
        type=Path,
        default=Path("/reports/RPS_report.md"),
        help="ścieżka raportu Markdown",
    )
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except _network_errors() as error:
        # Zewnętrzne serwery bywają chwilowo niedostępne; baza pozostaje bez zmian.
        print(f"{args.command}: przerwano — {error}", file=sys.stderr)
        return 2


def run_analysis_command(args: argparse.Namespace) -> int:
    from app.analysis.run import build_run_report, run_analysis

    def log(message: str) -> None:
        print(f"run-analysis: {message}", file=sys.stderr, flush=True)

    with psycopg.connect(**get_settings().database_connect_kwargs) as conn:
        try:
            summary = run_analysis(conn)
        except RuntimeError as error:
            log(str(error))
            return 1
        report = build_run_report(conn, summary)
    _write_report(report, args.report, log)
    log(f"przebieg {summary.run_id}: ocenionych {summary.scored}, z pozycją {summary.ranked}")
    return 0


def _network_errors() -> tuple[type[Exception], ...]:
    import httpx

    from app.etl.remote_zip import RemoteFileUnavailable

    return (RemoteFileUnavailable, httpx.TransportError, httpx.HTTPStatusError)


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "run-analysis":
        return run_analysis_command(args)
    if args.command == "import-schedule":
        return import_schedule_command(args)
    if args.command == "import-crossings":
        return import_crossings_command(args)
    if args.command == "import-topology":
        return import_topology_command(args)
    return status()


if __name__ == "__main__":
    raise SystemExit(main())
