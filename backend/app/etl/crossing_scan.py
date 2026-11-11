"""Odczyt przejazdów z WMS UTK: położenie z symbolu, atrybuty z GetFeatureInfo.

Dwa etapy:
1. przegląd zgrubny — kafle 4 m/px, każdy symbol (lub zlepek symboli) daje punkt startowy;
2. doprecyzowanie — okno 1 m/px wokół punktu, środek symbolu = położenie przejazdu,
   zapytanie GetFeatureInfo w tym miejscu = numer, kategoria i zarządca.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from app.etl.symbols import Blob, find_blobs
from app.etl.utk_wms import CrossingsWms, Window, WmsFeature, WmsRenderError

COARSE_TILE_M = 4096.0
COARSE_PIXELS = 1024
COARSE_OVERLAP_M = 256.0
FINE_PIXELS = 512
FINE_M_PER_PX = 1.0
# Pojedynczy symbol przy 1 m/px ma ok. 46 x 25 px; większy zlepek to kilka przejazdów obok siebie.
SINGLE_SYMBOL_MAX_W = 54
SINGLE_SYMBOL_MAX_H = 32
# Zapytanie dokładnie w środku symbolu bywa puste, więc próbujemy też punktów obok.
PROBE_OFFSETS = ((0, 0), (-5, -4), (5, -4), (0, -8), (-5, 4), (5, 4))
GRID_STEP_PX = 6
SEED_MERGE_M = 20.0
# Serwer zwraca wyjątek dla niektórych prostokątów; pomaga przesunięcie okna o kilka metrów.
WINDOW_SHIFTS_M = ((0.0, 0.0), (7.0, 5.0), (-11.0, -9.0), (16.0, 16.0))


@dataclass(frozen=True)
class Bbox:
    e_min: float
    n_min: float
    e_max: float
    n_max: float

    def contains(self, east: float, north: float) -> bool:
        return self.e_min <= east <= self.e_max and self.n_min <= north <= self.n_max


@dataclass
class ScannedCrossing:
    feature: WmsFeature
    east: float
    north: float
    # True, gdy symbol zlewał się z sąsiednim i położenie wynika z siatki zapytań (ok. ±10 m).
    approximate: bool = False


@dataclass
class ScanResult:
    crossings: list[ScannedCrossing] = field(default_factory=list)
    # Symbole, dla których usługa nie zwróciła żadnego obiektu (east, north).
    unidentified: list[tuple[float, float]] = field(default_factory=list)
    coarse_tiles: int = 0
    seeds: int = 0


def coarse_windows(bbox: Bbox) -> Iterator[Window]:
    step = COARSE_TILE_M - COARSE_OVERLAP_M
    north = bbox.n_min
    while north < bbox.n_max:
        east = bbox.e_min
        while east < bbox.e_max:
            yield Window(east, north, COARSE_TILE_M, COARSE_PIXELS)
            east += step
        north += step


def _merge_seeds(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    kept: list[tuple[float, float]] = []
    for east, north in points:
        if all(abs(east - e) > SEED_MERGE_M or abs(north - n) > SEED_MERGE_M for e, n in kept):
            kept.append((east, north))
    return kept


def _render(wms: CrossingsWms, window: Window) -> tuple[Window, list[Blob]] | None:
    """Renderuje okno, w razie błędu serwera próbuje lekko przesuniętych okien."""
    for shift_e, shift_n in WINDOW_SHIFTS_M:
        shifted = Window(
            window.e_min + shift_e, window.n_min + shift_n, window.size_m, window.pixels
        )
        try:
            return shifted, find_blobs(wms.get_map(shifted))[0]
        except WmsRenderError:
            continue
    return None


def _probe(wms: CrossingsWms, window: Window, px: int, py: int) -> list[WmsFeature]:
    for dx, dy in PROBE_OFFSETS:
        x, y = px + dx, py + dy
        if 0 <= x < window.pixels and 0 <= y < window.pixels:
            found = wms.get_feature_info(window, x, y)
            if found:
                return found
    return []


def _probe_grid(wms: CrossingsWms, window: Window, blob: Blob) -> dict[str, ScannedCrossing]:
    """Dla zlepka symboli: siatka zapytań, położenie = środek pikseli z trafieniem."""
    hits: dict[str, tuple[WmsFeature, list[tuple[int, int]]]] = {}
    x0, x1 = round(blob.cx - blob.width / 2), round(blob.cx + blob.width / 2)
    y0, y1 = round(blob.cy - blob.height / 2), round(blob.cy + blob.height / 2)
    for y in range(max(0, y0), min(window.pixels, y1 + 1), GRID_STEP_PX):
        for x in range(max(0, x0), min(window.pixels, x1 + 1), GRID_STEP_PX):
            for feature in wms.get_feature_info(window, x, y):
                hits.setdefault(feature.key, (feature, []))[1].append((x, y))
    found = {}
    for key, (feature, pixels) in hits.items():
        mean_x = sum(p[0] for p in pixels) / len(pixels)
        mean_y = sum(p[1] for p in pixels) / len(pixels)
        east, north = window.to_map(mean_x, mean_y)
        found[key] = ScannedCrossing(feature, east, north, approximate=True)
    return found


def scan_crossings(
    wms: CrossingsWms, bbox: Bbox, log: Callable[[str], None] = lambda _m: None
) -> ScanResult:
    result = ScanResult()
    seeds: list[tuple[float, float]] = []
    for window in coarse_windows(bbox):
        result.coarse_tiles += 1
        rendered = _render(wms, window)
        if rendered is None:
            # Bez kafla przeglądu nie wiadomo, czego brakuje: lepiej przerwać niż zgubić obszar.
            raise RuntimeError(f"WMS nie renderuje kafla przeglądu {window.wms_bbox}")
        window, blobs = rendered
        seeds.extend(window.to_map(blob.cx, blob.cy) for blob in blobs)
    seeds = _merge_seeds(seeds)
    result.seeds = len(seeds)
    log(f"przegląd zgrubny: {result.coarse_tiles} kafli, {len(seeds)} punktów startowych")

    found: dict[str, ScannedCrossing] = {}
    unidentified: list[tuple[float, float]] = []
    handled: list[tuple[float, float]] = []
    for number, (seed_e, seed_n) in enumerate(seeds, start=1):
        rendered = _render(
            wms, Window.centred(seed_e, seed_n, FINE_PIXELS * FINE_M_PER_PX, FINE_PIXELS)
        )
        if rendered is None:
            unidentified.append((seed_e, seed_n))
            continue
        window, blobs = rendered
        for blob in blobs:
            if blob.touches_edge:
                continue  # obcięty symbol; trafi do własnego okna z innego punktu startowego
            centre = window.to_map(blob.cx, blob.cy)
            if any(abs(centre[0] - e) < 3 and abs(centre[1] - n) < 3 for e, n in handled):
                continue  # ten sam symbol widziany już w sąsiednim oknie
            handled.append(centre)
            if blob.width > SINGLE_SYMBOL_MAX_W or blob.height > SINGLE_SYMBOL_MAX_H:
                grid = _probe_grid(wms, window, blob)
                if not grid:
                    unidentified.append(window.to_map(blob.cx, blob.cy))
                for key, crossing in grid.items():
                    found.setdefault(key, crossing)
                continue
            east, north = window.to_map(blob.cx, blob.cy)
            features = _probe(wms, window, round(blob.cx), round(blob.cy))
            if not features:
                unidentified.append((east, north))
            for feature in features:
                # Kilka obiektów pod jednym symbolem: wspólne położenie, oznaczone jako przybliżone.
                crossing = ScannedCrossing(feature, east, north, approximate=len(features) > 1)
                existing = found.get(feature.key)
                if existing is None or (existing.approximate and not crossing.approximate):
                    found[feature.key] = crossing
        if number % 25 == 0:
            log(f"doprecyzowanie: {number}/{len(seeds)}")

    result.crossings = [c for c in found.values() if bbox.contains(c.east, c.north)]
    identified = [(c.east, c.north) for c in found.values()]
    result.unidentified = [
        point
        for point in _merge_seeds(unidentified)
        if bbox.contains(*point)
        and all(abs(point[0] - e) > 30 or abs(point[1] - n) > 30 for e, n in identified)
    ]
    return result
