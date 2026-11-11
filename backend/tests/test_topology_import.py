"""Dzielnice, tory, drogi i weryfikacja przejazdów na PostGIS (baza testowa)."""

import os

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from app.config import get_settings
from app.etl import topology_import as topo
from app.etl.bdot10k import Segment
from app.etl.crossing_import import import_crossings
from app.etl.crossing_scan import Bbox, ScannedCrossing, ScanResult
from app.etl.prg import District
from app.etl.topology_report import build_topology_report
from app.etl.utk_wms import WmsFeature

pytestmark = pytest.mark.skipif(
    os.environ.get("RAILSAFE_TEST_DB") != "1",
    reason="ustaw RAILSAFE_TEST_DB=1 i POSTGRES_* wskazujące na bazę *_test",
)

GROUND = "na powierzchni gruntu"
BRIDGE = "ponad powierzchnią gruntu poziom 1"
BBOX = Bbox(625000, 475000, 645000, 485000)


def square(e0, n0, e1, n1):
    return f"MULTIPOLYGON((({e0} {n0},{e1} {n0},{e1} {n1},{e0} {n1},{e0} {n0})))"


DISTRICTS = [
    District("146502_8", "Bemowo", square(631000, 480000, 632000, 481000)),
    District("146501_8", "Alfa", square(630000, 480000, 631000, 481000)),
]


def rail(local_id, points, level=GROUND, existence="eksploatowany"):
    attrs = {"polozenie": level, "kategoriaIstnienia": existence, "liczbaTorow": "2",
             "funkcjaToru": "tor szlakowy", "numerLinii": "9"}  # fmt: skip
    return Segment(local_id, attrs, tuple(points))


def road(local_id, points, level=GROUND):
    attrs = {"polozenie": level, "klasaDrogi": "droga lokalna", "ulicaCecha": "ul.",
             "ulicaNazwa1": "Testowa", "kategoriaZarzadzania": "gminna"}  # fmt: skip
    return Segment(local_id, attrs, tuple(points))


RAILS = [
    rail("r-main", [(630000, 480500), (632000, 480500)]),
    rail("r-bridge", [(631300, 480700), (631700, 480700)], level=BRIDGE),
    rail("r-old", [(631600, 480900), (631990, 480900)], existence="nieczynny"),
]
ROADS = [
    road("d-1", [(630500, 480300), (630500, 480700)]),
    road("d-4", [(631500, 480600), (631500, 480800)]),
    road("d-6", [(631800, 480800), (631800, 480990)]),
]
CROSSINGS = {
    "ok": (630500, 480502, "B"),
    "boundary-ped": (631000, 480500, "E"),
    "no-road": (630800, 480503, "C"),
    "bridge": (631500, 480700, "D"),
    "outside": (640000, 480000, "A"),
    "old-track": (631800, 480900, "D"),
}


@pytest.fixture
def conn():
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.postgres_db.endswith("_test")
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    with psycopg.connect(**settings.database_connect_kwargs, autocommit=True) as connection:
        scan = ScanResult(
            crossings=[
                ScannedCrossing(
                    WmsFeature("PKP_Polskie_Linie_Kolejowe", name, cat, "szlakowy", "PKP PLK"),
                    east, north,
                )
                for name, (east, north, cat) in CROSSINGS.items()
            ]
        )  # fmt: skip
        import_crossings(connection, scan, None, BBOX)
        yield connection
    command.downgrade(cfg, "base")


def run_import(conn) -> topo.TopologySummary:
    with conn.transaction():
        prg_id, bdot_id = topo.ensure_sources(conn)
        summary = topo.TopologySummary(job_id=topo.start_job(conn, bdot_id, {}))
        summary.districts = topo.load_districts(conn, DISTRICTS, prg_id)
        summary.rail_segments = topo.load_rail_segments(conn, RAILS, bdot_id)
        summary.road_segments = topo.load_road_segments(conn, ROADS, bdot_id)
        topo.verify_crossings(conn, summary)
        topo.finish_job(conn, summary)
    return summary


def state(conn) -> dict[str, tuple[str, str | None]]:
    rows = conn.execute(
        "SELECT c.name, c.verification_status, d.name FROM spatial.crossings c "
        "LEFT JOIN spatial.districts d USING (district_id)"
    ).fetchall()
    return {row[0]: (row[1], row[2]) for row in rows}


def flags(conn) -> set[tuple[str, str]]:
    rows = conn.execute(
        "SELECT c.name, f.code FROM system.quality_flags f "
        "JOIN spatial.crossings c ON c.crossing_id::text = f.entity_id WHERE f.code = ANY(%s)",
        (topo.FLAG_CODES,),
    ).fetchall()
    return set(rows)


