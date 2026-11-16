"""Testy migracji na prawdziwym PostGIS (kryterium RSA-003: migracja i rollback).

Uruchamiane tylko, gdy RAILSAFE_TEST_DB=1, a POSTGRES_DB kończy się na "_test":
testy cofają migracje do zera, więc nie mogą trafić w bazę z danymi.
"""

import os

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from app.config import get_settings

pytestmark = pytest.mark.skipif(
    os.environ.get("RAILSAFE_TEST_DB") != "1",
    reason="ustaw RAILSAFE_TEST_DB=1 i POSTGRES_* wskazujące na bazę *_test",
)

SCHEMAS = ["analysis", "rail", "road", "safety", "spatial", "system"]
EXPECTED_TABLES = {
    "analysis": {"components", "risk_scores", "runs"},
    "rail": {"crossing_flow", "operation_events", "schedule_events"},
    "road": {"crossing_stations", "live_flow", "measurements", "stations"},
    "safety": {"crossing_attributes", "incidents"},
    "spatial": {
        "crossing_rail_segments",
        "crossing_road_segments",
        "crossings",
        "districts",
        "rail_segments",
        "road_segments",
    },
    "system": {"import_jobs", "licenses", "quality_flags", "sources"},
}
HEAD = "0010"


@pytest.fixture(scope="module")
def settings():
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.postgres_db.endswith("_test"), "testy migracji tylko na bazie *_test"
    return settings


@pytest.fixture(scope="module")
def alembic_cfg(settings):
    return Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))


@pytest.fixture
def conn(settings):
    with psycopg.connect(**settings.database_connect_kwargs, autocommit=True) as connection:
        yield connection


@pytest.fixture
def migrated(alembic_cfg):
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")
    yield
    command.downgrade(alembic_cfg, "base")


def _tables(conn) -> dict[str, set[str]]:
    rows = conn.execute(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_schema = ANY(%s)",
        (SCHEMAS,),
    ).fetchall()
    found: dict[str, set[str]] = {}
    for schema, table in rows:
        found.setdefault(schema, set()).add(table)
    return found


def _source(conn) -> int:
    return conn.execute(
        "INSERT INTO system.sources (code, name) VALUES ('test', 'Test') RETURNING source_id"
    ).fetchone()[0]


def _crossing(conn, source_id: int, object_id: str = "c1") -> int:
    return conn.execute(
        "INSERT INTO spatial.crossings (source_id, source_object_id, geom) "
        "VALUES (%s, %s, ST_SetSRID(ST_MakePoint(637000, 487000), 2180)) RETURNING crossing_id",
        (source_id, object_id),
    ).fetchone()[0]


def test_upgrade_creates_contract_tables(migrated, conn):
    assert _tables(conn) == EXPECTED_TABLES
    assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD


def test_all_geometries_use_epsg_2180(migrated, conn):
    srids = conn.execute(
        "SELECT DISTINCT srid FROM geometry_columns WHERE f_table_schema = ANY(%s)", (SCHEMAS,)
    ).fetchall()
    assert srids == [(2180,)]


def test_rollback_removes_everything_and_upgrade_works_again(alembic_cfg, conn):
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "base")
    assert _tables(conn) == {}
    assert conn.execute("SELECT count(*) FROM alembic_version").fetchone()[0] == 0
    command.upgrade(alembic_cfg, "head")
    assert _tables(conn) == EXPECTED_TABLES
    command.downgrade(alembic_cfg, "base")


def test_each_step_is_reversible(alembic_cfg, conn):
    command.downgrade(alembic_cfg, "base")
    for _ in range(int(HEAD)):
        command.upgrade(alembic_cfg, "+1")
        command.downgrade(alembic_cfg, "-1")
        command.upgrade(alembic_cfg, "+1")
    assert _tables(conn) == EXPECTED_TABLES
    command.downgrade(alembic_cfg, "base")


def test_crossing_rejects_wrong_srid_and_duplicates(migrated, conn):
    source_id = _source(conn)
    _crossing(conn, source_id)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _crossing(conn, source_id)
    with pytest.raises(psycopg.errors.InvalidParameterValue):
        conn.execute(
            "INSERT INTO spatial.crossings (source_id, source_object_id, geom) "
            "VALUES (%s, 'wgs', ST_SetSRID(ST_MakePoint(21.0, 52.2), 4326))",
            (source_id,),
        )


def test_verified_crossing_requires_verification_date(migrated, conn):
    crossing_id = _crossing(conn, _source(conn))
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "UPDATE spatial.crossings SET verification_status = 'verified' WHERE crossing_id = %s",
            (crossing_id,),
        )
    conn.execute(
        "UPDATE spatial.crossings SET verification_status = 'verified', verified_at = now() "
        "WHERE crossing_id = %s",
        (crossing_id,),
    )


def test_missing_road_count_is_null_not_zero(migrated, conn):
    source_id = _source(conn)
    insert = (
        "INSERT INTO road.measurements "
        "(source_id, station_id, period_start, period_end, vehicles_count) "
        "VALUES (%s, %s, '2026-11-01 00:00+01', '2026-11-02 00:00+01', %s)"
    )
    conn.execute(insert, (source_id, "s1", None))
    assert conn.execute("SELECT vehicles_count FROM road.measurements").fetchone()[0] is None
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(insert, (source_id, "s2", -5))


def test_unknown_component_has_no_value_and_no_rank(migrated, conn):
    crossing_id = _crossing(conn, _source(conn))
    run_id = conn.execute(
        "INSERT INTO analysis.runs (method_version, period_start, period_end) "
        "VALUES ('rps-0.1', '2026-11-01 00:00+01', '2026-11-02 00:00+01') RETURNING run_id"
    ).fetchone()[0]
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO analysis.risk_scores (run_id, crossing_id, rps, rank) "
            "VALUES (%s, %s, NULL, 1)",
            (run_id, crossing_id),
        )
    conn.execute(
        "INSERT INTO analysis.risk_scores (run_id, crossing_id) VALUES (%s, %s)",
        (run_id, crossing_id),
    )
    component = (
        "INSERT INTO analysis.components (run_id, crossing_id, component, value, weight, status) "
        "VALUES (%s, %s, %s, %s, 0.4, %s)"
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(component, (run_id, crossing_id, "T", 0, "unknown"))
    conn.execute(component, (run_id, crossing_id, "T", None, "unknown"))


def test_completed_run_requires_finish_time(migrated, conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO analysis.runs (status, method_version, period_start, period_end) "
            "VALUES ('completed', 'rps-0.1', '2026-11-01 00:00+01', '2026-11-02 00:00+01')"
        )
