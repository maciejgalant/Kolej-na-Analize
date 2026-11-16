"""Rozkład GTFS → planowa liczba pociągów na przejazd."""

import io
import os
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.etl.gtfs import merge_feeds, read_feed, reference_week, trips_on
from app.etl.train_flow import build_flow_report, import_train_flow
from app.main import app
from tests.test_topology_import import conn, run_import  # noqa: F401  (fixture)

DB = pytest.mark.skipif(
    os.environ.get("RAILSAFE_TEST_DB") != "1",
    reason="ustaw RAILSAFE_TEST_DB=1 i POSTGRES_* wskazujące na bazę *_test",
)
WEEK = [date(2026, 11, 16 + i) for i in range(7)]  # pon.–niedz.
WORKDAYS = [d.strftime("%Y%m%d") for d in WEEK[:5]]
SATURDAY = WEEK[5].strftime("%Y%m%d")


def gtfs_zip(
    shapes: dict[str, list[tuple[float, float]]],
    trips: list[tuple[str, str, str]],
    services: dict[str, list[str]],
    extra: dict[str, str] | None = None,
) -> zipfile.ZipFile:
    """shapes: id -> [(lon, lat)], trips: (route_id, service_id, shape_id)."""
    files = {
        "feed_info.txt": "feed_publisher_name,feed_version,feed_start_date,feed_end_date\r\n"
                         "T,2026-11-11T02:46:31,20261111,20261211\r\n",
        "routes.txt": "route_id,route_type\r\nRAIL,2\r\nBUS,3\r\n",
        "trips.txt": "trip_id,route_id,service_id,shape_id\r\n"
        + "".join(f"t{i},{r},{s},{sh}\r\n" for i, (r, s, sh) in enumerate(trips)),
        "shapes.txt": "shape_id,shape_pt_sequence,shape_pt_lat,shape_pt_lon\r\n"
        + "".join(
            f"{sid},{seq},{lat},{lon}\r\n"
            for sid, line in shapes.items()
            # celowo w odwrotnej kolejności: import musi sortować po shape_pt_sequence
            for seq, (lon, lat) in reversed(list(enumerate(line)))
        ),
        "calendar_dates.txt": "date,service_id,exception_type\r\n"
        + "".join(f"{d},{sid},1\r\n" for sid, days in services.items() for d in days)
        + f"{WORKDAYS[0]},REMOVED,2\r\n",
    } | (extra or {})  # fmt: skip
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, "﻿" + content if name == "trips.txt" else content)
    return zipfile.ZipFile(buffer)


WORLD = (-180.0, -90.0, 180.0, 90.0)
SIMPLE_SHAPES = {"S1": [(21.0, 52.2), (21.1, 52.2)], "FAR": [(15.0, 50.0), (15.1, 50.0)]}
SIMPLE_TRIPS = [("RAIL", "A", "S1"), ("RAIL", "A", "S1"), ("RAIL", "B", "S1"),
                ("BUS", "A", "S1"), ("RAIL", "A", "FAR"), ("RAIL", "A", "")]  # fmt: skip
SERVICES = {"A": WORKDAYS, "B": [SATURDAY]}


def test_read_feed_filters_rail_trips_and_area():
    feed = read_feed(gtfs_zip(SIMPLE_SHAPES, SIMPLE_TRIPS, SERVICES), 20.8, 52.0, 21.3, 52.4)
    assert (feed.start, feed.end) == (date(2026, 11, 11), date(2026, 12, 11))
    assert list(feed.shapes) == ["S1"]  # FAR poza obszarem
    assert feed.shapes["S1"] == [(21.0, 52.2), (21.1, 52.2)]  # posortowane po sekwencji
    assert feed.trips_by_shape["S1"] == ["A", "A", "B"]  # bez autobusu
    assert feed.rail_trips == 4  # trzy na S1 i jeden na FAR; kurs bez trasy pominięty
    assert trips_on(feed, ["S1"], WEEK[0]) == 2
    assert trips_on(feed, ["S1"], WEEK[5]) == 1
    assert trips_on(feed, ["S1"], WEEK[6]) == 0
    assert trips_on(feed, ["BRAK"], WEEK[0]) == 0


