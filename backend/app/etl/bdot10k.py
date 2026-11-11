"""Tory (OT_SKTR_L) i jezdnie (OT_SKJZ_L) z paczki GML BDOT10k."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import IO
from xml.etree import ElementTree

BDOT_URL = "https://opendata.geoportal.gov.pl/bdot10k/schemat2021/14/1465_GML.zip"
GROUND_LEVEL = "na powierzchni gruntu"
RAILWAY_VEHICLE = "kolej"  # pomijamy tramwaj i metro


@dataclass(frozen=True)
class Segment:
    local_id: str
    attributes: dict[str, str]
    # Wierzchołki (east, north) w EPSG:2180.
    points: tuple[tuple[float, float], ...]

    @property
    def wkt(self) -> str:
        return "LINESTRING(" + ",".join(f"{e} {n}" for e, n in self.points) + ")"

    def bbox(self) -> tuple[float, float, float, float]:
        easts = [p[0] for p in self.points]
        norths = [p[1] for p in self.points]
        return min(easts), min(norths), max(easts), max(norths)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def iter_segments(stream: IO[bytes], feature_tag: str) -> Iterator[Segment]:
    """Strumieniowo czyta obiekty liniowe; w BDOT10k `posList` ma kolejność wschód, północ."""
    for _event, element in ElementTree.iterparse(stream, events=("end",)):
        name = _local(element.tag)
        if name == "featureMember":
            element.clear()
            continue
        if name != feature_tag:
            continue
        attributes: dict[str, str] = {}
        points: list[tuple[float, float]] = []
        for child in element:
            child_name = _local(child.tag)
            if child_name == "geometria":
                for node in child.iter():
                    if _local(node.tag) == "posList" and node.text:
                        values = [float(v) for v in node.text.split()]
                        for east, north in zip(values[0::2], values[1::2], strict=True):
                            if not points or points[-1] != (east, north):
                                points.append((east, north))
            elif child.text and child.text.strip():
                attributes[child_name] = child.text.strip()
        if len(points) >= 2 and attributes.get("lokalnyId"):
            yield Segment(attributes["lokalnyId"], attributes, tuple(points))


def near_any_point(points: list[tuple[float, float]], margin_m: float) -> Callable[[Segment], bool]:
    """Filtr zgrubny: prostokąt odcinka powiększony o margines zawiera któryś z punktów."""

    def check(segment: Segment) -> bool:
        e_min, n_min, e_max, n_max = segment.bbox()
        return any(
            e_min - margin_m <= east <= e_max + margin_m
            and n_min - margin_m <= north <= n_max + margin_m
            for east, north in points
        )

    return check


def find_member(names: list[str], suffix: str) -> str:
    matches = [name for name in names if name.endswith(suffix)]
    if len(matches) != 1:
        raise RuntimeError(
            f"W paczce BDOT10k oczekiwano jednego pliku *{suffix}, jest {len(matches)}"
        )
    return matches[0]
