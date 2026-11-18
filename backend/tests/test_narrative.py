import httpx
import pytest
from pydantic import ValidationError

from app.api.assistant import ChatRequest
from app.assistant import service
from app.assistant.narrative import detail_text, ranking_text, recommendation_text
from app.assistant.presentation import Evidence


def row(i):
    return {
        "crossing_id": i,
        "numer": f"TEST-{i}",
        "dzielnica": "Wola",
        "kategoria": "D",
        "rps": 80.4,
        "kompletnosc_proc": 90,
        "pociagi_pasazerskie_dzien_roboczy_plan": 100,
        "skladniki": {
            "T": {
                "wartosc": 80,
                "waga": 0.4,
                "szczegoly": {"vehicles_source": "model", "vehicles_per_day_model": 2500},
            },
            "P": {"wartosc": 100, "waga": 0.3, "szczegoly": {}},
            "G": {"wartosc": 20, "waga": 0.2, "szczegoly": {"tracks": 2, "angle_deg": 89}},
            "H": {"wartosc": None, "waga": 0.1, "szczegoly": {}},
        },
    }


def test_ranking_is_short_and_asks_about_same_five():
    text = ranking_text([row(i) for i in range(1, 6)])
    assert text.count("**Numer:**") == 5
    assert "80,4" in text and "Czy chcesz więcej szczegółów o tych 5" in text
    assert "nie oznacza niebezpieczności" in text


@pytest.mark.parametrize("question", ["Więcej szczegółów", "Tak, więcej informacji", "tak"])
def test_followup_reads_exact_same_ids_without_reranking(monkeypatch, question):
    reads = []

    def read(conn, crossing_id):
        reads.append(crossing_id)
        return row(crossing_id)

    monkeypatch.setattr(service, "get_attached_crossing", read)
    monkeypatch.setattr(
        service,
        "build_evidence",
        lambda conn, results: Evidence(map_ids=[r["crossing_id"] for _, r in results]),
    )
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: pytest.fail("No model needed"))
    ) as http:
        reply = service.chat(
            None, http, "http://model", "test", question, analysis_crossing_ids=[5, 2, 8, 9, 3]
        )
    assert reads == [5, 2, 8, 9, 3]
    assert reply.evidence.map_ids == reads and reply.grounded
    assert reply.answer.count("**TEST-") == 5


def test_attached_crossing_takes_precedence_over_old_ranking(monkeypatch):
    monkeypatch.setattr(
        service,
        "build_evidence",
        lambda conn, results: Evidence(map_ids=[r["crossing_id"] for _, r in results]),
    )
    monkeypatch.setattr(service, "get_attached_crossing", lambda *a: pytest.fail("Old scope read"))
    with httpx.Client() as http:
        reply = service.chat(
            None,
            http,
            "http://model",
            "test",
            "Dlaczego taka wartość WPO?",
            attached_crossing=row(7),
            analysis_crossing_ids=[1, 2, 3, 4, 5],
        )
    assert reply.evidence.map_ids == [7]
    assert "Największy wkład" in reply.answer and "35,6 pkt" in reply.answer


def test_recommendations_are_proposals_and_do_not_claim_defects():
    text = recommendation_text([row(7)])
    assert "pomiar ruchu drogowego" in text
    assert "nie potwierdzają usterki" in text
    assert "uzgodnienia z zarządcą" in text


def test_missing_values_are_not_zero_or_measured():
    text = detail_text([{"numer": "MISSING", "skladniki": {}, "rps": None}])
    assert "brak danych" in text and "Największy wkład" not in text
    assert "brak danych°" not in text


@pytest.mark.parametrize("ids", [[0], [-1], ["7"], [True], list(range(1, 17))])
def test_analysis_scope_validation(ids):
    with pytest.raises(ValidationError):
        ChatRequest(message="Więcej szczegółów", analysis_crossing_ids=ids)


def test_initial_ranking_caps_model_request_and_uses_verified_rows(monkeypatch):
    calls = []

    def call(conn, name, args):
        calls.append((name, args))
        return {"ranking": [row(i) for i in range(1, 6)]}

    monkeypatch.setattr(service, "call_tool", call)
    monkeypatch.setattr(
        service,
        "build_evidence",
        lambda conn, results: Evidence(
            map_ids=[r["crossing_id"] for r in results[0][1]["ranking"]]
        ),
    )
    count = [0]

    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": []})
        count[0] += 1
        message = (
            {"tool_calls": [{"function": {"name": "get_ranking", "arguments": {"limit": 15}}}]}
            if count[0] == 1
            else {"content": "Unverified prose"}
        )
        return httpx.Response(200, json={"message": message})

    service._thinking_models.clear()
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = service.chat(
            None, http, "http://model", "test", "Które przejazdy mają najwyższy priorytet?"
        )
    assert calls == [("get_ranking", {"limit": 5})]
    assert result.evidence.presentation == "ranking_summary"
    assert result.evidence.map_ids == [1, 2, 3, 4, 5]
    assert "Unverified prose" not in result.answer
