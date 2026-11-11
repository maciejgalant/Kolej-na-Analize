"""GET /api/v1/health — stan backendu i usług zależnych.

Endpoint zawsze odpowiada 200, gdy backend działa. Niedostępność PostGIS
lub Ollamy jest raportowana w polu `services` i obniża `status` do
`degraded`: brak modelu AI nie może blokować mapy ani trybu demo.
"""

from typing import Literal

import httpx
import psycopg
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import APP_VERSION, Settings, get_settings

router = APIRouter(tags=["system"])

ServiceState = Literal["ok", "unavailable"]


class DatabaseHealth(BaseModel):
    status: ServiceState
    postgis_version: str | None = None


class OllamaHealth(BaseModel):
    status: ServiceState
    model: str
    model_available: bool = False


class Services(BaseModel):
    database: DatabaseHealth
    ollama: OllamaHealth


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    demo_mode: bool
    services: Services


def check_database(settings: Settings) -> DatabaseHealth:
    try:
        with psycopg.connect(**settings.database_connect_kwargs) as conn:
            row = conn.execute("SELECT PostGIS_Lib_Version()").fetchone()
        return DatabaseHealth(status="ok", postgis_version=row[0] if row else None)
    except psycopg.Error:
        return DatabaseHealth(status="unavailable")


def check_ollama(settings: Settings) -> OllamaHealth:
    try:
        response = httpx.get(
            f"{settings.ollama_base_url}/api/tags", timeout=settings.healthcheck_timeout_s
        )
        response.raise_for_status()
        names = {m.get("name", "") for m in response.json().get("models", [])}
    except (httpx.HTTPError, ValueError):
        return OllamaHealth(status="unavailable", model=settings.ollama_model)
    wanted = settings.ollama_model
    available = wanted in names or f"{wanted}:latest" in names
    return OllamaHealth(status="ok", model=wanted, model_available=available)


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:  # noqa: B008
    database = check_database(settings)
    ollama = check_ollama(settings)
    all_ok = database.status == "ok" and ollama.status == "ok" and ollama.model_available
    return HealthResponse(
        status="ok" if all_ok else "degraded",
        version=APP_VERSION,
        demo_mode=settings.demo_mode,
        services=Services(database=database, ollama=ollama),
    )
