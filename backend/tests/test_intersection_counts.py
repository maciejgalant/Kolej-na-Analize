"""Pomiary ZDM na skrzyżowaniach: parsowanie warstw ArcGIS, dopasowanie, zapis, API.

Odpowiedzi ArcGIS są sztuczne (FakeArcGis); testy nie łączą się z usługą ZDM.
Nazwy pól odpowiadają publicznym warstwom ZDM, liczby są wymyślone.
"""

import json
import os
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app.etl import intersection_counts as ic
from app.etl import road_counts as rc
from app.etl.remote_zip import RemoteFileUnavailable
from app.main import app
from app.worker import main
from tests.test_analysis_run import prepare
from tests.test_road_counts import lonlat
from tests.test_topology_import import conn  # noqa: F401  (fixture)

DB = pytest.mark.skipif(
    os.environ.get("RAILSAFE_TEST_DB") != "1",
    reason="ustaw RAILSAFE_TEST_DB=1 i POSTGRES_* wskazujące na bazę *_test",
)


def summary_row(point_id, name, lon, lat, day="2023-09-12"):
    return {
        "ID": point_id,
        "Nazwa_skrzyżowania": name,
        "Długość_geograficzna": lon,
        "Szerokość_geograficzna": lat,
        "Data_wykonania": day,
        "Liczba_godzin_pomiaru": 3,
        "Klasa_drogi_nadrzędnej": "Z",
        "Klasa_drogi_podrzędnej": "L",
        "Sygnalizacja_świetlna": "tak",
        "Raport": "https://example.invalid/raport.pdf",
    }


def hour_row(point_id, gg, so, sd=100, s_c=40, scp=10, bus=30, piesi=50, rowerzysci=20):
    total = so + sd + s_c + scp + bus
    return {"ID": point_id, "GG": gg, "SO": so, "SD": sd, "S_C_": s_c, "SCP": scp,
            "BUS": bus, "M": None, "Rower": 0, "suma": total, "Piesi": piesi,
            "Rowerzyści": rowerzysci, "Data_wykonania": None}  # fmt: skip


def hours(point_id):
    return [
        hour_row(point_id, "7.00-8.00", 1820, piesi=80),
        hour_row(point_id, "12.00-13.00", 1120, piesi=120, rowerzysci=35),
        hour_row(point_id, "16.00-17.00", 2020, piesi=95),
    ]


# --- bez bazy -------------------------------------------------------------------------------


def test_streets_are_split_from_intersection_names():
    assert ic.split_streets("ul. Marsa - ul. Żołnierska - ul. Rekrucka") == [
        "ul. Marsa", "ul. Żołnierska", "ul. Rekrucka",
    ]  # fmt: skip
    assert ic.split_streets("Dolina Służewiecka – Nowoursynowska") == [
        "Dolina Służewiecka", "Nowoursynowska",
    ]  # fmt: skip


def test_layers_are_parsed_into_intersections_with_hours():
    items = ic.parse(
        [summary_row("7", "ul. Testowa - ul. Inna", "21,03039", "52.26673")], hours("7")
    )
    item = items[0]
    assert (item.point_id, item.lon, item.lat, item.measured_on) == (
        "7", 21.03039, 52.26673, date(2023, 9, 12),
    )  # fmt: skip
    assert item.streets == {"testowa", "inna"}
    assert [h.label for h in item.hours] == ["7:00–8:00", "12:00–13:00", "16:00–17:00"]
    assert item.peak.vehicles == 2200 and item.peak.label == "16:00–17:00"
    # ciężkie = ciężarowe + z przyczepą + autobusy: 80 na godzinę z 5 500 pojazdów łącznie
    assert item.heavy_share == pytest.approx(240 / 5500)
    assert (item.pedestrians_max, item.cyclists_max, item.signals) == (120, 35, True)


def test_rows_without_position_or_hours_are_handled():
    items = ic.parse(
        [summary_row("1", "A - B", None, "52.2"), summary_row("2", "C - D", 21.0, 52.2)],
        [{"ID": "2", "GG": "bez godziny", "suma": 10}],
    )
    assert [i.point_id for i in items] == ["2"]  # bez współrzędnych: pominięte
    assert items[0].hours == [] and items[0].peak is None and items[0].heavy_share is None


class FakeArcGis:
    """Warstwa FeatureServer ze stronicowaniem (exceededTransferLimit)."""

    def __init__(self, layers, page=2, fail_first=0):
        self.layers = layers  # url -> lista atrybutów
        self.page = page
        self.fail_first = fail_first
        self.requests = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_first:
            self.fail_first -= 1
            return httpx.Response(502)
        layer = str(request.url.copy_with(query=None)).removesuffix("/query")
        rows = self.layers[layer]
        offset = int(request.url.params.get("resultOffset", 0))
        chunk = rows[offset : offset + self.page]
        return httpx.Response(
            200,
            json={"features": [{"attributes": r} for r in chunk],
                  "exceededTransferLimit": offset + self.page < len(rows)},
        )  # fmt: skip


