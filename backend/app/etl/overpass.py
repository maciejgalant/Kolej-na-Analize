"""Punkty przejazdów i przejść z OpenStreetMap (Overpass API) do kontroli krzyżowej."""

from dataclasses import dataclass

import httpx

from app.etl.utk_wms import USER_AGENT

OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
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


class OverpassUnavailable(RuntimeError):
    """Żaden serwer Overpass nie odpowiedział."""


def build_query(south: float, west: float, north: float, east: float) -> str:
    return QUERY.format(south=south, west=west, north=north, east=east).strip()


def _default_transports() -> list[httpx.BaseTransport | None]:
    # Najpierw wymuszone IPv4: w kontenerach Dockera bez trasy IPv6 połączenie
    # z adresem AAAA kończy się błędem "Network is unreachable".
    return [httpx.HTTPTransport(local_address="0.0.0.0", retries=1), None]


def fetch_osm_crossings(
    south: float,
    west: float,
    north: float,
    east: float,
    urls: tuple[str, ...] = OVERPASS_URLS,
    transports: list[httpx.BaseTransport | None] | None = None,
) -> list[OsmCrossing]:
    """Pobiera punkty z pierwszego działającego serwera Overpass."""
    query = build_query(south, west, north, east)
    errors = []
    for url in urls:
        for transport in transports if transports is not None else _default_transports():
            try:
                with httpx.Client(
                    transport=transport, timeout=120.0, headers={"User-Agent": USER_AGENT}
                ) as client:
                    response = client.post(url, data={"data": query})
                    response.raise_for_status()
                    return parse_overpass(response.json())
            except (httpx.HTTPError, ValueError, OSError) as error:
                errors.append(f"{url}: {error}")
    raise OverpassUnavailable("; ".join(errors))