def test_read_feed_rejects_unsupported_calendar_and_missing_files():
    with_calendar = gtfs_zip(SIMPLE_SHAPES, SIMPLE_TRIPS, SERVICES,
                             {"calendar.txt": "service_id,monday\r\nA,1\r\n"})  # fmt: skip
    with pytest.raises(RuntimeError, match="calendar.txt"):
        read_feed(with_calendar, *WORLD)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("routes.txt", "route_id,route_type\r\n")
    with pytest.raises(RuntimeError, match="brakuje"):
        read_feed(zipfile.ZipFile(buffer), *WORLD)


def test_reference_week_is_next_full_monday_to_sunday_within_feed():
    feed = read_feed(gtfs_zip(SIMPLE_SHAPES, SIMPLE_TRIPS, SERVICES), *WORLD)
    assert reference_week(feed, date(2026, 11, 11)) == WEEK  # środa → najbliższy poniedziałek
    assert reference_week(feed, date(2026, 11, 16))[0] == date(2026, 11, 16)
    assert reference_week(feed, date(2026, 1, 1))[0] == date(2026, 11, 16)
    with pytest.raises(RuntimeError, match="pełnego tygodnia"):
        reference_week(feed, date(2026, 12, 8))


def lonlat(conn, east, north):  # noqa: F811
    return conn.execute(
        "SELECT ST_X(g), ST_Y(g) FROM (SELECT ST_Transform(ST_SetSRID("
        "ST_MakePoint(%s, %s), 2180), 4326) AS g) t",
        (east, north),
    ).fetchone()


def city_feed(conn, parallel: bool):  # noqa: F811
    shapes = {"MAIN": [lonlat(conn, 630000, 480500), lonlat(conn, 632000, 480500)]}
    trips = [("RAIL", "A", "MAIN")] * 3 + [("RAIL", "B", "MAIN")]
    if parallel:  # linia równoległa 30 m obok: poza progiem 20 m, w progu 50 m
        shapes["PAR"] = [lonlat(conn, 630000, 480530), lonlat(conn, 632000, 480530)]
        trips += [("RAIL", "A", "PAR")] * 2
    return merge_feeds({"PL": read_feed(gtfs_zip(shapes, trips, SERVICES), *WORLD)})


def flows(conn) -> dict[str, list[int]]:  # noqa: F811
    rows = conn.execute(
        "SELECT c.name, f.train_count FROM rail.crossing_flow f "
        "JOIN spatial.crossings c USING (crossing_id) ORDER BY c.name, f.period_start"
    ).fetchall()
    out: dict[str, list[int]] = {}
    for name, count in rows:
        out.setdefault(name, []).append(count)
    return out


@DB
def test_flow_counts_trips_per_service_day(conn):  # noqa: F811
    run_import(conn)
    summary = import_train_flow(conn, city_feed(conn, parallel=False), WEEK)
    assert flows(conn) == {
        "ok": [3, 3, 3, 3, 3, 1, 0],
        "boundary-ped": [3, 3, 3, 3, 3, 1, 0],
        "no-road": [3, 3, 3, 3, 3, 1, 0],
        "bridge": [0] * 7,  # trasa 200 m obok: zero kursów pasażerskich, nie NULL
        "old-track": [0] * 7,
    }  # obiekt spoza Warszawy nie dostaje wierszy
    assert (summary.crossings, summary.with_trains, summary.sensitive) == (5, 3, 0)
    row = conn.execute(
        "SELECT unit, evidence_type, method_version, "
        "period_start AT TIME ZONE 'Europe/Warsaw', period_end - period_start "
        "FROM rail.crossing_flow ORDER BY period_start LIMIT 1"
    ).fetchone()
    assert row[:3] == ("passenger_trains/day", "planned", "gtfs-shape-2")
    assert str(row[3]) == "2026-11-16 00:00:00" and str(row[4]) == "1 day, 0:00:00"


@DB
def test_parallel_line_is_not_counted_but_flags_sensitivity(conn):  # noqa: F811
    run_import(conn)
    summary = import_train_flow(conn, city_feed(conn, parallel=True), WEEK)
    assert flows(conn)["ok"] == [3, 3, 3, 3, 3, 1, 0]
    assert summary.sensitive == 3
    flagged = conn.execute(
        "SELECT count(*) FROM system.quality_flags WHERE code = 'train_count_sensitive'"
    ).fetchone()[0]
    assert flagged == 3


