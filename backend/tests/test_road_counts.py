"""Pomiary ruchu ZDM (APR): klient, parsowanie, dopasowanie do przejazdów i użycie w WPO.

Wszystkie odpowiedzi serwera są sztuczne (FakeZdm); testy nie łączą się z ZDM.
Struktura odpowiedzi odpowiada publicznemu narzędziu ZDM, liczby są wymyślone.
"""

import json
import os
from datetime import date, datetime

import httpx
import pytest

from app.analysis import rps
from app.analysis.run import build_run_report, run_analysis
from app.etl import road_counts as rc
from app.etl.remote_zip import RemoteFileUnavailable
from app.etl.zdm_apr import (
    REPRESENTATIVE_DAYS,
    WARSAW_TZ,
    ZdmClient,
    ZdmReportError,
    parse_report,
    report_request,
)
from app.worker import main
from tests.test_analysis_run import prepare
from tests.test_topology_import import conn  # noqa: F401  (fixture)

DB = pytest.mark.skipif(
    os.environ.get("RAILSAFE_TEST_DB") != "1",
    reason="ustaw RAILSAFE_TEST_DB=1 i POSTGRES_* wskazujące na bazę *_test",
)
HOURLY = [50] * 6 + [400] * 3 + [300] * 6 + [500] * 3 + [200] * 6  # suma 6 000, szczyt 15–17


def section(point_id, street, lon, lat, average=7200, days=20, hourly=HOURLY, section="A - B"):
    return {
        "pointId": point_id,
        "sectionName": point_id,
        "street": street,
        "section": section,
        "coordinates": f"{lon:.6f} {lat:.6f}",
        "date": "2026-10-13 - 2026-11-09",
        "direction": "Oba kierunki",
        "average": average,
        "maximum": average + 900 if average else "-",
        "summary": average * days if average else "-",
        "measuresAmount": 24,
        "values": [
            {"date": f"{h:02d}", "serie": "Liczba pojazdów", "value": v, "filterOut": False}
            for h, v in enumerate(hourly)
        ],
    }


def finished(*sections, uuid="u-1"):
    return {"status": "FINISHED", "progress": 100, "uuid": uuid,
            "data": {"sections": list(sections), "dayTypes": [], "locations": []}}  # fmt: skip


def location(point_id, street, lon, lat, direction, road_class="Z"):
    return {
        "locationId": f"{point_id}-{direction}",
        "direction": direction,
        "forPortal": True,
        "latitude": lat,
        "longitude": lon,
        "roadClass": road_class,
        "point": {"pointId": point_id, "pointStreet": street, "pointSection": "A - B",
                  "latitude": lat, "longitude": lon},
    }  # fmt: skip


class FakeZdm:
    """Naśladuje lokalizacje, zlecenie raportu i odpytywanie o postęp."""

    def __init__(self, locations, sections, polls_before_done=2, fail_first=0):
        self.locations = locations
        self.sections = sections  # point_id -> sekcja raportu
        self.polls_before_done = polls_before_done
        self.fail_first = fail_first
        self.requests = []
        self.jobs = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_first:
            self.fail_first -= 1
            return httpx.Response(503)
        name = request.url.path.rsplit("/", 1)[-1]
        if name == "getLocations.ccor":
            assert request.method == "POST"
            return httpx.Response(200, json=self.locations)
        if name == "generateReport.ccor":
            body = json.loads(request.content)
            uuid = f"u-{len(self.jobs) + 1}"
            points = {loc["point"]["pointId"] for loc in body["locations"]}
            self.jobs[uuid] = [body, [self.sections[p] for p in sorted(points)], 0]
            return httpx.Response(200, json={"status": "RUNNING", "progress": 0, "uuid": uuid})
        if name == "getReportProgress.ccor":
            job = self.jobs[request.url.params["uuid"]]
            job[2] += 1
            if job[2] <= self.polls_before_done:
                return httpx.Response(200, json={"status": "RUNNING", "progress": 50})
            return httpx.Response(200, json=finished(*job[1], uuid=request.url.params["uuid"]))
        return httpx.Response(404)

    def client(self, **kwargs) -> ZdmClient:
        http = httpx.Client(transport=httpx.MockTransport(self.handler))
        return ZdmClient(http, base_url="https://fake.zdm/api/", sleep=lambda _s: None, **kwargs)


