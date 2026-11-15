"""Klient usługi WMS „Przejazdy kolejowe” (UTK, utrzymywana przez GUGiK)."""

import time
from dataclasses import dataclass
from typing import Protocol
from xml.etree import ElementTree

import httpx

WMS_URL = "https://mapy.geoportal.gov.pl/wss/service/sdi/Przejazdy/get"
# Zarządcy, których infrastruktura leży w Warszawie lub tuż obok.
DEFAULT_LAYERS = (
    "PKP_Polskie_Linie_Kolejowe",
    "Warszawska_Kolej_Dojazdowa",
    "PGNiG_TERMIKA_SA",
    "CARGOTOR_Sp__z_o_o_",
)
USER_AGENT = "KolejNaAnalize/0.1 (projekt edukacyjny; github.com/maciejgalant/Kolej-na-Analize)"


@dataclass(frozen=True)
class Window:
    """Kwadratowy wycinek mapy w EPSG:2180 renderowany jako obraz `pixels` x `pixels`."""

    e_min: float
    n_min: float
    size_m: float
    pixels: int

    @property
    def m_per_px(self) -> float:
        return self.size_m / self.pixels

    @property
    def wms_bbox(self) -> str:
        # WMS 1.3.0 + EPSG:2180: kolejność osi to północ, wschód.
        e_max, n_max = self.e_min + self.size_m, self.n_min + self.size_m
        return f"{self.n_min},{self.e_min},{n_max},{e_max}"

    def to_map(self, px: float, py: float) -> tuple[float, float]:
        east = self.e_min + (px + 0.5) * self.m_per_px
        north = self.n_min + self.size_m - (py + 0.5) * self.m_per_px
        return east, north

    def to_pixel(self, east: float, north: float) -> tuple[int, int]:
        px = round((east - self.e_min) / self.m_per_px - 0.5)
        py = round((self.n_min + self.size_m - north) / self.m_per_px - 0.5)
        return px, py

    @classmethod
    def centred(cls, east: float, north: float, size_m: float, pixels: int) -> "Window":
        return cls(east - size_m / 2, north - size_m / 2, size_m, pixels)


@dataclass(frozen=True)
class WmsFeature:
    layer: str
    name: str
    category_raw: str
    location_type: str
    manager: str

    @property
    def key(self) -> str:
        return f"{self.layer}:{self.name}"


def parse_feature_info(xml_text: str) -> list[WmsFeature]:
    """Parsuje odpowiedź GetFeatureInfo (text/xml, format GeoMedia)."""
    root = ElementTree.fromstring(xml_text)
    features = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "Layer":
            continue
        attrs = {
            child.get("Name"): (child.text or "").strip()
            for child in element
            if child.tag.rsplit("}", 1)[-1] == "Attribute"
        }
        name = attrs.get("NAZWA", "")
        if not name:
            continue
        features.append(
            WmsFeature(
                layer=element.get("Name", ""),
                name=name,
                category_raw=attrs.get("KATEGORIA", ""),
                location_type=attrs.get("STAC_SZLAK", ""),
                manager=attrs.get("IDDE", ""),
            )
        )
    return features


class WmsRenderError(RuntimeError):
    """Usługa odpowiedziała wyjątkiem zamiast obrazu.

    Zdarza się to dla konkretnych prostokątów (błąd po stronie serwera) i znika
    po przesunięciu okna o kilka metrów, więc wywołujący ponawia z innym oknem.
    """


class CrossingsWms(Protocol):
    def get_map(self, window: Window) -> bytes: ...

    def get_feature_info(self, window: Window, px: int, py: int) -> list[WmsFeature]: ...


class UtkWmsClient:
    def __init__(
        self,
        url: str = WMS_URL,
        layers: tuple[str, ...] = DEFAULT_LAYERS,
        delay_s: float = 0.15,
        timeout_s: float = 60.0,
        retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._url = url
        self._layers = ",".join(layers)
        self._delay_s = delay_s
        self._retries = retries
        self._http = httpx.Client(
            timeout=timeout_s, headers={"User-Agent": USER_AGENT}, transport=transport
        )
        self.requests_made = 0

    def close(self) -> None:
        self._http.close()

    def _get(self, params: dict[str, str | int]) -> httpx.Response:
        base = {
            "SERVICE": "WMS",
            "VERSION": "1.3.0",
            "LAYERS": self._layers,
            "STYLES": "",
            "CRS": "EPSG:2180",
            "FORMAT": "image/png",
        }
        last_error: Exception | None = None
        for attempt in range(self._retries):
            time.sleep(self._delay_s * (1 + 4 * attempt))
            try:
                self.requests_made += 1
                response = self._http.get(self._url, params=base | params)
                response.raise_for_status()
                return response
            except httpx.HTTPError as error:
                last_error = error
        raise RuntimeError(f"Usługa WMS przejazdów nie odpowiada: {last_error}") from last_error

    def get_map(self, window: Window) -> bytes:
        response = self._get(
            {
                "REQUEST": "GetMap",
                "BBOX": window.wms_bbox,
                "WIDTH": window.pixels,
                "HEIGHT": window.pixels,
                "TRANSPARENT": "TRUE",
            }
        )
        if "image" not in response.headers.get("content-type", ""):
            raise WmsRenderError(f"WMS zwrócił błąd zamiast obrazu: {response.text[:300]}")
        return response.content

    def get_feature_info(self, window: Window, px: int, py: int) -> list[WmsFeature]:
        response = self._get(
            {
                "REQUEST": "GetFeatureInfo",
                "QUERY_LAYERS": self._layers,
                "BBOX": window.wms_bbox,
                "WIDTH": window.pixels,
                "HEIGHT": window.pixels,
                "I": px,
                "J": py,
                "FEATURE_COUNT": 50,
                "INFO_FORMAT": "text/xml",
            }
        )
        return parse_feature_info(response.text)