@DB
def test_reimport_replaces_week_without_duplicates(conn):  # noqa: F811
    run_import(conn)
    import_train_flow(conn, city_feed(conn, parallel=True), WEEK)
    import_train_flow(conn, city_feed(conn, parallel=False), WEEK)
    assert conn.execute("SELECT count(*) FROM rail.crossing_flow").fetchone()[0] == 35
    assert (
        conn.execute(
            "SELECT count(*) FROM system.quality_flags WHERE code = 'train_count_sensitive'"
        ).fetchone()[0]
        == 0
    )


@DB
def test_report_and_api_expose_planned_flow(conn):  # noqa: F811
    run_import(conn)
    feed = city_feed(conn, parallel=False)
    report = build_flow_report(conn, feed, import_train_flow(conn, feed, WEEK))
    assert "z co najmniej jednym kursem pasażerskim w tygodniu: **3**" in report
    assert "| ok | B | Alfa | 3 | 1 | 0 | 2.0 |  |" in report
    assert "| bridge | D | Bemowo | 0 | 0 | 0 | — |  |" in report

    client = TestClient(app)
    listing = client.get("/api/v1/crossings", params={"verification_status": "all"}).json()
    weekday = {f["properties"]["name"]: f["properties"]["trains_weekday"]
               for f in listing["features"]}  # fmt: skip
    assert weekday == {"ok": 3, "boundary-ped": 3, "no-road": 3, "bridge": 0, "old-track": 0}
    ok_id = next(f["id"] for f in listing["features"] if f["properties"]["name"] == "ok")
    flow = client.get(f"/api/v1/crossings/{ok_id}").json()["rail_flow"]
    assert flow == {
        "weekday_avg": 3.0, "saturday": 1, "sunday": 0,
        "period_start": "2026-11-16", "period_end": "2026-11-22",
        "unit": "passenger_trains/day", "evidence_type": "planned",
        "method_version": "gtfs-shape-2",
        "source": "Polish Trains GTFS - rozkład pociągów pasażerskich",
        # zbiór bez godzin przystanków: brak profilu dobowego (RSA-018)
        "hourly_weekday": None, "max_per_hour": None, "max_hour": None,
        "in_road_peaks": None, "road_peak_hours": None, "road_peak_source": None,
        "at_night": None,
    }  # fmt: skip


@DB
def test_api_flow_is_null_before_schedule_import(conn):  # noqa: F811
    run_import(conn)
    client = TestClient(app)
    listing = client.get("/api/v1/crossings").json()
    assert listing["features"][0]["properties"]["trains_weekday"] is None
    assert (
        client.get(f"/api/v1/crossings/{listing['features'][0]['id']}").json()["rail_flow"] is None
    )


def test_feed_without_date_range_uses_calendar_extent():
    archive = gtfs_zip(
        SIMPLE_SHAPES, SIMPLE_TRIPS, SERVICES,
        {"feed_info.txt": "feed_publisher_name,feed_version\r\nT,2026-08-22T09:08:14\r\n"},
    )  # fmt: skip
    feed = read_feed(archive, *WORLD)
    assert (feed.start, feed.end) == (WEEK[0], WEEK[5])


def test_merge_feeds_prefixes_ids_and_intersects_date_ranges():
    main = read_feed(gtfs_zip(SIMPLE_SHAPES, SIMPLE_TRIPS, SERVICES), *WORLD)
    wkd = read_feed(
        gtfs_zip({"S1": [(20.9, 52.2), (20.95, 52.2)]}, [("RAIL", "A", "S1")] * 5,
                 {"A": [SATURDAY]},
                 {"feed_info.txt": "feed_publisher_name,feed_version\r\nT,v2\r\n"}),
        *WORLD,
    )  # fmt: skip
    merged = merge_feeds({"PL": main, "WKD": wkd})
    assert set(merged.shapes) == {"PL:S1", "PL:FAR", "WKD:S1"}  # ten sam shape_id nie koliduje
    assert trips_on(merged, ["PL:S1"], WEEK[0]) == 2
    assert trips_on(merged, ["WKD:S1"], WEEK[0]) == 0
    assert trips_on(merged, ["WKD:S1", "PL:S1"], WEEK[5]) == 6
    assert (merged.start, merged.end) == (WEEK[5], WEEK[5])  # część wspólna zakresów
    assert merged.rail_trips == main.rail_trips + 5
    with pytest.raises(RuntimeError, match="pełnego tygodnia"):
        reference_week(merged, date(2026, 11, 11))


