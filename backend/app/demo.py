"""Syntetyczny zestaw demonstracyjny (RSA-014): uruchomienie bez sieci i kluczy API.

Wszystkie obiekty są FIKCYJNE: nazwy zaczynają się od „DEMO-”, a dzielnice od „Demo-”.
Zestaw przechodzi przez te same funkcje importu i analizy co dane rzeczywiste, więc
demonstruje działanie aplikacji, a nie stan sieci kolejowej. Danych demonstracyjnych
nie wolno mieszać z rzeczywistymi: `load_demo` odmawia pracy na bazie z prawdziwymi
przejazdami, a importy rzeczywiste — na bazie z zestawem demonstracyjnym.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import psycopg

from app.analysis.run import RunSummary, run_analysis
from app.etl import road_counts as rc
from app.etl import topology_import as topo
from app.etl.bdot10k import GROUND_LEVEL, Segment
from app.etl.crossing_import import import_crossings
from app.etl.crossing_scan import Bbox, ScannedCrossing, ScanResult
from app.etl.gtfs import Feed, merge_feeds
from app.etl.prg import District
from app.etl.train_flow import import_train_flow
from app.etl.utk_wms import WmsFeature
from app.etl.zdm_apr import PointReport

DEMO_PREFIX = "DEMO-"
DEMO_LABEL = "DEMO"
BBOX = Bbox(629000, 477000, 638000, 484000)
MAIN_N = 480500.0  # linia główna, przebieg zachód–wschód, 2 tory
BRANCH_E = 634000.0  # linia boczna, przebieg południe–północ, 1 tor
SIDING_N = 482000.0  # bocznica bez ruchu pasażerskiego


class DemoConflict(RuntimeError):
    """Baza zawiera dane, których nie wolno mieszać z żądaną operacją."""


@dataclass(frozen=True)
class DemoCrossing:
    name: str
    east: float
    north: float
    category: str
    road_class: str | None  # None = brak jezdni w danych
    skew: bool = False  # jezdnia pod kątem 45° zamiast prostopadle
    # tylko ulica równoległa do toru, 25 m obok: potwierdza drogę, ale nie jest ulicą przejazdu
    parallel_only: bool = False


CROSSINGS = [
    DemoCrossing("DEMO-01", 630600, MAIN_N, "A", "droga główna"),
    DemoCrossing("DEMO-02", 631400, MAIN_N, "B", "droga zbiorcza"),
    DemoCrossing("DEMO-03", 632600, MAIN_N, "C", "droga lokalna", skew=True),
    DemoCrossing("DEMO-04", 633300, MAIN_N, "D", "droga dojazdowa"),
    DemoCrossing("DEMO-05", 635200, MAIN_N, "B", "droga lokalna"),
    DemoCrossing("DEMO-06", BRANCH_E, 479000, "D", "droga wewnętrzna"),
    DemoCrossing("DEMO-07", BRANCH_E, 481500, "C", "droga zbiorcza"),
    DemoCrossing("DEMO-08", BRANCH_E, 482600, "F", "droga zbiorcza", parallel_only=True),
    DemoCrossing("DEMO-09", 631000, SIDING_N, "D", "droga dojazdowa"),
    DemoCrossing("DEMO-10", 631000, MAIN_N, "E", None),
    DemoCrossing("DEMO-11", BRANCH_E, 479800, "E", None),
]
# Fikcyjny punkt pomiaru ruchu drogowego: 150 m od DEMO-02, na tej samej ulicy.
DEMO_ROAD_SOURCE = "demo_road_counts"
DEMO_STATION = ("DEMO-APR-1", "Demonstracyjna 02", 631400.0, MAIN_N + 150, 21500)
# kursy na dobę: (dni robocze, weekend)
TRIPS = {"MAIN": (120, 80), "BRANCH": (24, 12)}


def _square(e0: float, n0: float, e1: float, n1: float) -> str:
    return f"MULTIPOLYGON((({e0} {n0},{e1} {n0},{e1} {n1},{e0} {n1},{e0} {n0})))"


DISTRICTS = [
    District("999901_8", "Demo-Zachód", _square(630000, 478000, 632000, 483000)),
    District("999902_8", "Demo-Centrum", _square(632000, 478000, 634500, 483000)),
    District("999903_8", "Demo-Wschód", _square(634500, 478000, 636500, 483000)),
]


def _rail(local_id: str, points: list[tuple[float, float]], tracks: int, line: str) -> Segment:
    attrs = {
        "polozenie": GROUND_LEVEL,
        "kategoriaIstnienia": "eksploatowany",
        "liczbaTorow": str(tracks),
        "funkcjaToru": "tor szlakowy",
        "numerLinii": line,
    }
    return Segment(local_id, attrs, tuple(points))


RAILS = [
    _rail("demo-main", [(630000, MAIN_N), (636500, MAIN_N)], 2, "901"),
    _rail("demo-branch", [(BRANCH_E, 478000), (BRANCH_E, 483000)], 1, "902"),
    _rail("demo-siding", [(630500, SIDING_N), (631500, SIDING_N)], 1, "903"),
]


def _roads() -> list[Segment]:
    roads = []
    for item in CROSSINGS:
        if item.road_class is None:
            continue
        on_branch = item.east == BRANCH_E
        if item.parallel_only:
            ends = [(item.east + 25, item.north - 200), (item.east + 25, item.north + 200)]
        elif item.skew:
            ends = [(item.east - 150, item.north - 150), (item.east + 150, item.north + 150)]
        elif on_branch:
            ends = [(item.east - 200, item.north), (item.east + 200, item.north)]
        else:
            ends = [(item.east, item.north - 200), (item.east, item.north + 200)]
        attrs = {
            "polozenie": GROUND_LEVEL,
            "klasaDrogi": item.road_class,
            "ulicaCecha": "ul.",
            "ulicaNazwa1": f"Demonstracyjna {item.name[-2:]}",
            "kategoriaZarzadzania": "gminna",
        }
        roads.append(Segment(f"demo-road-{item.name[-2:]}", attrs, tuple(ends)))
    return roads


def demo_present(conn: psycopg.Connection) -> bool:
    if conn.execute("SELECT to_regclass('spatial.crossings')").fetchone()[0] is None:
        return False
    return bool(
        conn.execute(
            "SELECT EXISTS (SELECT 1 FROM spatial.crossings WHERE name LIKE %s)",
            (DEMO_PREFIX + "%",),
        ).fetchone()[0]
    )


def real_data_present(conn: psycopg.Connection) -> bool:
    return bool(
        conn.execute(
            "SELECT EXISTS (SELECT 1 FROM spatial.crossings WHERE name NOT LIKE %s)",
            (DEMO_PREFIX + "%",),
        ).fetchone()[0]
    )


def _lonlat(conn: psycopg.Connection, east: float, north: float) -> tuple[float, float]:
    return conn.execute(
        "SELECT ST_X(p), ST_Y(p) FROM (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), "
        "2180), 4326) AS p) t",
        (east, north),
    ).fetchone()


def _feed(conn: psycopg.Connection, week: list[date]) -> Feed:
    lines = {
        "MAIN": [(630000, MAIN_N), (636500, MAIN_N)],
        "BRANCH": [(BRANCH_E, 478000), (BRANCH_E, 483000)],
    }
    feed = Feed(version=DEMO_LABEL, start=week[0], end=week[-1])
    feed.service_dates = {"WD": set(week[:5]), "WE": set(week[5:])}
    for shape_id, points in lines.items():
        feed.shapes[shape_id] = [_lonlat(conn, e, n) for e, n in points]
        workday, weekend = TRIPS[shape_id]
        feed.trips_by_shape[shape_id] = ["WD"] * workday + ["WE"] * weekend
        feed.rail_trips += workday + weekend
    return merge_feeds({"PL": feed})


def _load_road_counts(conn: psycopg.Connection, week: list[date]) -> None:
    """Fikcyjny pomiar natężenia w formacie importu ZDM; źródło oznaczone jako demo."""
    point_id, street, east, north, per_day = DEMO_STATION
    lon, lat = _lonlat(conn, east, north)
    share = [1, 1, 1, 1, 1, 2, 4, 7, 7, 6, 5, 5, 5, 5, 6, 7, 7, 7, 6, 5, 4, 3, 2, 2]
    hourly = [round(per_day * part / sum(share)) for part in share]
    report = PointReport(point_id, street, "odcinek demonstracyjny", lon, lat, per_day,
                         per_day + 1800, 5, hourly, week[0], week[4])  # fmt: skip
    with conn.transaction():
        source_id = conn.execute(
            """
            INSERT INTO system.sources (code, name, provider, is_demo)
            VALUES (%s, 'Fikcyjne pomiary ruchu drogowego (zestaw demonstracyjny)', 'RailSafe AI',
                    true)
            ON CONFLICT (code) DO UPDATE SET is_demo = true
            RETURNING source_id
            """,
            (DEMO_ROAD_SOURCE,),
        ).fetchone()[0]
        stations = rc.stations_from_reports([report])
        summary = rc.RoadCountsSummary(
            job_id=rc.start_job(conn, source_id, {"demo": True}),
            start=week[0],
            end=week[4],
            day_type="miarodajny",
            stations_seen=1,
            matches=rc.match_stations(conn, stations, rc.crossing_streets(conn)),
            reports={point_id: report},
        )
        rc.save(conn, source_id, summary, stations)


def load_demo(conn: psycopg.Connection, today: date | None = None) -> RunSummary:
    """Ładuje zestaw i liczy ranking. Powtórne wywołanie odświeża zestaw."""
    if real_data_present(conn):
        raise DemoConflict(
            "Baza zawiera rzeczywiste przejazdy. Zestaw demonstracyjny wymaga pustej bazy "
            "(osobny wolumen), żeby dane fikcyjne nie zmieszały się z prawdziwymi."
        )
    today = today or date.today()
    monday = today + timedelta(days=(7 - today.weekday()) % 7)
    week = [monday + timedelta(days=offset) for offset in range(7)]
    scan = ScanResult(
        crossings=[
            ScannedCrossing(
                WmsFeature(
                    "PKP_Polskie_Linie_Kolejowe",
                    item.name,
                    item.category,
                    "szlakowy",
                    "Zarządca demonstracyjny",
                ),
                item.east,
                item.north,
            )
            for item in CROSSINGS
        ]
    )
    import_crossings(conn, scan, None, BBOX)
    with conn.transaction():
        prg_id, bdot_id = topo.ensure_sources(conn)
        summary = topo.TopologySummary(job_id=topo.start_job(conn, bdot_id, {"demo": True}))
        summary.districts = topo.load_districts(conn, DISTRICTS, prg_id)
        summary.rail_segments = topo.load_rail_segments(conn, RAILS, bdot_id)
        summary.road_segments = topo.load_road_segments(conn, _roads(), bdot_id)
        topo.verify_crossings(conn, summary)
        topo.finish_job(conn, summary)
    import_train_flow(conn, _feed(conn, week), week)
    _load_road_counts(conn, week)
    # Zadania importu noszą etykietę DEMO, żeby pochodzenie było widoczne także w bazie.
    conn.execute("UPDATE system.import_jobs SET snapshot_label = %s", (DEMO_LABEL,))
    return run_analysis(conn, is_demo=True)
