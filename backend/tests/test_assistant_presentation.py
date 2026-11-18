"""UI contract and context handling without requiring PostGIS or a live language model."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import assistant as api
from app.assistant import service
from app.assistant.presentation import Evidence, build_evidence
from app.assistant.tools import ToolError
from app.config import Settings, get_settings
from app.db import get_connection
from app.main import app


def row(crossing_id=7, **extra):
    return {
        "crossing_id": crossing_id,
        "numer": "021 003 504",
        "kategoria": "B",
        "dzielnica": "Wawer",
        "pozycja": 2,
        "rps": 35.5,
        "pociagi_dzien_roboczy_plan": 12,
        **extra,
    }


def detail(*_, measured=False):
    return SimpleNamespace(
        sources=[SimpleNamespace(name="Ewidencja testowa", attribution="Test")],
        rail_flow=SimpleNamespace(
            source="Rozkład testowy",
            weekday_avg=12,
            saturday=None,
            sunday=0,
            period_start="2026-11-09",
            period_end="2026-11-15",
        ),
        priority=SimpleNamespace(
            method_version="test-1",
            completeness_pct=90,
            components=[
                SimpleNamespace(
                    component="T",
                    value=42,
                    status="ok" if measured else "modelled",
                    detail={
                        "vehicles_source": "measured" if measured else "model",
                        "vehicles_per_day_measured": 1200 if measured else None,
                        "vehicles_per_day_model": 900,
                        "measurement": {
                            "street": "Testowa",
                            "period_start": "2026-10-01",
                            "period_end": "2026-10-28",
                        },
                    },
                ),
                SimpleNamespace(component="H", value=None, status="unknown", detail={}),
            ],
        ),
    )


def test_ranking_produces_only_database_ids_and_preserves_missing_values():
    e = build_evidence(
        None, [("get_ranking", {"ranking": [row(), row(9, rps=None)]})], load_detail=detail
    )
    assert e.map_ids == [7, 9]
    assert e.cards[1].rps is None
    assert e.tables[0].rows[1][4] is None
    assert e.charts[0].points[0].value == 12
    assert "Ewidencja testowa — Test" in e.sources and "Rozkład testowy" in e.sources
    assert len(e.charts) == 1  # rankings do not create dozens of component charts


def test_no_ids_are_inferred_from_model_text_or_names():
    e = build_evidence(
        None,
        [("get_ranking", {"ranking": [{"numer": "7"}]})],
        load_detail=lambda *_: pytest.fail("unexpected read"),
    )
    assert e.map_ids == [] and e.cards == []
    assert build_evidence(None, []).model_dump() == Evidence().model_dump()


@pytest.mark.parametrize(
    "measured,expected,status", [(True, 1200, "measured"), (False, 900, "modelled")]
)
def test_detail_charts_distinguish_measurements_estimates_and_missing_values(
    measured, expected, status
):
    e = build_evidence(
        None, [("get_crossing", row())], load_detail=lambda *_: detail(measured=measured)
    )
    traffic = next(c for c in e.charts if c.unit == "pojazdy / dobę")
    assert (traffic.points[0].value, traffic.points[0].status) == (expected, status)
    components = next(c for c in e.charts if c.unit == "pkt / 100")
    assert components.points[1].value is None
    weekend = next(c for c in e.charts if c.unit == "pociągi / dzień")
    assert weekend.points[1].value is None and weekend.points[2].value == 0
    if measured:
        assert any("2026-10-28" in n and "Testowa" in n for n in e.notes)


def test_comparison_deduplicates_objects_and_repeated_calls():
    e = build_evidence(
        None,
        [("compare_crossings", {"a": row(), "b": row(9)}), ("get_crossing", row())],
        load_detail=detail,
    )
    assert e.map_ids == [7, 9] and len(e.cards) == 2
    assert len([c for c in e.charts if c.unit == "pkt / 100"]) == 2


@pytest.mark.parametrize("value", [-1, 0, "7", True])
def test_evidence_rejects_invalid_map_identifiers(value):
    with pytest.raises(ValidationError):
        Evidence(map_ids=[value])


def test_attachment_is_read_before_inference_and_included_in_evidence(monkeypatch):
    sent = []

    def handle(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": []})
        sent.append(__import__("json").loads(request.content))
        return httpx.Response(200, json={"message": {"content": "Opis dołączonego przejazdu."}})

    service._thinking_models.clear()
    monkeypatch.setattr(
        service,
        "build_evidence",
        lambda conn, results: Evidence(map_ids=[r["crossing_id"] for _, r in results]),
    )
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        answer = service.chat(
            None, client, "http://test", "test", "Jaki ruch?", attached_crossing=row()
        )
    assert answer.grounded and answer.evidence.map_ids == [7]
    assert answer.tool_calls[0].name == "attached_crossing"
    assert sent[0]["messages"][-1]["role"] == "tool"
    assert "021 003 504" in sent[0]["messages"][-1]["content"]


@pytest.fixture
def client():
    settings = Settings(_env_file=None, postgres_password="test")
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_connection] = lambda: None
    app.dependency_overrides[api.get_http_client] = lambda: httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(500))
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("value", [-1, 0, "7", True])
def test_endpoint_rejects_invalid_attachment(client, value):
    assert (
        client.post(
            "/api/v1/assistant/chat", json={"message": "Pytanie", "crossing_id": value}
        ).status_code
        == 422
    )


def test_missing_attachment_returns_404_without_calling_model(client, monkeypatch):
    def missing(*_):
        raise ToolError("Nie ma przejazdu o takim identyfikatorze.")

    monkeypatch.setattr(api, "get_attached_crossing", missing)
    monkeypatch.setattr(
        api, "chat", lambda *_args, **_kwargs: pytest.fail("model must not be called")
    )
    assert (
        client.post(
            "/api/v1/assistant/chat", json={"message": "Pytanie", "crossing_id": 999}
        ).status_code
        == 404
    )


def test_text_only_response_stays_compatible(client, monkeypatch):
    monkeypatch.setattr(
        api,
        "chat",
        lambda *_args, **_kwargs: service.AssistantReply(answer="Opis metody", model="test"),
    )
    body = client.post("/api/v1/assistant/chat", json={"message": "Co to WPO?"}).json()
    assert body["answer"] == "Opis metody" and body["evidence"]["map_ids"] == []