@DB
def test_report_lists_threshold_counts_for_sensitive_crossings(conn):  # noqa: F811
    run_import(conn)
    feed = city_feed(conn, parallel=True)
    report = build_flow_report(conn, feed, import_train_flow(conn, feed, WEEK))
    assert "## Przejazdy z niejednoznacznym dopasowaniem" in report
    assert "| ok | 16 | 16 | 26 | 16 | 2.0 | możliwa linia równoległa |" in report


def two_manager_feed(conn):  # noqa: F811
    """Linia PLK na osi toru i linia WKD 27 m obok (jak przy ul. Mszczonowskiej)."""
    plk = read_feed(
        gtfs_zip({"MAIN": [lonlat(conn, 630000, 480500), lonlat(conn, 632000, 480500)]},
                 [("RAIL", "A", "MAIN")] * 3, SERVICES),
        *WORLD,
    )  # fmt: skip
    wkd = read_feed(
        gtfs_zip({"0": [lonlat(conn, 630000, 480530), lonlat(conn, 632000, 480530)]},
                 [("RAIL", "A", "0")] * 2, SERVICES),
        *WORLD,
    )  # fmt: skip
    return merge_feeds({"PL": plk, "WKD": wkd})


@DB
def test_each_manager_is_counted_from_its_own_timetable(conn):  # noqa: F811
    run_import(conn)
    conn.execute(
        "UPDATE spatial.crossings SET source_object_id = 'Warszawska_Kolej_Dojazdowa:WK 1' "
        "WHERE name = 'no-road'"
    )
    conn.execute(
        "UPDATE spatial.crossings SET source_object_id = 'PGNiG_TERMIKA_SA:BK1' "
        "WHERE name = 'boundary-ped'"
    )
    summary = import_train_flow(conn, two_manager_feed(conn), WEEK)
    result = flows(conn)
    assert result["ok"] == [3, 3, 3, 3, 3, 0, 0]  # obiekt PLK: bez kursów WKD z 27 m
    assert result["no-road"] == [2, 2, 2, 2, 2, 0, 0]  # obiekt WKD: tylko WKD, próg 50 m
    assert result["boundary-ped"] == [0] * 7  # bocznica: żaden rozkład pasażerski
    assert (summary.extended, summary.sensitive) == (1, 0)
    flagged = conn.execute(
        "SELECT c.name, f.code, f.severity FROM system.quality_flags f "
        "JOIN spatial.crossings c ON c.crossing_id::text = f.entity_id "
        "WHERE f.code LIKE 'train_count%'"
    ).fetchall()
    assert flagged == [("no-road", "train_count_extended", "info")]


@DB
@pytest.mark.parametrize(
    ("number", "expected", "extended"),
    [
        ("007 000 500", [2, 2, 2, 2, 2, 0, 0], True),  # numer: linia 7, punkt na torach linii 9
        ("009 000 500", [0] * 7, False),  # punkt na własnej linii: zero zostaje, z flagą
    ],
)
def test_threshold_is_extended_only_when_point_lies_on_another_line(
    conn,  # noqa: F811
    number,
    expected,
    extended,
):
    run_import(conn)
    conn.execute("UPDATE spatial.crossings SET name = %s WHERE name = 'ok'", (number,))
    feed = merge_feeds(
        {"PL": read_feed(
            gtfs_zip({"PAR": [lonlat(conn, 630000, 480530), lonlat(conn, 632000, 480530)]},
                     [("RAIL", "A", "PAR")] * 2, SERVICES),
            *WORLD,
        )}
    )  # fmt: skip
    summary = import_train_flow(conn, feed, WEEK)
    assert flows(conn)[number] == expected
    codes = {
        row[0]
        for row in conn.execute(
            "SELECT f.code FROM system.quality_flags f JOIN spatial.crossings c "
            "ON c.crossing_id::text = f.entity_id WHERE c.name = %s AND f.code LIKE 'train%%'",
            (number,),
        )
    }
    assert codes == ({"train_count_extended"} if extended else {"train_count_sensitive"})
    assert summary.extended == (1 if extended else 0)
