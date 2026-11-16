"""Godzina przejazdu pociągu przez przejazd i profil dobowy (RSA-018)."""

import os
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.etl.gtfs import Feed, _seconds, merge_feeds, read_feed
from app.etl.train_flow import build_flow_report, import_train_flow
from app.etl.train_times import ShapeIndex, _project, hourly_profile, profile_stats
from app.main import app
from tests.test_topology_import import conn, run_import  # noqa: F401  (fixture)
from tests.test_train_flow import SERVICES, WEEK, WORLD, gtfs_zip, lonlat

DB = pytest.mark.skipif(
    os.environ.get("RAILSAFE_TEST_DB") != "1",
    reason="ustaw RAILSAFE_TEST_DB=1 i POSTGRES_* wskazujące na bazę *_test",
)
LINE = [(21.0, 52.2), (21.1, 52.2)]  # ok. 6,8 km z zachodu na wschód
SUNDAY_BEFORE = date(2026, 11, 15)  # dzień przed pierwszym dniem tygodnia WEEK


def feed_with(trips: dict[str, list[tuple[str, int, int]]], services: dict[str, str]) -> Feed:
    """Jedna trasa LINE, przystanki W (początek), M (środek), E (koniec)."""
    feed = Feed(version="t", start=WEEK[0], end=WEEK[-1])
    feed.shapes["S"] = LINE
    feed.stops = {"W": (21.0, 52.2), "M": (21.05, 52.2), "E": (21.1, 52.2)}
    feed.trips["S"] = [(trip, services[trip]) for trip in trips]
    feed.trips_by_shape["S"] = [services[trip] for trip in trips]
    feed.stop_times = trips
    feed.service_dates = {"WD": set(WEEK[:5]), "SUN": {SUNDAY_BEFORE}}
    return feed


def test_gtfs_times_beyond_midnight_are_kept():
    assert _seconds("07:30:15") == 27015
    assert _seconds("25:10:00") == 90600
    assert _seconds("") is None and _seconds(None) is None


def test_point_is_projected_along_the_route():
    along, off = _project(LINE, (21.025, 52.2005))
    assert along == pytest.approx(0.25 * 6820, rel=0.01)
    assert off == pytest.approx(55, abs=3)


def test_passage_time_is_interpolated_between_stops():
    # odjazd z W 8:00, przyjazd do M 8:10; przejazd w 1/4 drogi W–E, czyli w połowie W–M
    feed = feed_with({"T": [("W", 28800, 28800), ("M", 29400, 29460), ("E", 30000, 30000)]},
                     {"T": "WD"})  # fmt: skip
    index = ShapeIndex.build(feed, "S", (21.025, 52.2))
    assert index.passage("T") == pytest.approx(29100, abs=10)  # ok. 8:05
    # kurs w przeciwnym kierunku (E → W) też mija przejazd
    feed.stop_times["R"] = [("E", 36000, 36000), ("M", 36600, 36600), ("W", 37200, 37200)]
    assert index.passage("R") == pytest.approx(36900, abs=10)  # ok. 10:15
    # kurs, który kończy bieg przed przejazdem, go nie mija
    feed.stop_times["SHORT"] = [("M", 40000, 40000), ("E", 40600, 40600)]
    assert index.passage("SHORT") is None


def test_profile_counts_trips_per_calendar_hour_including_after_midnight():
    trips = {
        "MORNING": [("W", 28800, 28800), ("E", 30000, 30000)],  # przejazd 8:05
        "EVENING": [("W", 61200, 61200), ("E", 62400, 62400)],  # 17:05
        "NIGHT": [("W", 88200, 88200), ("E", 89400, 89400)],  # 24:35 → 0:35 dnia następnego
        "NOTIMES": [],
    }
    services = {"MORNING": "WD", "EVENING": "WD", "NIGHT": "SUN", "NOTIMES": "WD"}
    feed = feed_with(trips, services)
    monday, profile_unplaced = hourly_profile(feed, ["S"], (21.025, 52.2), WEEK[0])
    assert monday[8] == 1 and monday[17] == 1 and monday[0] == 1  # nocny kurs z niedzieli
    assert sum(monday) == 3 and profile_unplaced == 1  # kurs bez godzin
    sunday, _ = hourly_profile(feed, ["S"], (21.025, 52.2), SUNDAY_BEFORE)
    assert sum(sunday) == 0  # kurs niedzielny mija przejazd już w poniedziałek


