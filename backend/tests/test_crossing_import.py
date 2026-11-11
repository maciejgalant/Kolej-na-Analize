"""Import przejazdów do PostGIS — wymaga bazy testowej (jak test_migrations)."""

import os

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from app.config import get_settings
from app.etl.crossing_import import import_crossings
from app.etl.crossing_report import build_report
from app.etl.crossing_scan import Bbox, ScannedCrossing, ScanResult
from app.etl.overpass import OsmCrossing
from app.etl.utk_wms import WmsFeature

pytestmark = pytest.mark.skipif(
    os.environ.get("RAILSAFE_TEST_DB") != "1",
    reason="ustaw RAILSAFE_TEST_DB=1 i POSTGRES_* wskazujące na bazę *_test",
)

BBOX = Bbox(630000, 480000, 640000, 490000)
PLK = "PKP_Polskie_Linie_Kolejowe"


@pytest.fixture
def conn():
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.postgres_db.endswith("_test")
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    with psycopg.connect(**settings.database_connect_kwargs, autocommit=True) as connection:
        yield connection
    command.downgrade(cfg, "base")


def crossing(name, east, north, category="B", layer=PLK, approximate=False):
    feature = WmsFeature(layer, name, category, "szlakowy", "PKP PLK WARSZAWA")
    return ScannedCrossing(feature, east, north, approximate)


def osm_node(conn, node_id, east, north, **tags):
    lon, lat = conn.execute(
        "SELECT ST_X(g), ST_Y(g) FROM (SELECT ST_Transform("
        "ST_SetSRID(ST_MakePoint(%s, %s), 2180), 4326) AS g) t",
        (east, north),
    ).fetchone()
    return OsmCrossing(node_id, lon, lat, {"railway": "level_crossing", **tags})


def rows(conn, sql, *params):
    return conn.execute(sql, params).fetchall()


def scan_of(*crossings, unidentified=()):
    return ScanResult(crossings=list(crossings), unidentified=list(unidentified), coarse_tiles=1)


def test_import_verifies_only_crossings_confirmed_by_osm(conn):
    scan = scan_of(
        crossing("001 000 100", 631000, 481000, "B"),
        crossing("001 000 900", 635000, 485000, "D"),
    )
    osm = [
        osm_node(conn, 11, 631006, 481004, **{"crossing:barrier": "half", "crossing:light": "yes"}),
        osm_node(conn, 12, 638000, 488000),  # bez odpowiednika w rejestrze
    ]
    summary = import_crossings(conn, scan, osm, BBOX, wms_requests=7)
    assert (summary.written, summary.matched, summary.osm_points) == (2, 1, 2)

    status = dict(rows(conn, "SELECT name, verification_status FROM spatial.crossings"))
    assert status == {"001 000 100": "verified", "001 000 900": "unverified"}
    assert rows(conn, "SELECT DISTINCT ST_SRID(geom) FROM spatial.crossings") == [(2180,)]

    attrs = dict(
        rows(
            conn,
            "SELECT a.attribute_code, a.value_text FROM safety.crossing_attributes a "
            "JOIN spatial.crossings c USING (crossing_id) WHERE c.name = '001 000 100'",
        )
    )
    assert attrs["osm:crossing:barrier"] == "half"
    assert attrs["osm_node_id"] == "11"
    assert float(attrs["osm_distance_m"]) == pytest.approx(7.2, abs=0.3)
    assert attrs["manager"] == "PKP PLK WARSZAWA"

    flags = {r[0] for r in rows(conn, "SELECT code FROM system.quality_flags")}
    assert flags == {"no_osm_confirmation", "osm_without_official_match"}
    job = rows(conn, "SELECT status, records_written, params FROM system.import_jobs")[0]
    assert job[:2] == ("succeeded", 2)
    assert job[2]["wms_requests"] == 7


def test_category_is_normalised_and_unknown_becomes_null(conn):
    scan = scan_of(
        crossing("WK 1", 631000, 481000, "c"),
        crossing("WK 2", 632000, 481000, "?"),
        crossing("WK 3", 633000, 481000, ""),
    )
    import_crossings(conn, scan, None, BBOX)
    assert dict(rows(conn, "SELECT name, category FROM spatial.crossings")) == {
        "WK 1": "C",
        "WK 2": None,
        "WK 3": None,
    }
    flagged = rows(
        conn, "SELECT count(*) FROM system.quality_flags WHERE code = 'category_unrecognised'"
    )
    assert flagged == [(2,)]
    # Bez OSM nic nie jest weryfikowane i nie powstają flagi "brak potwierdzenia".
    assert rows(conn, "SELECT DISTINCT verification_status FROM spatial.crossings") == [
        ("unverified",)
    ]


