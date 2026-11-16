import csv
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.incidents import incidents, street_candidates
from app.main import app
from tests.test_topology_import import conn  # noqa: F401


def test_api_distinguishes_city_records_street_candidates_and_demo():
    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

    class Connection:
        name = "Przejazd testowy"

        def execute(self, sql, params=None):
            if "SELECT name FROM spatial.crossings" in sql:
                return Cursor([{"name": self.name}])
            if "road_name" in sql:
                return Cursor([{"road_name": "ul. Jutrzenki"}])
            return Cursor(
                [
                    {
                        "source_object_id": "109899553",
                        "occurred_on": "2021-02-17",
                        "incident_type": "Zderzenie pojazdów boczne",
                        "crossing_id": None,
                        "confirmed": False,
                        "location_confidence": "unknown",
                        "metadata": {
                            "address": "WARSZAWA JUTRZENKI",
                            "street_keys": ["Jutrzenki"],
                            "local_time": "15:23",
                            "place": "Przejazd kolejowy niestrzeżony",
                            "injured": 3,
                            "killed": None,
                        },
                    }
                ]
            )

    database = Connection()
    city = incidents(database, crossing_id=None).model_dump()
    assert city["scope"] == "warsaw" and city["coverage"] == "partial"
    assert city["records"][0]["killed"] is None
    candidates = incidents(database, crossing_id=7).model_dump()
    assert candidates["scope"] == "street_candidates"
    assert candidates["records"][0]["crossing_id"] is None
    assert candidates["records"][0]["confirmed"] is False
    database.name = "DEMO-7"
    assert incidents(database, crossing_id=7).records == []


def test_street_match_is_exact_not_substring_and_never_assigns_crossing():
    record = {"street_keys": ["Chłopickiego"], "crossing_id": None}
    assert street_candidates([record], ["ul. Józefa Chłopickiego"]) == [record]
    assert street_candidates([record], ["ul. Chłopickiego Boczna"]) == []
    assert street_candidates([record], []) == []
    assert record["crossing_id"] is None


def test_snapshot_preserves_unknown_casualties_and_reported_dates():
    path = Path(__file__).parents[1] / "migrations/data/sewik_warsaw_user_snapshot.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len({r["id"] for r in rows}) == 20
    assert sum(r["place"].startswith("Przejazd") for r in rows) == 14
    assert sum(int(r["injured"]) for r in rows if r["injured"]) == 5
    salomea = next(r for r in rows if r["id"] == "109899553")
    assert (salomea["date"], salomea["time"], salomea["injured"]) == ("2021-02-17", "15:23", "3")
    assert rows[-1]["date"] == "2025-11-18"
    assert rows[0]["injured"] == ""


@pytest.mark.skipif(os.environ.get("RAILSAFE_TEST_DB") != "1", reason="wymaga PostGIS test")
def test_migration_and_api_preserve_unassigned_partial_records(conn):  # noqa: F811
    # The real migration seeds the snapshot, with no fabricated coordinates or links.
    client = TestClient(app)
    response = client.get("/api/v1/incidents")
    assert response.status_code == 200
    body = response.json()
    assert body["coverage"] == "partial" and len(body["records"]) == 20
    assert all(r["crossing_id"] is None and not r["confirmed"] for r in body["records"])
    assert all(r["location_confidence"] == "unknown" for r in body["records"])
    assert all(r["killed"] is None for r in body["records"])
    assert client.get("/api/v1/incidents?crossing_id=999999999").status_code == 404
    assert client.get("/api/v1/incidents?crossing_id=0").status_code == 422
