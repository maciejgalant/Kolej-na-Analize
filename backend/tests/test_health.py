import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api import health
from app.api.health import DatabaseHealth, OllamaHealth
from app.config import Settings, get_settings
from app.main import app

SETTINGS = Settings(_env_file=None, ollama_model="qwen3:4b", postgres_password="x")


@pytest.fixture
def client():
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    yield TestClient(app)
    app.dependency_overrides.clear()


def _patch(monkeypatch, database: DatabaseHealth, ollama: OllamaHealth):
    monkeypatch.setattr(health, "check_database", lambda _s: database)
    monkeypatch.setattr(health, "check_ollama", lambda _s: ollama)


def test_health_ok(client, monkeypatch):
    _patch(
        monkeypatch,
        DatabaseHealth(status="ok", postgis_version="3.4.3"),
        OllamaHealth(status="ok", model="qwen3:4b", model_available=True),
    )
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["demo_mode"] is True
    assert body["services"]["database"]["postgis_version"] == "3.4.3"


def test_health_degraded_but_200_when_dependencies_down(client, monkeypatch):
    _patch(
        monkeypatch,
        DatabaseHealth(status="unavailable"),
        OllamaHealth(status="unavailable", model="qwen3:4b"),
    )
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


def test_health_degraded_when_model_not_pulled(client, monkeypatch):
    _patch(
        monkeypatch,
        DatabaseHealth(status="ok", postgis_version="3.4.3"),
        OllamaHealth(status="ok", model="qwen3:4b", model_available=False),
    )
    assert client.get("/api/v1/health").json()["status"] == "degraded"


def test_check_database_reports_unavailable(monkeypatch):
    def boom(*_a, **_k):
        raise psycopg.OperationalError("brak połączenia")

    monkeypatch.setattr(psycopg, "connect", boom)
    assert health.check_database(SETTINGS).status == "unavailable"


@pytest.mark.parametrize(
    ("models", "expected"),
    [([{"name": "qwen3:4b"}], True), ([{"name": "inny:1b"}], False), ([], False)],
)
def test_check_ollama_detects_model(monkeypatch, models, expected):
    def fake_get(url, timeout):
        return httpx.Response(200, json={"models": models}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    result = health.check_ollama(SETTINGS)
    assert result.status == "ok"
    assert result.model_available is expected


def test_check_ollama_reports_unavailable(monkeypatch):
    def boom(url, timeout):
        raise httpx.ConnectError("brak połączenia")

    monkeypatch.setattr(httpx, "get", boom)
    assert health.check_ollama(SETTINGS).status == "unavailable"


def test_openapi_exposed_under_api_prefix(client):
    assert client.get("/api/v1/openapi.json").status_code == 200