def test_reimport_is_idempotent_and_keeps_manual_rejection(conn):
    scan = scan_of(
        crossing("001 000 100", 631000, 481000),
        crossing("001 000 200", 632000, 481000),
    )
    osm = [osm_node(conn, 11, 631000, 481000), osm_node(conn, 12, 632000, 481000)]
    import_crossings(conn, scan, osm, BBOX)
    conn.execute(
        "UPDATE spatial.crossings SET verification_status = 'rejected_grade_separated' "
        "WHERE name = '001 000 200'"
    )
    moved = scan_of(
        crossing("001 000 100", 631003, 481000, "A"),
        crossing("001 000 200", 632000, 481000),
    )
    import_crossings(conn, moved, osm, BBOX)

    result = {r[0]: r[1:] for r in rows(
        conn, "SELECT name, verification_status, category, ST_X(geom) FROM spatial.crossings"
    )}  # fmt: skip
    assert result == {
        "001 000 100": ("verified", "A", 631003.0),
        "001 000 200": ("rejected_grade_separated", "B", 632000.0),
    }
    assert rows(conn, "SELECT count(*) FROM system.import_jobs") == [(2,)]
    assert rows(conn, "SELECT count(*) FROM system.sources") == [(2,)]
    duplicates = rows(
        conn,
        "SELECT count(*) FROM (SELECT 1 FROM safety.crossing_attributes "
        "GROUP BY crossing_id, attribute_code, source_id HAVING count(*) > 1) t",
    )
    assert duplicates == [(0,)]


def test_each_osm_node_confirms_at_most_one_crossing(conn):
    scan = scan_of(
        crossing("001 000 100", 631000, 481000, "A"),
        crossing("001 000 110", 631020, 481000, "E"),
    )
    import_crossings(conn, scan, [osm_node(conn, 11, 631002, 481000)], BBOX)
    assert dict(rows(conn, "SELECT name, verification_status FROM spatial.crossings")) == {
        "001 000 100": "verified",
        "001 000 110": "unverified",
    }


def test_duplicate_number_across_managers_and_flags(conn):
    scan = scan_of(
        crossing("X1", 631000, 481000, layer=PLK),
        crossing("X1", 636000, 486000, layer="PGNiG_TERMIKA_SA", approximate=True),
        unidentified=[(634000.0, 484000.0)],
    )
    import_crossings(conn, scan, None, BBOX)
    assert rows(conn, "SELECT count(*), count(official_id) FROM spatial.crossings") == [(2, 0)]
    codes = dict(rows(conn, "SELECT code, count(*) FROM system.quality_flags GROUP BY 1"))
    assert codes == {
        "duplicate_official_id": 2,
        "position_approximate": 1,
        "wms_symbol_unidentified": 1,
    }


def test_type_mismatch_between_category_and_osm_is_flagged(conn):
    scan = scan_of(crossing("001 000 100", 631000, 481000, "E"))
    import_crossings(conn, scan, [osm_node(conn, 11, 631000, 481000)], BBOX)
    assert rows(conn, "SELECT code FROM system.quality_flags") == [("osm_type_mismatch",)]


def test_report_contains_counts_and_review_lists(conn):
    scan = scan_of(
        crossing("001 000 100", 631000, 481000, "B"),
        crossing("001 000 900", 635000, 485000, "D"),
    )
    osm = [
        osm_node(conn, 11, 631006, 481004, **{"crossing:barrier": "half"}),
        osm_node(conn, 12, 638000, 488000),
    ]
    summary = import_crossings(conn, scan, osm, BBOX)
    report = build_report(conn, scan, summary)
    assert "| PKP PLK WARSZAWA | 0 | 1 | 0 | 1 | 0 | 0 | 0 | 2 |" in report
    assert "| verified | 1 |" in report
    assert "mediana 7.2 m" in report
    assert "| osm:crossing:barrier | 1 |" in report
    assert "| 001 000 900 | D | 635000 | 485000 |" in report
    assert "| 12 |" in report

    no_osm = build_report(conn, scan, import_crossings(conn, scan, None, BBOX))
    assert "Dane OSM nie zostały pobrane" in no_osm
