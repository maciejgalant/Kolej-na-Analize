"""API dzielnic i przejazdów na danych testowych z test_topology_import."""

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.test_topology_import import conn, run_import  # noqa: F401  (fixture)

DB = pytest.mark.skipif(
    os.environ.get("RAILSAFE_TEST_DB") != "1",
    reason="ustaw RAILSAFE_TEST_DB=1 i POSTGRES_* wskazujące na bazę *_test",
)


@pytest.fixture
def client(conn):  # noqa: F811
    run_import(conn)
    return TestClient(app)


def names(body) -> list[str]:
    return [feature["properties"]["name"] for feature in body["features"]]


@DB
def test_districts_are_geojson_with_counts(client):
    body = client.get("/api/v1/districts").json()
    assert body["type"] == "FeatureCollection"
    by_name = {f["properties"]["name"]: f for f in body["features"]}
    assert list(by_name) == ["Alfa", "Bemowo"]
    alfa = by_name["Alfa"]
    assert alfa["geometry"]["type"] == "MultiPolygon"
    lon, lat = alfa["geometry"]["coordinates"][0][0][0]
    assert 20 < lon < 22 and 51 < lat < 53  # WGS84, nie EPSG:2180
    assert alfa["properties"]["crossings_verified"] == 2
    assert alfa["properties"]["road_crossings"] == 1
    assert alfa["properties"]["pedestrian_crossings"] == 1


@DB
def test_crossings_default_to_verified_inside_city(client):
    body = client.get("/api/v1/crossings").json()
    assert body["total"] == 3
    assert names(body) == ["boundary-ped", "ok", "old-track"]
    first = body["features"][0]
    assert first["geometry"]["type"] == "Point"
    assert first["properties"]["is_pedestrian"] is True
    assert first["properties"]["district_name"] == "Alfa"
    assert first["properties"]["manager"] == "PKP PLK"


@DB
def test_crossings_filters(client):
    everything = client.get("/api/v1/crossings", params={"verification_status": "all"}).json()
    assert everything["total"] == 5  # bez obiektu spoza miasta
    assert "outside" not in names(everything)
    warned = {f["properties"]["name"]: f["properties"]["warnings"] for f in everything["features"]}
    assert warned["no-road"] == 1 and warned["ok"] == 0

    unverified = client.get(
        "/api/v1/crossings", params={"verification_status": "unverified"}
    ).json()
    assert sorted(names(unverified)) == ["bridge", "no-road"]

    district = next(
        f["id"]
        for f in client.get("/api/v1/districts").json()["features"]
        if f["properties"]["name"] == "Bemowo"
    )
    assert names(client.get("/api/v1/crossings", params={"district_id": district}).json()) == [
        "old-track"
    ]
    by_category = client.get("/api/v1/crossings", params={"category": ["B", "E"]}).json()
    assert names(by_category) == ["boundary-ped", "ok"]

    page = client.get("/api/v1/crossings", params={"limit": 1, "offset": 1}).json()
    assert (page["total"], names(page)) == (3, ["ok"])


@DB
def test_crossings_bbox_filter(client):
    ok = client.get("/api/v1/crossings").json()["features"][1]
    lon, lat = ok["geometry"]["coordinates"]
    box = f"{lon - 0.0005},{lat - 0.0005},{lon + 0.0005},{lat + 0.0005}"
    assert names(client.get("/api/v1/crossings", params={"bbox": box}).json()) == ["ok"]


@DB
def test_crossing_detail_lists_links_flags_and_sources(client):
    listing = client.get("/api/v1/crossings").json()
    old_track = next(f for f in listing["features"] if f["properties"]["name"] == "old-track")
    detail = client.get(f"/api/v1/crossings/{old_track['id']}").json()
    assert detail["category"] == "D"
    assert detail["verification_status"] == "verified"
    assert detail["verified_at"].endswith("Z")
    assert detail["district_name"] == "Bemowo"
    assert detail["tracks"] == [
        {"line_number": "9", "track_function": "tor szlakowy", "track_count": 2,
         "existence": "nieczynny", "distance_m": 0.0}
    ]  # fmt: skip
    assert detail["roads"][0]["name"] == "ul. Testowa"
    assert [flag["code"] for flag in detail["quality_flags"]] == ["track_inactive"]
    assert {a["code"] for a in detail["attributes"]} >= {"manager", "location_type"}
    sources = {s["name"]: s for s in detail["sources"]}
    assert len(sources) == 2
    utk = next(s for name, s in sources.items() if "UTK" in name)
    assert utk["license_verified"] is False  # licencja usługi UTK niepotwierdzona


@DB
def test_crossing_detail_404(client):
    assert client.get("/api/v1/crossings/999999").status_code == 404


@pytest.mark.parametrize(
    "params",
    [
        {"bbox": "1,2,3"},
        {"bbox": "22,52,21,53"},
        {"limit": 0},
        {"limit": 501},
        {"verification_status": "maybe"},
        {"category": "X"},
        {"district_id": 0},
    ],
)
def test_crossings_rejects_invalid_parameters(params, monkeypatch):
    from app import db

    app.dependency_overrides[db.get_connection] = lambda: None
    try:
        assert TestClient(app).get("/api/v1/crossings", params=params).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_database_down_gives_503(monkeypatch):
    from app.config import Settings, get_settings

    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, postgres_host="127.0.0.1", postgres_port=1, healthcheck_timeout_s=1
    )
    try:
        assert TestClient(app).get("/api/v1/districts").status_code == 503
    finally:
        app.dependency_overrides.clear()
