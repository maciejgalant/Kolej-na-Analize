"""Sztuczna usługa WMS do testów: rysuje symbole i odpowiada na GetFeatureInfo."""

from io import BytesIO

from PIL import Image, ImageDraw

from app.etl.utk_wms import Window, WmsFeature, WmsRenderError

ICON_W, ICON_H = 46, 25
HIT_RADIUS_PX = 9


class FakeWms:
    def __init__(self, features: list[tuple[WmsFeature, float, float]], dead_centre=False):
        self.features = features
        self.dead_centre = dead_centre  # naśladuje puste odpowiedzi dokładnie w środku symbolu
        self.broken_windows: set[tuple[float, float, float]] = set()
        self.fail_all_fine = False
        self.map_requests = 0
        self.info_requests = 0

    def get_map(self, window: Window) -> bytes:
        self.map_requests += 1
        key = (window.e_min, window.n_min, window.size_m)
        if key in self.broken_windows or (self.fail_all_fine and window.m_per_px <= 1):
            raise WmsRenderError("E_FAIL")
        image = Image.new("RGBA", (window.pixels, window.pixels), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        # Jak w prawdziwej usłudze: symbol ma stały rozmiar w pikselach, mniejszy w małej skali.
        w, h = (ICON_W, ICON_H) if window.m_per_px <= 1 else (32, 18)
        for _feature, east, north in self.features:
            px = (east - window.e_min) / window.m_per_px - 0.5
            py = (window.n_min + window.size_m - north) / window.m_per_px - 0.5
            draw.rectangle(
                [px - w / 2, py - h / 2, px + w / 2 - 1, py + h / 2 - 1], fill=(200, 0, 0, 255)
            )
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def get_feature_info(self, window: Window, px: int, py: int) -> list[WmsFeature]:
        self.info_requests += 1
        found = []
        for feature, east, north in self.features:
            fx, fy = window.to_pixel(east, north)
            if self.dead_centre and (fx, fy) == (px, py):
                continue
            if abs(fx - px) <= HIT_RADIUS_PX and abs(fy - py) <= HIT_RADIUS_PX:
                found.append(feature)
        return found
