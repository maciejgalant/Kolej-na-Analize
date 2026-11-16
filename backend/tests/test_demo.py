"""Zestaw demonstracyjny: pełna ścieżka import → analiza → API → funkcje asystenta."""

import os
from datetime import date

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from app import worker
from app.assistant.tools import call_tool
from app.config import get_settings
from app.demo import CROSSINGS, DemoConflict, demo_present, load_demo
from app.main import app

pytestmark = pytest.mark.skipif(
    os.environ.get("RAILSAFE_TEST_DB") != "1",
    reason="ustaw RAILSAFE_TEST_DB=1 i POSTGRES_* wskazujące na bazę *_test",
)
TODAY = date(2026, 11, 13)


@pytest.fixture
def db():
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.postgres_db.endswith("_test")
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    with psycopg.connect(**settings.database_connect_kwargs, autocommit=True) as connection:
        yield connection
    command.downgrade(cfg, "base")


def test_demo_set_gives_a_complete_labelled_ranking(db):
    assert not demo_present(db)
    summary = load_demo(db, TODAY)
    assert demo_present(db)
    # 9 przejazdów drogowych; bocznica (DEMO-09) nie ma kursów, więc nie ma pozycji
    assert (summary.scored, summary.ranked) == (9, 8)

    client = TestClient(app)
    run = client.get("/api/v1/analysis/latest").json()
    assert run["is_demo"] is True and run["ranked"] == 8
    features = client.get("/api/v1/crossings").json()["features"]
    props = {f["properties"]["official_id"]: f["properties"] for f in features}
    assert set(props) == {item.name for item in CROSSINGS}
    assert all(p["verification_status"] == "verified" for p in props.values())
    assert all(p["district_name"].startswith("Demo-") for p in props.values())
    assert props["DEMO-01"]["trains_weekday"] == 120 and props["DEMO-06"]["trains_weekday"] == 24
    assert props["DEMO-09"]["rank"] is None and props["DEMO-10"]["rank"] is None
    # kategoria D przy 120 pociągach wyprzedza kategorię A na drodze głównej
    assert props["DEMO-04"]["rank"] < props["DEMO-01"]["rank"]
    assert props["DEMO-08"]["rank"] is not None  # kategoria F bez jezdni: droga wewnętrzna
    assert client.get("/api/v1/health").json()["services"]["database"]["demo_data"] is True
    # fikcyjny pomiar ruchu drogowego 150 m od DEMO-02, ze źródłem oznaczonym jako demo
    demo02 = client.get(f"/api/v1/crossings/{props['DEMO-02']['crossing_id']}").json()
    exposure = next(c for c in demo02["priority"]["components"] if c["component"] == "T")
    assert exposure["status"] == "ok"
    assert exposure["detail"]["vehicles_per_day_measured"] == 21500
    assert exposure["detail"]["measurement"]["source"] == "demo_road_counts"
    assert db.execute(
        "SELECT bool_and(is_demo) FROM system.sources WHERE code = 'demo_road_counts'"
    ).fetchone()[0]
    # fikcyjny rozkład w ciągu doby: szczyty poranny i popołudniowy (RSA-018)
    flow = demo02["rail_flow"]
    assert sum(flow["hourly_weekday"]) == 120 and flow["max_hour"] in (7, 16)
    assert flow["road_peak_source"] == "zdm"  # profil z fikcyjnego licznika DEMO-APR-1
    # fikcyjne skrzyżowanie z pomiarem godzinowym przy DEMO-04
    demo04 = client.get(f"/api/v1/crossings/{props['DEMO-04']['crossing_id']}").json()
    intersection = demo04["road_counts"][0]
    assert intersection["kind"] == "intersection" and intersection["is_demo"] is True
    assert (intersection["peak_vehicles"], intersection["pedestrians_max"]) == (670, 88)

    with psycopg.connect(
        **get_settings().database_connect_kwargs, row_factory=dict_row
    ) as dict_conn:
        ranking = call_tool(dict_conn, "get_ranking", {"district": "Demo-Centrum", "limit": 5})
    assert "DEMO-04" in str(ranking)


def test_demo_reload_is_idempotent_and_never_mixes_with_real_data(db, capsys):
    load_demo(db, TODAY)
    load_demo(db, TODAY)
    assert db.execute("SELECT count(*) FROM spatial.crossings").fetchone()[0] == len(CROSSINGS)
    # import danych rzeczywistych na bazie demonstracyjnej jest odrzucany przed pobraniem
    assert worker.main(["import-crossings"]) == 1
    assert "zestaw demonstracyjny" in capsys.readouterr().err

    db.execute("UPDATE spatial.crossings SET name = '021 005 525' WHERE name = 'DEMO-01'")
    with pytest.raises(DemoConflict):
        load_demo(db, TODAY)
