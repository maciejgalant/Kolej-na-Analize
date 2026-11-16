"""Kolej na Analizę — backend FastAPI (szkielet, RSA-002)."""

from fastapi import FastAPI

from app.api import assistant, crossings, health, incidents, rail
from app.config import APP_VERSION

app = FastAPI(
    title="Kolej na Analizę API",
    version=APP_VERSION,
    description=(
        "Projekt edukacyjny, niezależny. Wyniki to priorytet do dalszej oceny, "
        "nie prognoza wypadków ani urzędowa klasyfikacja przejazdów."
    ),
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
    redoc_url=None,
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(crossings.router, prefix="/api/v1")
app.include_router(assistant.router, prefix="/api/v1")
app.include_router(rail.router, prefix="/api/v1")
app.include_router(incidents.router, prefix="/api/v1")