def test_profile_stats_use_given_road_peaks():
    profile = [0.0] * 24
    profile[7], profile[8], profile[12], profile[23] = 4, 6, 2, 1
    stats = profile_stats(profile)
    assert (stats["max_per_hour"], stats["max_hour"]) == (6, 8)
    assert stats["in_road_peaks"] == 10 and stats["at_night"] == 1 and stats["total"] == 13
    assert profile_stats(profile, (12,))["in_road_peaks"] == 2


def timed_zip(conn, shapes, trips, times, stops):  # noqa: F811
    stop_rows = "".join(f"{sid},{lat},{lon}\r\n" for sid, (lon, lat) in stops.items())
    time_rows = "".join(
        f"t{i},{seq},{stop},{arr},{dep}\r\n"
        for i, rows in enumerate(times)
        for seq, (stop, arr, dep) in enumerate(rows)
    )
    return gtfs_zip(
        shapes,
        trips,
        SERVICES,
        {"stops.txt": "stop_id,stop_lat,stop_lon\r\n" + stop_rows,
         "stop_times.txt": "trip_id,stop_sequence,stop_id,arrival_time,departure_time\r\n"
         + time_rows},
    )  # fmt: skip


def test_read_feed_keeps_times_only_for_trips_in_area():
    shapes = {"S1": LINE, "FAR": [(15.0, 50.0), (15.1, 50.0)]}
    trips = [("RAIL", "A", "S1"), ("RAIL", "A", "FAR")]
    times = [[("W", "08:00:00", "08:00:00"), ("E", "08:20:00", "08:20:00")],
             [("X", "09:00:00", "09:00:00"), ("Y", "09:30:00", "")]]  # fmt: skip
    stops = {"W": LINE[0], "E": LINE[1], "X": (15.0, 50.0), "Y": (15.1, 50.0)}
    feed = read_feed(timed_zip(None, shapes, trips, times, stops), 20.8, 52.0, 21.3, 52.4)
    assert feed.trips == {"S1": [("t0", "A")]}
    assert feed.stop_times == {"t0": [("W", 28800, 28800), ("E", 30000, 30000)]}
    assert set(feed.stops) == {"W", "E"}  # przystanki kursu spoza obszaru pominięte
    merged = merge_feeds({"PL": feed})
    assert merged.trips["PL:S1"] == [("PL:t0", "PL:A")]
    assert merged.stop_times["PL:t0"][0] == ("PL:W", 28800, 28800)
    assert "PL:W" in merged.stops


@DB
def test_import_stores_profile_and_api_exposes_it(conn):  # noqa: F811
    run_import(conn)
    west, east = lonlat(conn, 630000, 480500), lonlat(conn, 632000, 480500)
    shapes = {"MAIN": [west, east]}
    trips = [("RAIL", "A", "MAIN")] * 3 + [("RAIL", "B", "MAIN")]
    departures = ["07:10:00", "07:40:00", "16:15:00", "11:00:00"]
    times = [[("W", d, d), ("E", d[:3] + "55:00", d[:3] + "55:00")] for d in departures]
    stops = {"W": west, "E": east}
    feed = merge_feeds({"PL": read_feed(timed_zip(conn, shapes, trips, times, stops), *WORLD)})
    summary = import_train_flow(conn, feed, WEEK)
    assert summary.unplaced == 0
    report = build_flow_report(conn, feed, summary)
    assert "## Rozkład w ciągu doby (RSA-018)" in report
    assert "| ok | 3 | 2 (7:00) | 3 | 100% | 0 |" in report

    crossing_id, profile, count = conn.execute(
        "SELECT f.crossing_id, f.hourly_profile, f.train_count FROM rail.crossing_flow f "
        "JOIN spatial.crossings c USING (crossing_id) WHERE c.name = 'ok' "
        "ORDER BY f.period_start LIMIT 1"
    ).fetchone()
    assert count == 3 and sum(profile) == 3
    assert profile[7] == 2 and profile[16] == 1

    flow = TestClient(app).get(f"/api/v1/crossings/{crossing_id}").json()["rail_flow"]
    assert flow["hourly_weekday"][7] == 2.0 and len(flow["hourly_weekday"]) == 24
    assert (flow["max_per_hour"], flow["max_hour"]) == (2.0, 7)
    assert flow["in_road_peaks"] == 3.0  # 7:xx i 16:xx mieszczą się w szczycie 7–9, 15–18
    assert flow["road_peak_source"] == "assumed" and flow["at_night"] == 0


def test_feed_without_times_has_empty_profile_data():
    feed = read_feed(gtfs_zip({"S1": LINE}, [("RAIL", "A", "S1")], SERVICES), *WORLD)
    assert feed.stop_times == {} and feed.stops == {}
    assert hourly_profile(feed, ["S1"], (21.05, 52.2), date(2026, 11, 16)) == ([0] * 24, 1)