# --- bez bazy -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ul. Radzymińska", "radzymińska"),
        ("Radzymińska", "radzymińska"),
        ("al. Solidarności", "solidarności"),
        ("Aleja Gen. Sikorskiego", "gen sikorskiego"),
        ("ul.Testowa", "testowa"),
        (None, None),
        ("ul.", None),
    ],
)
def test_street_names_are_normalized(raw, expected):
    assert rc.normalize_street(raw) == expected


def test_report_is_parsed_with_hourly_profile_and_days():
    reports = parse_report(finished(section("1354", "Radzymińska", 21.0767, 52.2882)))
    assert len(reports) == 1
    r = reports[0]
    assert (r.point_id, r.street, r.vehicles_per_day, r.max_per_day, r.days) == (
        "1354", "Radzymińska", 7200, 8100, 20,
    )  # fmt: skip
    assert (r.lon, r.lat) == (21.0767, 52.2882)
    assert (r.period_start, r.period_end) == (date(2026, 10, 13), date(2026, 11, 9))
    assert len(r.hourly) == 24 and sum(r.hourly) == 6000
    assert r.peak_hour == 15


def test_missing_values_are_not_turned_into_zero():
    empty = section("9", "Pusta", 21.0, 52.2, average=0, hourly=[0] * 24)
    r = parse_report(finished(empty))[0]
    assert (r.vehicles_per_day, r.max_per_day, r.days, r.hourly) == (None, None, None, None)
    with pytest.raises(ZdmReportError):
        parse_report({"status": "RUNNING"})


def test_report_request_uses_local_days_and_representative_days():
    body = report_request([{"locationId": "1"}], date(2026, 10, 29), date(2026, 11, 12))
    start = datetime.fromtimestamp(body["startDate"] / 1000, WARSAW_TZ)
    end = datetime.fromtimestamp(body["endDate"] / 1000, WARSAW_TZ)
    # jak formularz ZDM: od północy pierwszego dnia do 23:59:59 ostatniego, czas lokalny
    assert (start.isoformat(), end.isoformat()) == (
        "2026-10-29T00:00:00+01:00", "2026-11-12T23:59:59+01:00",
    )  # fmt: skip
    assert body["dayTypes"] == [REPRESENTATIVE_DAYS]
    assert (body["groupByPoint"], body["aggregationFunction"], body["reportId"]) == (
        "POINT", "AVG", "001A",
    )  # fmt: skip


def test_client_orders_report_and_polls_until_finished():
    locations = [location("1354", "Radzymińska", 21.0767, 52.2882, d) for d in ("C", "M")]
    fake = FakeZdm(locations, {"1354": section("1354", "Radzymińska", 21.0767, 52.2882)},
                   fail_first=1)  # fmt: skip
    client = fake.client()
    assert len(client.locations()) == 2  # pierwsze zapytanie dostało 503 i zostało ponowione
    payload = client.report(locations, date(2026, 10, 13), date(2026, 11, 9))
    assert parse_report(payload)[0].vehicles_per_day == 7200
    order = [r.url.path.rsplit("/", 1)[-1] for r in fake.requests]
    assert (
        order
        == ["getLocations.ccor"] * 2 + ["generateReport.ccor"] + ["getReportProgress.ccor"] * 3
    )
    sent = json.loads(fake.requests[2].content)
    assert len(sent["locations"]) == 2  # oba kierunki punktu w jednym raporcie


def test_client_gives_up_on_slow_report_and_dead_server():
    locations = [location("1", "X", 21.0, 52.2, "C")]
    slow = FakeZdm(locations, {"1": section("1", "X", 21.0, 52.2)}, polls_before_done=100)
    with pytest.raises(ZdmReportError, match="nie powstał"):
        slow.client(timeout_s=3.0, poll_interval_s=1.5).report(
            locations, date(2026, 1, 5), date(2026, 1, 9)
        )
    dead = FakeZdm(locations, {}, fail_first=10)
    with pytest.raises(RemoteFileUnavailable):
        dead.client(retry_delays_s=(0.0, 0.0)).locations()