def test_verification_and_district_rules(conn):
    summary = run_import(conn)
    assert (summary.districts, summary.rail_segments, summary.road_segments) == (2, 3, 3)
    assert state(conn) == {
        "ok": ("verified", "Alfa"),
        # na samej granicy: niższy TERYT (Alfa = 146501_8); kategoria E nie wymaga jezdni
        "boundary-ped": ("verified", "Alfa"),
        "no-road": ("unverified", "Alfa"),
        "bridge": ("unverified", "Bemowo"),
        "outside": ("unverified", None),
        "old-track": ("verified", "Bemowo"),
    }
    assert flags(conn) == {
        ("boundary-ped", "near_district_boundary"),
        ("no-road", "no_road_nearby"),
        ("bridge", "grade_separation_suspected"),
        ("outside", "outside_warsaw"),
        ("old-track", "track_inactive"),
    }
    assert summary.newly_verified == 3
    verified_at = conn.execute(
        "SELECT count(*) FROM spatial.crossings WHERE verification_status = 'verified' "
        "AND verified_at IS NOT NULL"
    ).fetchone()[0]
    assert verified_at == 3


def test_links_only_to_ground_level_segments_inside_city(conn):
    run_import(conn)
    links = conn.execute(
        "SELECT c.name, r.source_object_id, l.match_method, l.match_confidence "
        "FROM spatial.crossing_rail_segments l JOIN spatial.crossings c USING (crossing_id) "
        "JOIN spatial.rail_segments r USING (segment_id) ORDER BY 1, 2"
    ).fetchall()
    assert [(row[0], row[1], row[2]) for row in links] == [
        ("boundary-ped", "r-main", "proximity_candidate"),
        ("no-road", "r-main", "proximity_candidate"),
        ("ok", "r-main", "proximity_candidate"),
        ("old-track", "r-old", "proximity_candidate"),
    ]
    assert float(links[2][3]) == pytest.approx(0.87, abs=0.01)  # 2 m od toru przy zasięgu 15 m
    roads = conn.execute(
        "SELECT c.name FROM spatial.crossing_road_segments l "
        "JOIN spatial.crossings c USING (crossing_id) ORDER BY 1"
    ).fetchall()
    assert roads == [("bridge",), ("ok",), ("old-track",)]


def test_segment_attributes_are_stored(conn):
    run_import(conn)
    row = conn.execute(
        "SELECT line_number, level_position, existence, track_function, track_count, "
        "ST_SRID(geom) FROM spatial.rail_segments WHERE source_object_id = 'r-bridge'"
    ).fetchone()
    assert row == ("9", BRIDGE, "eksploatowany", "tor szlakowy", 2, 2180)
    assert conn.execute(
        "SELECT road_name, road_class, management_category FROM spatial.road_segments LIMIT 1"
    ).fetchone() == ("ul. Testowa", "droga lokalna", "gminna")


def test_rerun_is_idempotent_and_respects_manual_rejection(conn):
    run_import(conn)
    conn.execute(
        "UPDATE spatial.crossings SET verification_status = 'rejected_other' WHERE name = 'ok'"
    )
    before = flags(conn)
    second = run_import(conn)
    assert second.newly_verified == 0
    assert state(conn)["ok"] == ("rejected_other", "Alfa")
    assert flags(conn) == before
    counts = conn.execute(
        "SELECT (SELECT count(*) FROM spatial.districts), "
        "(SELECT count(*) FROM spatial.rail_segments), "
        "(SELECT count(*) FROM spatial.crossing_rail_segments)"
    ).fetchone()
    assert counts == (2, 3, 4)


def test_invalid_district_geometry_is_repaired(conn):
    bowtie = "MULTIPOLYGON(((0 0,10 10,10 0,0 10,0 0)))"
    with conn.transaction():
        prg_id, _ = topo.ensure_sources(conn)
        topo.load_districts(conn, [District("146599_8", "Kokardka", bowtie)], prg_id)
    assert conn.execute(
        "SELECT ST_IsValid(geom), GeometryType(geom) FROM spatial.districts"
    ).fetchone() == (True, "MULTIPOLYGON")


def test_report_summarises_city_and_review_list(conn):
    report = build_topology_report(conn, run_import(conn))
    assert "Razem **5**, zweryfikowanych **3**." in report
    assert "| Alfa | 2 | 1 | 3 | 2 |" in report
    assert "| (poza Warszawą) | 1 | 0 | 1 | 0 |" in report
    assert "| bridge | D | Bemowo | grade_separation_suspected |" in report
    assert "| no-road | C | Alfa | no_road_nearby |" in report
    assert "mediana" in report
