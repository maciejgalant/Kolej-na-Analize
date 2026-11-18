"""Przebieg WPO na PostGIS: dane wejściowe z geometrii, zapis i raport."""

import os

import pytest

from app.analysis import rps
from app.analysis.run import build_run_report, load_inputs, run_analysis
from app.etl.gtfs import merge_feeds, read_feed
from app.etl.train_flow import import_train_flow
from tests.test_topology_import import conn, run_import  # noqa: F401  (fixture)
from tests.test_train_flow import SERVICES, WEEK, WORLD, gtfs_zip, lonlat

pytestmark = pytest.mark.skipif(
    os.environ.get("RAILSAFE_TEST_DB") != "1",
    reason="ustaw RAILSAFE_TEST_DB=1 i POSTGRES_* wskazujące na bazę *_test",
)


def prepare(conn):  # noqa: F811
    """Topologia testowa + rozkład: 3 kursy/dzień roboczy po torze r-main i 2 po r-old."""
    run_import(conn)
    shapes = {
        "MAIN": [lonlat(conn, 630000, 480500), lonlat(conn, 632000, 480500)],
        "OLD": [lonlat(conn, 631600, 480900), lonlat(conn, 631990, 480900)],
    }
    trips = [("RAIL", "A", "MAIN")] * 3 + [("RAIL", "A", "OLD")] * 2
    feed = merge_feeds({"PL": read_feed(gtfs_zip(shapes, trips, SERVICES), *WORLD)})
    import_train_flow(conn, feed, WEEK)


def by_name(conn, inputs):  # noqa: F811
    names = dict(conn.execute("SELECT crossing_id, name FROM spatial.crossings").fetchall())
    return {names[item.crossing_id]: item for item in inputs}


def test_inputs_cover_verified_road_crossings_with_geometry(conn):  # noqa: F811
    prepare(conn)
    inputs = by_name(conn, load_inputs(conn))
    # poza zakresem: przejście piesze (E), niezweryfikowane (no-road, bridge), spoza miasta
    assert set(inputs) == {"ok", "old-track"}
    ok = inputs["ok"]
    assert ok.category == "B"
    assert ok.trains_weekday == pytest.approx(3.0)
    assert ok.road_class == "droga lokalna"
    assert ok.tracks == 2  # jeden odcinek BDOT10k z liczbaTorow = 2
    assert ok.angle_deg == pytest.approx(90.0, abs=0.5)  # tor W–E, droga N–S
    assert inputs["old-track"].trains_weekday == pytest.approx(2.0)


def test_angle_and_track_count_follow_geometry(conn):  # noqa: F811
    prepare(conn)
    # Drugi tor 8 m obok i droga pod kątem 45° przez przejazd "ok".
    conn.execute(
        "INSERT INTO spatial.rail_segments (source_id, source_object_id, level_position, "
        "track_count, geom) SELECT source_id, 'r-second', level_position, 1, "
        "ST_Translate(geom, 0, 8) FROM spatial.rail_segments WHERE source_object_id = 'r-main'"
    )
    conn.execute(
        "UPDATE spatial.road_segments SET geom = ST_SetSRID(ST_MakeLine("
        "ST_MakePoint(630400, 480402), ST_MakePoint(630600, 480602)), 2180) "
        "WHERE source_object_id = 'd-1'"
    )
    ok = by_name(conn, load_inputs(conn))["ok"]
    assert ok.tracks == 3
    assert ok.angle_deg == pytest.approx(45.0, abs=0.5)


def test_run_writes_scores_components_and_metadata(conn):  # noqa: F811
    prepare(conn)
    summary = run_analysis(conn)
    assert (summary.scored, summary.ranked) == (2, 2)
    assert summary.period == ("2026-11-16", "2026-11-22")  # dni lokalne, nie UTC
    run = conn.execute(
        "SELECT status, method_version, parameters, input_snapshot, finished_at IS NOT NULL, "
        "period_start AT TIME ZONE 'Europe/Warsaw' FROM analysis.runs"
    ).fetchone()
    assert run[:2] == ("completed", rps.METHOD_VERSION)
    assert run[2]["weights"] == rps.WEIGHTS
    assert run[3] == {
        "crossings": 2,
        "with_road_measurement": 0,
        "flow_methods": ["gtfs-shape-2"],
    }
    assert run[4] and str(run[5]) == "2026-11-16 00:00:00"

    rows = conn.execute(
        "SELECT c.name, s.rank, s.rps, s.is_partial, s.completeness_pct, s.quality_status, "
        "s.rank_best, s.rank_worst FROM analysis.risk_scores s "
        "JOIN spatial.crossings c USING (crossing_id) ORDER BY s.rank"
    ).fetchall()
    # old-track: kategoria D (bez urządzeń) wyprzedza "ok" z kategorią B mimo mniejszego ruchu
    assert [(r[0], r[1]) for r in rows] == [("old-track", 1), ("ok", 2)]
    assert all(r[3] and float(r[4]) == 90.0 and r[5] == "modelled" for r in rows)
    assert all(r[6] <= r[1] <= r[7] for r in rows)

    components = conn.execute(
        "SELECT k.component, k.value, k.weight, k.status, k.detail FROM analysis.components k "
        "JOIN spatial.crossings c USING (crossing_id) WHERE c.name = 'ok' ORDER BY 1"
    ).fetchall()
    assert [c[0] for c in components] == ["G", "H", "P", "T"]
    g, h, p, t = components
    assert (float(g[1]), g[3]) == (24.0, "modelled")
    assert (h[1], h[3]) == (None, "unknown")
    assert (float(p[1]), p[3], float(p[2])) == (30.0, "ok", 0.3)
    assert t[3] == "modelled" and t[4]["vehicles_per_day_model"] == 2500
    assert t[4]["exposure_product"] == 7500


