"""Station-level live context. Does not alter crossing evidence or RPS."""

from datetime import date
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import Settings, get_settings
from app.plk import PlkClient, PlkError

router = APIRouter(prefix="/rail", tags=["PKP PLK"])


@lru_cache(maxsize=1)
def _client(key: str) -> PlkClient:
    return PlkClient(key)


def get_plk(settings: Annotated[Settings, Depends(get_settings)]) -> PlkClient:
    return _client(settings.plk_api_key.get_secret_value().strip())


Client = Annotated[PlkClient, Depends(get_plk)]
Station = Annotated[int, Query(gt=0, le=2147483647)]
Page = Annotated[int, Query(ge=1, le=1000)]


def _fetch(client: PlkClient, endpoint: str, params: dict) -> dict:
    try:
        return client.fetch(endpoint, params)
    except PlkError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from None


@router.get("/status")
def status(settings: Annotated[Settings, Depends(get_settings)]):
    return {
        "configured": bool(settings.plk_api_key.get_secret_value().strip()),
        "scope": "station_context",
        "affects_rps": False,
    }


@router.get("/stations")
def stations(
    client: Client,
    search: Annotated[str, Query(min_length=2, max_length=80)] = "Warszawa",
    page: Page = 1,
):
    return _fetch(
        client, "dictionaries/stations", {"search": search.strip(), "page": page, "pageSize": 100}
    )


@router.get("/operations")
def operations(client: Client, station_id: Station, page: Page = 1):
    return _fetch(
        client,
        "operations",
        {
            "stations": str(station_id),
            "page": page,
            "pageSize": 100,
            "withPlanned": "true",
            "fullRoutes": "false",
        },
    )


@router.get("/disruptions")
def disruptions(client: Client, station_id: Station):
    return _fetch(client, "disruptions", {"stations": str(station_id)})


@router.get("/schedules")
def schedules(client: Client, station_id: Station, day: date):
    return _fetch(
        client,
        "schedules",
        {"stations": str(station_id), "dateFrom": day.isoformat(), "dateTo": day.isoformat()},
    )