def test_arcgis_client_pages_through_layer_and_retries():
    rows = [summary_row(str(i), f"X{i} - Y", 21.0, 52.2) for i in range(5)]
    fake = FakeArcGis({ic.SUMMARY_URL: rows}, page=2, fail_first=1)
    client = ic.ArcGisClient(
        httpx.Client(transport=httpx.MockTransport(fake.handler)), sleep=lambda _s: None
    )
    assert [r["ID"] for r in client.features(ic.SUMMARY_URL, ic.SUMMARY_FIELDS)] == [
        "0", "1", "2", "3", "4",
    ]  # fmt: skip
    offsets = [r.url.params["resultOffset"] for r in fake.requests]
    assert offsets == ["0", "0", "2", "4"]  # pierwsze zapytanie dostało 502
    assert fake.requests[-1].url.params["returnGeometry"] == "false"
    dead = FakeArcGis({ic.SUMMARY_URL: rows}, fail_first=10)
    with pytest.raises(RemoteFileUnavailable):
        ic.ArcGisClient(
            httpx.Client(transport=httpx.MockTransport(dead.handler)),
            retry_delays_s=(0.0,),
            sleep=lambda _s: None,
        ).features(ic.SUMMARY_URL, ic.SUMMARY_FIELDS)


# --- PostGIS --------------------------------------------------------------------------------


def layers_near_ok(conn):  # noqa: F811
    """Skrzyżowania: 120 m od 'ok' na Testowej, 600 m dalej i obok, ale na innej ulicy."""
    near = lonlat(conn, 630500, 480622)
    far = lonlat(conn, 630500, 481102)
    other = lonlat(conn, 630520, 480510)
    summary = [
        summary_row("1", "ul. Testowa - ul. Boczna", *near),
        summary_row("2", "ul. Testowa - ul. Daleka", *far),
        summary_row("3", "ul. Inna - ul. Obca", *other),
    ]
    return summary, hours("1") + hours("2") + hours("3")


@DB
def test_nearest_intersection_on_the_same_street_is_matched(conn):  # noqa: F811
    prepare(conn)
    summary, hourly = layers_near_ok(conn)
    items = ic.parse(summary, hourly)
    crossings = rc.crossing_streets(conn)
    names = {c.crossing_id: c.name for c in crossings}
    found = {(names[m.crossing_id], m.point_id) for m in ic.match(conn, items, crossings)}
    # 'ok': najbliższe na Testowej (1); 2 jest dalej niż MAX_M, 3 leży na innej ulicy.
    # 'old-track' (1,3 km dalej) nie ma skrzyżowania do 300 m.
    assert found == {("ok", "1")}


@DB
def test_import_stores_hours_and_detail_api_summarises_them(conn, tmp_path):  # noqa: F811
    prepare(conn)
    summary, hourly = layers_near_ok(conn)
    summary_path, hourly_path = tmp_path / "summary.json", tmp_path / "hourly.json"
    summary_path.write_text(json.dumps({"features": [{"attributes": r} for r in summary]}))
    hourly_path.write_text(json.dumps({"features": [{"attributes": r} for r in hourly]}))
    report_path = tmp_path / "inter.md"
    args = ["import-intersection-counts", "--summary-file", str(summary_path),
            "--hourly-file", str(hourly_path), "--report", str(report_path)]  # fmt: skip
    assert main(args) == 0
    assert main(args) == 0  # powtórny import aktualizuje zamiast dublować

    stored = conn.execute(
        "SELECT station_id, count(*), max(vehicles_count), sum(pedestrians), unit, direction "
        "FROM road.measurements GROUP BY station_id, unit, direction"
    ).fetchall()
    assert stored == [("SKRZ-1", 3, 2200, 295, "vehicles/hour", "all")]
    kinds = conn.execute("SELECT match_type FROM road.crossing_stations").fetchall()
    assert kinds == [("intersection",)]

    report = report_path.read_text(encoding="utf-8")
    assert "ul. Testowa - ul. Boczna" in report and "2 200 (16:00–17:00)" in report
    assert "Skrzyżowań w danych: **3**" in report

    # API szczegółów: podsumowanie godzin; pomiar nie zmienia składnika T
    crossing_id = conn.execute(
        "SELECT crossing_id FROM spatial.crossings WHERE name = 'ok'"
    ).fetchone()[0]
    detail = TestClient(app).get(f"/api/v1/crossings/{crossing_id}").json()
    count = detail["road_counts"][0]
    assert count["kind"] == "intersection" and count["match_type"] == "intersection"
    assert count["name"] == "ul. Testowa - ul. Boczna"
    assert (count["measured_on"], count["hours"], count["peak_vehicles"]) == (
        "2023-09-12", 3, 2200,
    )  # fmt: skip
    assert count["peak_hour"] == "16:00–17:00"
    assert count["heavy_share"] == pytest.approx(0.044, abs=0.001)
    assert (count["pedestrians_max"], count["cyclists_max"]) == (120, 35)
    assert count["distance_m"] == pytest.approx(120, abs=1)
    sources = {s["name"] for s in detail["sources"]}
    assert "ZDM - pomiary ruchu na skrzyżowaniach 2023-2026" in sources