def test_crossing_without_passenger_trains_has_no_rank(conn):  # noqa: F811
    prepare(conn)
    conn.execute(
        "UPDATE rail.crossing_flow SET train_count = 0 WHERE crossing_id = "
        "(SELECT crossing_id FROM spatial.crossings WHERE name = 'old-track')"
    )
    summary = run_analysis(conn)
    assert (summary.scored, summary.ranked) == (2, 1)
    row = conn.execute(
        "SELECT s.rps, s.rank, s.quality_status, s.completeness_pct FROM analysis.risk_scores s "
        "JOIN spatial.crossings c USING (crossing_id) WHERE c.name = 'old-track'"
    ).fetchone()
    assert row[:3] == (None, None, "partial") and float(row[3]) == 50.0
    report = build_run_report(conn, summary)
    assert "## Bez pozycji w rankingu" in report
    assert "| old-track | D | Bemowo | 100.0 |" in report
    assert "ruch towarowy i manewrowy nieznany" in report
    assert "| 1 | ok | B | Alfa |" in report


def test_each_run_is_kept_and_requires_train_data(conn):  # noqa: F811
    run_import(conn)
    with pytest.raises(RuntimeError, match="import-schedule"):
        run_analysis(conn)
    assert conn.execute("SELECT count(*) FROM analysis.runs").fetchone()[0] == 0
    prepare_only_flow(conn)
    first, second = run_analysis(conn), run_analysis(conn)
    assert second.run_id > first.run_id
    assert conn.execute("SELECT count(*) FROM analysis.runs").fetchone()[0] == 2


def prepare_only_flow(conn):  # noqa: F811
    shapes = {"MAIN": [lonlat(conn, 630000, 480500), lonlat(conn, 632000, 480500)]}
    feed = merge_feeds(
        {"PL": read_feed(gtfs_zip(shapes, [("RAIL", "A", "MAIN")], SERVICES), *WORLD)}
    )
    import_train_flow(conn, feed, WEEK)


def test_api_exposes_latest_run_ranking_and_components(conn):  # noqa: F811
    from fastapi.testclient import TestClient

    from app.main import app

    prepare(conn)
    client = TestClient(app)
    assert client.get("/api/v1/analysis/latest").status_code == 404
    listing = client.get("/api/v1/crossings").json()
    assert all(f["properties"]["rank"] is None for f in listing["features"])
    ok_id = next(f["id"] for f in listing["features"] if f["properties"]["name"] == "ok")
    assert client.get(f"/api/v1/crossings/{ok_id}").json()["priority"] is None

    run_analysis(conn)
    summary = run_analysis(conn)  # API ma pokazywać ostatni przebieg
    meta = client.get("/api/v1/analysis/latest").json()
    assert meta["run_id"] == summary.run_id
    assert (meta["scored"], meta["ranked"]) == (2, 2)
    assert (meta["period_start"], meta["period_end"]) == ("2026-11-16", "2026-11-22")
    assert meta["weights"] == rps.WEIGHTS
    assert "nie prognoza" in meta["disclaimer"]

    ranks = {
        f["properties"]["name"]: (f["properties"]["rank"], f["properties"]["rps"])
        for f in client.get("/api/v1/crossings").json()["features"]
    }
    assert ranks["old-track"][0] == 1 and ranks["ok"][0] == 2
    assert ranks["boundary-ped"] == (None, None)  # przejście piesze poza rankingiem
    assert ranks["old-track"][1] > ranks["ok"][1]

    priority = client.get(f"/api/v1/crossings/{ok_id}").json()["priority"]
    assert priority["run_id"] == summary.run_id
    assert (priority["rank"], priority["ranked_total"]) == (2, 2)
    assert priority["completeness_pct"] == 90.0
    assert [c["component"] for c in priority["components"]] == ["T", "P", "G", "H"]
    assert priority["components"][3] == {
        "component": "H", "value": None, "weight": 0.1, "status": "unknown",
        "detail": {"reason": "brak danych o zdarzeniach"},
    }  # fmt: skip


def test_road_between_15_and_30_m_gives_class_but_no_angle(conn):  # noqa: F811
    prepare(conn)
    # Jezdnia odsunięta o 20 m: nadal w promieniu potwierdzenia drogi (30 m), poza 15 m.
    conn.execute(
        "UPDATE spatial.road_segments r SET geom = ST_Translate(r.geom, 20, 0) "
        "FROM spatial.crossings c WHERE c.name = 'ok' AND ST_DWithin(r.geom, c.geom, 15)"
    )
    ok = by_name(conn, load_inputs(conn))["ok"]
    assert ok.road_class == "droga lokalna"
    assert ok.road_distance_m == pytest.approx(20.0, abs=0.5)
    assert ok.angle_deg is None
    detail = rps.exposure_component(ok.trains_weekday, ok.road_class, ok.road_distance_m).detail
    assert "rozszerzonego promienia" in detail["note"]


def test_parallel_road_beyond_15_m_is_not_taken(conn):  # noqa: F811
    prepare(conn)
    # Zamiast ulicy przejazdu zostaje tylko ulica równoległa do toru, 20 m od punktu.
    conn.execute(
        "UPDATE spatial.road_segments r SET geom = ST_Translate(rail.geom, 0, 20) "
        "FROM spatial.crossings c, spatial.rail_segments rail "
        "WHERE c.name = 'ok' AND rail.source_object_id = 'r-main' "
        "AND ST_DWithin(r.geom, c.geom, 15)"
    )
    ok = by_name(conn, load_inputs(conn))["ok"]
    assert ok.road_class is None and ok.road_distance_m is None and ok.angle_deg is None
