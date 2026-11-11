"""Granice dzielnic Warszawy z Państwowego Rejestru Granic (WFS GUGiK)."""

from dataclasses import dataclass
from xml.etree import ElementTree

import httpx

from app.etl.utk_wms import USER_AGENT

PRG_WFS_URL = "https://mapy.geoportal.gov.pl/wss/service/PZGIK/PRG/WFS/AdministrativeBoundaries"
LAYER = "ms:A05_Granice_jednostek_ewidencyjnych"
# Dzielnice Warszawy to jednostki ewidencyjne o kodach 1465xx_8.
WARSAW_PREFIX = "1465"
NAME_SUFFIX = " - dzielnica"


@dataclass(frozen=True)
class District:
    teryt: str
    name: str
    wkt: str  # MULTIPOLYGON w EPSG:2180, kolejność osi wschód-północ


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _ring(pos_list: str) -> str:
    # Usługa zwraca współrzędne w kolejności osi układu: północ, wschód.
    values = pos_list.split()
    pairs = zip(values[1::2], values[0::2], strict=True)
    return "(" + ",".join(f"{east} {north}" for east, north in pairs) + ")"


def _polygon(element: ElementTree.Element) -> str:
    rings = []
    for part in ("exterior", "interior"):
        for boundary in element:
            if _local(boundary.tag) != part:
                continue
            for node in boundary.iter():
                if _local(node.tag) == "posList" and node.text:
                    rings.append(_ring(node.text))
    return "(" + ",".join(rings) + ")"


def parse_districts(xml_text: str) -> list[District]:
    root = ElementTree.fromstring(xml_text)
    districts = []
    for feature in root.iter():
        if _local(feature.tag) != LAYER.split(":")[1]:
            continue
        fields = {_local(child.tag): (child.text or "").strip() for child in feature}
        teryt = fields.get("JPT_KOD_JE", "")
        if not teryt.startswith(WARSAW_PREFIX):
            continue
        polygons = [_polygon(node) for node in feature.iter() if _local(node.tag) == "Polygon"]
        if not polygons:
            continue
        districts.append(
            District(
                teryt=teryt,
                name=fields.get("JPT_NAZWA_", "").removesuffix(NAME_SUFFIX),
                wkt="MULTIPOLYGON(" + ",".join(polygons) + ")",
            )
        )
    return districts


def fetch_districts(
    e_min: float, n_min: float, e_max: float, n_max: float, client: httpx.Client | None = None
) -> list[District]:
    owned = client is None
    client = client or httpx.Client(timeout=120.0, headers={"User-Agent": USER_AGENT})
    try:
        response = client.get(
            PRG_WFS_URL,
            params={
                "SERVICE": "WFS",
                "VERSION": "2.0.0",
                "REQUEST": "GetFeature",
                "TYPENAMES": LAYER,
                "SRSNAME": "urn:ogc:def:crs:EPSG::2180",
                "BBOX": f"{n_min},{e_min},{n_max},{e_max},urn:ogc:def:crs:EPSG::2180",
            },
        )
        response.raise_for_status()
        return parse_districts(response.text)
    finally:
        if owned:
            client.close()
