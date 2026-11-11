"""Punkty przejazdów i przejść z OpenStreetMap (Overpass API) do kontroli krzyżowej."""

from dataclasses import dataclass

import httpx

from app.etl.utk_wms import USER_AGENT

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
QUERY = """
[out:json][timeout:90];
way["railway"~"^(rail|light_rail|narrow_gauge)$"]({south},{west},{north},{east})->.tracks;
node(w.tracks)["railway"~"^(level_crossing|crossing)$"];
out body;
"""
KEPT_TAGS = (
    "railway",
    "ref",
    "crossing:barrier",
    "crossing:light",
    "crossing:bell",
    "crossing:saltire",
    "railway:position",
)


@dataclass(frozen=True)
class OsmCrossing:
    node_id: int
    lon: float
    lat: float
    tags: dict[str, str]


def parse_overpass(payload: dict) -> list[OsmCrossing]:
    crossings = []
    for element in payload.get("elements", []):
        if element.get("type") != "node":
            continue
        tags = element.get("tags", {})
        crossings.append(
            OsmCrossing(
                node_id=int(element["id"]),
                lon=float(element["lon"]),
                lat=float(element["lat"]),
                tags={key: tags[key] for key in KEPT_TAGS if key in tags},
            )
        )
    return crossings


def fetch_osm_crossings(
    south: float, west: float, north: float, east: float, url: str = OVERPASS_URL
) -> list[OsmCrossing]:
    query = QUERY.format(south=south, west=west, north=north, east=east)
    response = httpx.post(
        url, data={"data": query}, timeout=120.0, headers={"User-Agent": USER_AGENT}
    )
    response.raise_for_status()
    return parse_overpass(response.json())