def test_measured_vehicles_replace_the_model_in_exposure():
    model = rps.exposure_component(100, "droga zbiorcza")
    measured = rps.exposure_component(
        100, "droga zbiorcza", vehicles_measured=35000, measurement={"station_id": "1354"}
    )
    assert model.status == "modelled" and model.detail["vehicles_source"] == "model"
    assert measured.status == "ok"
    assert measured.detail["vehicles_per_day_measured"] == 35000
    assert measured.detail["vehicles_per_day_model"] == 8000  # zostaje do porównania
    assert measured.detail["measurement"] == {"station_id": "1354"}
    assert measured.value > model.value
    # pomiar nie ratuje przejazdu bez kursów pasażerskich: ruch kolejowy wciąż nieznany
    assert rps.exposure_component(0, "droga zbiorcza", vehicles_measured=35000).value is None


# --- PostGIS --------------------------------------------------------------------------------


def lonlat(conn, east, north):  # noqa: F811
    return conn.execute(
        "SELECT ST_X(p), ST_Y(p) FROM (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), "
        "2180), 4326) AS p) t",
        (east, north),
    ).fetchone()


def stations_near_ok(conn):  # noqa: F811
    """Punkty: 100 m od 'ok' na tej samej ulicy, 800 m dalej, oraz inna ulica tuż obok."""
    near = lonlat(conn, 630500, 480602)
    far = lonlat(conn, 630500, 481302)
    other = lonlat(conn, 630510, 480510)
    return {
        "NEAR": section("NEAR", "Testowa", *near, average=12000),
        "FAR": section("FAR", "Testowa", *far, average=9000),
        "OTHER": section("OTHER", "Inna", *other, average=50000),
    }


@DB
def test_points_are_matched_only_on_the_same_street(conn):  # noqa: F811
    prepare(conn)
    sections = stations_near_ok(conn)
    reports = parse_report(finished(*sections.values()))
    crossings = rc.crossing_streets(conn)
    names = {c.crossing_id: c.name for c in crossings}
    assert {c.name: c.streets for c in crossings}["ok"] == {"testowa"}
    matches = rc.match_stations(conn, rc.stations_from_reports(reports), crossings)
    found = {(names[m.crossing_id], m.point_id, m.match_type) for m in matches}
    assert found == {
        ("ok", "NEAR", "direct"),
        ("ok", "FAR", "validation"),  # ta sama ulica, ale dalej niż DIRECT_M
        # 'old-track' leży na innej „Testowej” 1,3 km dalej: tylko walidacja
        ("old-track", "NEAR", "validation"),
        ("old-track", "FAR", "validation"),
    }
    # punkt OTHER jest 12 m od przejazdu, ale na innej ulicy — nigdy nie jest przypisywany
    assert all(m.point_id != "OTHER" for m in matches)
    near = next(m for m in matches if m.point_id == "NEAR" and names[m.crossing_id] == "ok")
    assert near.distance_m == pytest.approx(100.0, abs=1.0)


def _import_from_file(conn, tmp_path, sections):  # noqa: F811
    path = tmp_path / "zdm.json"
    path.write_text(json.dumps(finished(*sections)), encoding="utf-8")
    report_path = tmp_path / "DATA_AUDIT_road.md"
    code = main(
        ["import-road-counts", "--zdm-file", str(path), "--day-type", "miarodajny",
         "--report", str(report_path)]
    )  # fmt: skip
    assert code == 0
    return report_path.read_text(encoding="utf-8")


