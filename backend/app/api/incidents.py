"""Częściowy wykaz SEWiK; zgodność ulicy nie potwierdza przejazdu."""

import unicodedata

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.api.crossings import Connection

router = APIRouter(tags=["historia zdarzeń"])
NOTICE = (
    "Częściowy wykaz przepisany ze zrzutu SEWiK przekazanego 16.11.2026. "
    "Nie jest pełną statystyką Warszawy. Puste skutki oznaczają brak informacji, nie zero. "
    "Wpisy nie zmieniają RPS; przypisanie do przejazdów wymaga weryfikacji."
)


class Incident(BaseModel):
    source_object_id: str
    occurred_on: str
    local_time: str
    address: str
    street_keys: list[str]
    incident_type: str
    place: str
    injured: int | None
    killed: int | None
    crossing_id: int | None
    confirmed: bool
    location_confidence: str


class IncidentHistory(BaseModel):
    source: str = "SEWiK / sewik.pl — zrzut użytkownika"
    source_url: str = "https://sewik.pl/"
    coverage: str = "partial"
    scope: str = "warsaw"
    notice: str = NOTICE
    records: list[Incident]


def load_incidents(conn: Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT i.source_object_id, i.occurred_on::text AS occurred_on,
               i.incident_type, i.crossing_id, i.confirmed, i.location_confidence,
               i.metadata
        FROM safety.incidents i JOIN system.sources s USING (source_id)
        WHERE s.code = 'sewik_user_snapshot'
        ORDER BY i.occurred_on DESC, i.source_object_id DESC
        """
    ).fetchall()
    return [
        dict(row["metadata"]) | {k: v for k, v in row.items() if k != "metadata"} for row in rows
    ]


def _street(value: str) -> str:
    value = value.lower().replace("ł", "l")
    value = "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))
    return " ".join(value.replace("ul.", "").split()).removeprefix("jozefa ")


def street_candidates(records: list[dict], streets: list[str]) -> list[dict]:
    """Tylko wskazówki adresowe. Bez zapisu crossing_id ani geokodowania ulicy."""
    names = {_street(s).removeprefix("jozefa ") for s in streets}
    return [r for r in records if names.intersection(_street(k) for k in r["street_keys"])]


@router.get("/incidents", response_model=IncidentHistory)
def incidents(conn: Connection, crossing_id: int | None = Query(None, gt=0)) -> IncidentHistory:
    records = load_incidents(conn)
    if crossing_id is None:
        return IncidentHistory(records=records)
    crossing = conn.execute(
        "SELECT name FROM spatial.crossings WHERE crossing_id = %s", (crossing_id,)
    ).fetchone()
    if crossing is None:
        raise HTTPException(404, "Nie ma przejazdu o takim identyfikatorze.")
    streets = conn.execute(
        "SELECT DISTINCT r.road_name FROM spatial.crossing_road_segments l "
        "JOIN spatial.road_segments r USING (segment_id) "
        "WHERE l.crossing_id = %s AND r.road_name IS NOT NULL",
        (crossing_id,),
    ).fetchall()
    candidates = street_candidates(records, [s["road_name"] for s in streets])
    if (crossing["name"] or "").startswith("DEMO-"):
        candidates = []
    return IncidentHistory(scope="street_candidates", records=candidates)
