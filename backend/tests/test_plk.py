import httpx
import pytest

from app.plk import PlkClient, PlkError


def test_cache_keeps_payload_and_does_not_repeat_requests():
    calls = []
    clock = [0.0]

    def handler(request):
        calls.append(request)
        assert request.headers["X-API-Key"] == "private-key"
        assert "private-key" not in str(request.url)
        return httpx.Response(200, json={"trains": [], "generatedAt": "2026-11-16T12:00:00Z"})

    client = PlkClient("private-key", httpx.MockTransport(handler), lambda: clock[0])
    first = client.fetch("operations", {"stations": "123"})
    first["data"]["trains"].append({"changed": True})
    second = client.fetch("operations", {"stations": "123"})
    assert second["cached"] is True
    assert second["data"]["trains"] == []
    assert len(calls) == 1
    clock[0] = 301
    assert client.fetch("operations", {"stations": "123"})["cached"] is False
    assert len(calls) == 2


@pytest.mark.parametrize(
    "status,code",
    [(401, "unauthorized"), (403, "unauthorized"), (429, "rate_limited"), (500, "unavailable")],
)
def test_upstream_errors_are_sanitized_and_backed_off(status, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="sensitive upstream body private-key")

    client = PlkClient("private-key", httpx.MockTransport(handler))
    with pytest.raises(PlkError) as exc:
        client.fetch("operations", {"stations": "123"})
    assert exc.value.code == code
    assert "private-key" not in str(exc.value)
    with pytest.raises(PlkError, match="przerwy"):
        client.fetch("disruptions", {"stations": "123"})
    assert len(calls) == 1


def test_missing_key_does_not_connect():
    def handler(request):
        pytest.fail("No network request should be made")

    with pytest.raises(PlkError) as exc:
        PlkClient("", httpx.MockTransport(handler)).fetch("operations", {})
    assert exc.value.code == "not_configured"


@pytest.mark.parametrize("payload", [{}, [], {"trains": "bad"}])
def test_malformed_response_is_not_success(payload):
    client = PlkClient("key", httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))
    with pytest.raises(PlkError) as exc:
        client.fetch("operations", {})
    assert exc.value.code == "unavailable"


def test_page_and_station_are_distinct_cache_entries():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"trains": [], "pagination": {"totalPages": 2}})

    client = PlkClient("key", httpx.MockTransport(handler))
    for station, page in [(1, 1), (1, 2), (2, 1), (1, 1)]:
        client.fetch("operations", {"stations": str(station), "page": page})
    assert len(calls) == 3


def test_local_basic_budget():
    client = PlkClient(
        "key", httpx.MockTransport(lambda r: httpx.Response(200, json={"trains": []}))
    )
    for page in range(90):
        client.fetch("operations", {"page": page})
    with pytest.raises(PlkError) as exc:
        client.fetch("operations", {"page": 90})
    assert exc.value.code == "local_limit"


def test_timeout_is_sanitized():
    def handler(request):
        raise httpx.ReadTimeout("private-key")

    with pytest.raises(PlkError) as exc:
        PlkClient("private-key", httpx.MockTransport(handler)).fetch("operations", {})
    assert exc.value.code == "unavailable"
    assert "private-key" not in str(exc.value)