@DB
def test_file_import_stores_measurements_and_feeds_rps(conn, tmp_path):  # noqa: F811
    prepare(conn)
    report = _import_from_file(conn, tmp_path, stations_near_ok(conn).values())

    stored = conn.execute(
        "SELECT station_id, vehicles_count, unit, day_type, days_count, "
        "jsonb_array_length(hourly_profile), quality_status FROM road.measurements ORDER BY 1"
    ).fetchall()
    assert stored == [
        ("FAR", 9000, "vehicles/day", "miarodajny", 20, 24, "ok"),
        ("NEAR", 12000, "vehicles/day", "miarodajny", 20, 24, "ok"),
    ]  # OTHER nie pasuje do żadnego przejazdu, więc nie jest zapisywany
    assert conn.execute("SELECT count(*) FROM road.crossing_stations").fetchone()[0] == 4
    licence = conn.execute(
        "SELECT l.attribution_text FROM system.sources s JOIN system.licenses l "
        "USING (license_id) WHERE s.code = 'zdm_apr'"
    ).fetchone()[0]
    assert "Zarząd Dróg Miejskich" in licence

    assert "pomiar w WPO" in report and "walidacja" in report
    assert "12\u00a0000" in report and "4,8×" in report  # droga lokalna: model 2 500
    run_analysis(conn)
    components = {
        name: (status, detail)
        for name, status, detail in conn.execute(
            "SELECT c.name, k.status, k.detail FROM analysis.components k "
            "JOIN spatial.crossings c USING (crossing_id) WHERE k.component = 'T'"
        )
    }
    status, detail = components["ok"]
    assert status == "ok"
    assert detail["vehicles_per_day_measured"] == 12000
    assert detail["measurement"]["station_id"] == "NEAR"
    assert detail["measurement"]["period_start"] == "2026-10-13"
    # old-track ma tylko punkty walidacyjne: zostaje model z klasy drogi
    assert components["old-track"][0] == "modelled"
    assert components["old-track"][1]["vehicles_source"] == "model"
    run_report = build_run_report(conn, run_summary(conn))
    assert "pomiaru ZDM ma 1 z 2" in run_report


def run_summary(conn):  # noqa: F811
    from app.analysis.run import RunSummary

    run_id, scored = conn.execute(
        "SELECT r.run_id, count(s.*) FROM analysis.runs r JOIN analysis.risk_scores s "
        "USING (run_id) GROUP BY r.run_id ORDER BY r.run_id DESC LIMIT 1"
    ).fetchone()
    return RunSummary(run_id, scored, scored, ("2026-11-16", "2026-11-22"))


@DB
def test_reimport_updates_instead_of_duplicating(conn, tmp_path):  # noqa: F811
    prepare(conn)
    sections = list(stations_near_ok(conn).values())
    _import_from_file(conn, tmp_path, sections)
    sections[0] = sections[0] | {"average": 13000, "summary": 13000 * 20}
    _import_from_file(conn, tmp_path, sections)
    assert conn.execute(
        "SELECT station_id, vehicles_count FROM road.measurements ORDER BY 1"
    ).fetchall() == [("FAR", 9000), ("NEAR", 13000)]
    assert conn.execute("SELECT count(*) FROM road.stations").fetchone()[0] == 2
    assert conn.execute("SELECT count(*) FROM road.crossing_stations").fetchone()[0] == 4


@DB
def test_api_import_orders_reports_only_for_matched_points(conn, tmp_path, monkeypatch):  # noqa: F811
    prepare(conn)
    sections = stations_near_ok(conn)
    locations = []
    for point_id, s in sections.items():
        lon, lat = (float(x) for x in s["coordinates"].split())
        locations += [location(point_id, s["street"], lon, lat, d) for d in ("C", "M")]
    fake = FakeZdm(locations, sections, polls_before_done=1)

    real_client = httpx.Client

    def fake_http(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_client(transport=httpx.MockTransport(fake.handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", fake_http)
    monkeypatch.setattr("app.etl.zdm_apr.time.sleep", lambda _s: None)
    report_path = tmp_path / "road.md"
    assert main(["import-road-counts", "--end", "2026-11-09", "--report", str(report_path)]) == 0
    ordered = [json.loads(r.content) for r in fake.requests if r.url.path.endswith("ort.ccor")]
    points = sorted({loc["point"]["pointId"] for body in ordered for loc in body["locations"]})
    assert points == ["FAR", "NEAR"]  # OTHER (inna ulica) nie jest odpytywany
    assert all(body["dayTypes"] == [REPRESENTATIVE_DAYS] for body in ordered)
    first = datetime.fromtimestamp(ordered[0]["startDate"] / 1000, WARSAW_TZ).date()
    assert first == date(2026, 10, 13)  # 28 dni kończących się 9 listopada
    assert conn.execute("SELECT day_type FROM road.measurements GROUP BY 1").fetchall() == [
        ("miarodajny",)
    ]
