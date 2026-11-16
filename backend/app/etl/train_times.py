"""Godzina przejazdu pociągu przez przejazd i profil dobowy (RSA-018), metoda `gtfs-time-1`.

Rozkład GTFS podaje godziny tylko na przystankach. Godzinę przejazdu wyznaczamy tak:
1. punkt przejazdu i przystanki kursu są rzutowane na geometrię trasy (odległość
   wzdłuż trasy, lokalny układ metryczny),
2. przejazd leży między dwoma kolejnymi przystankami z godzinami; czas jest
   interpolowany liniowo między odjazdem z pierwszego a przyjazdem do drugiego.

Dokładność: kilka minut (stała prędkość między przystankami, geometria trasy z mapy
autora zbioru) — wystarcza do przydziału do godziny. Kurs, którego przystanki nie
obejmują przejazdu albo nie mają godzin, jest liczony jako „bez godziny”.

Profil jest według dnia kalendarzowego przejazdu: kurs dnia D, który mija przejazd po
północy (godzina GTFS ≥ 24:00), trafia do wczesnych godzin dnia D+1. Suma profilu może
się więc nieznacznie różnić od liczby kursów na dobę liczonej według dnia kursowania.
"""

import math
from dataclasses import dataclass
from datetime import date, timedelta

from app.etl.gtfs import Feed

METHOD_VERSION = "gtfs-time-1"
DAY_S = 86_400
# Godziny szczytu drogowego przyjmowane, gdy nie ma pomiaru ZDM z profilem godzinowym.
ROAD_PEAK_HOURS = (7, 8, 15, 16, 17)
NIGHT_HOURS = (22, 23, 0, 1, 2, 3, 4, 5)


def _project(line: list[tuple[float, float]], point: tuple[float, float]) -> tuple[float, float]:
    """(odległość wzdłuż linii, odległość od linii) w metrach, rzut na najbliższy odcinek."""
    lat0 = math.radians(point[1])
    kx, ky = 111_320.0 * math.cos(lat0), 110_540.0

    def xy(p: tuple[float, float]) -> tuple[float, float]:
        return p[0] * kx, p[1] * ky

    px, py = xy(point)
    best = (math.inf, 0.0)  # (odległość od linii, odległość wzdłuż)
    walked = 0.0
    for a, b in zip(line, line[1:], strict=False):
        ax, ay = xy(a)
        bx, by = xy(b)
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        t = 0.0
        if length > 0:
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length**2))
        off = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
        if off < best[0]:
            best = (off, walked + t * length)
        walked += length
    return best[1], best[0]


@dataclass
class ShapeIndex:
    """Położenie przejazdu i przystanków wzdłuż jednej trasy (z pamięcią podręczną)."""

    feed: Feed
    shape_id: str
    crossing_at: float
    _stops: dict[str, float]

    @classmethod
    def build(cls, feed: Feed, shape_id: str, crossing: tuple[float, float]) -> "ShapeIndex":
        return cls(feed, shape_id, _project(feed.shapes[shape_id], crossing)[0], {})

    def stop_at(self, stop_id: str) -> float | None:
        if stop_id not in self._stops:
            point = self.feed.stops.get(stop_id)
            self._stops[stop_id] = (
                math.nan if point is None else _project(self.feed.shapes[self.shape_id], point)[0]
            )
        value = self._stops[stop_id]
        return None if math.isnan(value) else value

    def passage(self, trip_id: str) -> int | None:
        """Sekundy od północy dnia kursowania, gdy kurs mija przejazd; inaczej None."""
        rows = [
            (at, arr, dep)
            for stop, arr, dep in self.feed.stop_times.get(trip_id, [])
            if (at := self.stop_at(stop)) is not None
        ]
        c = self.crossing_at
        for (a1, _arr1, dep1), (a2, arr2, _dep2) in zip(rows, rows[1:], strict=False):
            low, high = min(a1, a2), max(a1, a2)
            if low <= c <= high:
                share = 0.0 if high == low else abs(c - a1) / (high - low)
                return round(dep1 + share * (arr2 - dep1))
        return None


def hourly_profile(
    feed: Feed, shape_ids: list[str], crossing: tuple[float, float], day: date
) -> tuple[list[int], int]:
    """(liczba kursów w każdej godzinie dnia kalendarzowego, kursy bez wyznaczonej godziny)."""
    counts = [0] * 24
    unplaced = 0
    previous = day - timedelta(days=1)
    for shape_id in shape_ids:
        if shape_id not in feed.shapes:
            continue
        index = ShapeIndex.build(feed, shape_id, crossing)
        for trip_id, service in feed.trips.get(shape_id, []):
            dates = feed.service_dates.get(service, ())
            today, yesterday = day in dates, previous in dates
            if not (today or yesterday):
                continue
            seconds = index.passage(trip_id)
            if seconds is None:
                unplaced += today
                continue
            if today and seconds < DAY_S:
                counts[seconds // 3600] += 1
            if yesterday and DAY_S <= seconds < 2 * DAY_S:
                counts[(seconds - DAY_S) // 3600] += 1
    return counts, unplaced


def profile_stats(profile: list[float], road_peaks: tuple[int, ...] = ROAD_PEAK_HOURS) -> dict:
    """Wskaźniki do karty i raportu: maksimum na godzinę, pociągi w szczycie drogowym, nocą."""
    return {
        "max_per_hour": max(profile) if profile else 0,
        "max_hour": max(range(24), key=lambda h: profile[h]) if any(profile) else None,
        "in_road_peaks": round(sum(profile[h] for h in road_peaks), 1),
        "at_night": round(sum(profile[h] for h in NIGHT_HOURS), 1),
        "total": round(sum(profile), 1),
    }
