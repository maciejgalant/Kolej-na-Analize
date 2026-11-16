from fastapi.testclient import TestClient

from app.api.rail import get_plk
from app.config import Settings, get_settings
from app.main import app
from app.plk import PlkClient


def test_disabled_status_and_error_do_not_expose_secret():
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, plk_api_key="")
    app.dependency_overrides[get_plk] = lambda: PlkClient("")
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/rail/status").json()["configured"] is False
            response = client.get("/api/v1/rail/operations?station_id=123")
            assert response.status_code == 503
            assert response.json()["detail"]["code"] == "not_configured"
            assert client.get("/api/v1/rail/operations?station_id=-1").status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_operations_preserve_page_and_request_plan():
    class Fake:
        def fetch(self, endpoint, params):
            assert endpoint == "operations"
            assert params == {
                "stations": "123",
                "page": 2,
                "pageSize": 100,
                "withPlanned": "true",
                "fullRoutes": "false",
            }
            return {"data": {"trains": [], "pagination": {"totalPages": 3}}}

    app.dependency_overrides[get_plk] = lambda: Fake()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/rail/operations?station_id=123&page=2")
            assert response.status_code == 200
            assert response.json()["data"]["pagination"]["totalPages"] == 3
    finally:
        app.dependency_overrides.clear()
