"""Wykrywanie symboli przejazdów na obrazie WMS (PNG z przezroczystym tłem).

Usługa UTK w Geoportalu udostępnia tylko WMS: nie zwraca współrzędnych obiektów,
więc położenie odczytujemy ze środka narysowanego symbolu.
"""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image

ALPHA_THRESHOLD = 40


@dataclass(frozen=True)
class Blob:
    """Spójna grupa nieprzezroczystych pikseli; współrzędne w pikselach obrazu."""

    cx: float
    cy: float
    width: int
    height: int
    area: int
    touches_edge: bool


def find_blobs(png: bytes) -> tuple[list[Blob], int, int]:
    image = Image.open(BytesIO(png)).convert("RGBA")
    width, height = image.size
    alpha = image.getchannel("A").tobytes()
    pending = {i for i, value in enumerate(alpha) if value >= ALPHA_THRESHOLD}
    blobs: list[Blob] = []
    while pending:
        stack = [pending.pop()]
        sum_x = sum_y = count = 0
        min_x = min_y = max(width, height)
        max_x = max_y = 0
        while stack:
            index = stack.pop()
            y, x = divmod(index, width)
            sum_x += x
            sum_y += y
            count += 1
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
            for neighbour in (index - width, index + width):
                if neighbour in pending:
                    pending.remove(neighbour)
                    stack.append(neighbour)
            if x > 0 and index - 1 in pending:
                pending.remove(index - 1)
                stack.append(index - 1)
            if x < width - 1 and index + 1 in pending:
                pending.remove(index + 1)
                stack.append(index + 1)
        blobs.append(
            Blob(
                cx=sum_x / count,
                cy=sum_y / count,
                width=max_x - min_x + 1,
                height=max_y - min_y + 1,
                area=count,
                touches_edge=min_x == 0 or min_y == 0 or max_x == width - 1 or max_y == height - 1,
            )
        )
    return blobs, width, height
