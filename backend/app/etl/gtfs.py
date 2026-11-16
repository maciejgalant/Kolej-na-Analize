"""Otwarty rozkład pociągów pasażerskich w formacie GTFS (mkuran.pl, dane PKP PLK i KM).

Czytane są tylko pliki potrzebne do policzenia kursów: trasy (shapes), kursy (trips),
linie (routes) i kalendarz (calendar_dates), a do profilu godzinowego (RSA-018) także
przystanki (stops) i godziny (stop_times) — tylko dla kursów przez analizowany obszar.
Geometrie tras pochodzą z odręcznie utrzymywanej mapy autora zbioru, a nie z pomiaru
geodezyjnego.
"""

import csv
import io
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

GTFS_URL = "https://mkuran.pl/gtfs/polish_trains.zip"
# WKD nie korzysta z sieci PKP PLK, więc nie ma jej w zbiorze ogólnopolskim.
WKD_GTFS_URL = "https://mkuran.pl/gtfs/wkd.zip"
RAIL_ROUTE_TYPE = "2"


@dataclass
class Feed:
    version: str
    start: date
    end: date
    # shape_id -> [(lon, lat), ...] tylko dla tras kolejowych przecinających obszar
    shapes: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    # shape_id -> lista service_id kursów kolejowych jadących tą trasą
    trips_by_shape: dict[str, list[str]] = field(default_factory=dict)
    # service_id -> dni kursowania
    service_dates: dict[str, set[date]] = field(default_factory=dict)
    rail_trips: int = 0
    # Do profilu godzinowego (RSA-018); puste, gdy zbiór nie ma stop_times/stops.
    # shape_id -> [(trip_id, service_id)]
    trips: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    # trip_id -> [(stop_id, przyjazd [s od północy dnia kursu], odjazd [s])] w kolejności
    stop_times: dict[str, list[tuple[str, int, int]]] = field(default_factory=dict)
    # stop_id -> (lon, lat)
    stops: dict[str, tuple[float, float]] = field(default_factory=dict)


def _rows(archive: zipfile.ZipFile, name: str):
    with archive.open(name) as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))


def _day(text: str) -> date:
    return datetime.strptime(text.strip(), "%Y%m%d").date()


def _seconds(text: str | None) -> int | None:
    """'25:10:00' → 90 600 (godziny GTFS mogą przekraczać 24 dla kursów po północy)."""
    if not text or not text.strip():
        return None
    hours, minutes, seconds = (int(part) for part in text.strip().split(":"))
    return hours * 3600 + minutes * 60 + seconds


def read_feed(
    archive: zipfile.ZipFile, west: float, south: float, east: float, north: float
) -> Feed:
    names = set(archive.namelist())
    required = {"feed_info.txt", "routes.txt", "trips.txt", "shapes.txt", "calendar_dates.txt"}
    if missing := required - names:
        raise RuntimeError(f"W zbiorze GTFS brakuje plików: {sorted(missing)}")
    if "calendar.txt" in names and any(True for _ in _rows(archive, "calendar.txt")):
        raise RuntimeError("Zbiór używa calendar.txt — import obsługuje tylko calendar_dates.txt")

    info = next(_rows(archive, "feed_info.txt"))
    if info.get("feed_start_date") and info.get("feed_end_date"):
        start, end = _day(info["feed_start_date"]), _day(info["feed_end_date"])
    else:  # część zbiorów nie podaje zakresu: przyjmujemy skrajne daty kalendarza
        days = [
            _day(row["date"])
            for row in _rows(archive, "calendar_dates.txt")
            if row["exception_type"].strip() == "1"
        ]
        if not days:
            raise RuntimeError("Zbiór GTFS nie ma ani zakresu dat, ani dni kursowania.")
        start, end = min(days), max(days)
    feed = Feed(version=info.get("feed_version", ""), start=start, end=end)
    rail_routes = {
        row["route_id"] for row in _rows(archive, "routes.txt")
        if row["route_type"].strip() == RAIL_ROUTE_TYPE
    }  # fmt: skip
    trips_by_shape: dict[str, list[str]] = defaultdict(list)
    trip_list: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in _rows(archive, "trips.txt"):
        if row["route_id"] in rail_routes and row.get("shape_id"):
            trips_by_shape[row["shape_id"]].append(row["service_id"])
            trip_list[row["shape_id"]].append((row["trip_id"], row["service_id"]))
            feed.rail_trips += 1

    points: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
    for row in _rows(archive, "shapes.txt"):
        if row["shape_id"] in trips_by_shape:
            points[row["shape_id"]].append(
                (int(row["shape_pt_sequence"]), float(row["shape_pt_lon"]),
                 float(row["shape_pt_lat"]))
            )  # fmt: skip
    for shape_id, rows in points.items():
        if any(west <= lon <= east and south <= lat <= north for _seq, lon, lat in rows):
            rows.sort()
            line = [(lon, lat) for _seq, lon, lat in rows]
            if len(line) >= 2:
                feed.shapes[shape_id] = line
                feed.trips_by_shape[shape_id] = trips_by_shape[shape_id]
                feed.trips[shape_id] = trip_list[shape_id]

    wanted = {service for services in feed.trips_by_shape.values() for service in services}
    dates: dict[str, set[date]] = defaultdict(set)
    for row in _rows(archive, "calendar_dates.txt"):
        if row["service_id"] in wanted and row["exception_type"].strip() == "1":
            dates[row["service_id"]].add(_day(row["date"]))
    feed.service_dates = dict(dates)
    if {"stop_times.txt", "stops.txt"} <= names:
        _read_times(archive, feed)
    return feed


def _read_times(archive: zipfile.ZipFile, feed: Feed) -> None:
    """Godziny przystanków dla kursów przez obszar (strumieniowo, bez całego pliku w pamięci)."""
    wanted = {trip for trips in feed.trips.values() for trip, _service in trips}
    times: dict[str, list[tuple[int, str, int, int]]] = defaultdict(list)
    for row in _rows(archive, "stop_times.txt"):
        if row["trip_id"] not in wanted:
            continue
        arrival = _seconds(row.get("arrival_time"))
        departure = _seconds(row.get("departure_time"))
        if arrival is None and departure is None:
            continue  # przystanek bez godziny (nie jest punktem pomiaru czasu)
        times[row["trip_id"]].append(
            (int(row["stop_sequence"]), row["stop_id"], arrival if arrival is not None
             else departure, departure if departure is not None else arrival)
        )  # fmt: skip
    used = set()
    for trip_id, rows in times.items():
        rows.sort()
        feed.stop_times[trip_id] = [(stop, arr, dep) for _seq, stop, arr, dep in rows]
        used.update(stop for _seq, stop, _arr, _dep in rows)
    for row in _rows(archive, "stops.txt"):
        if row["stop_id"] in used:
            feed.stops[row["stop_id"]] = (float(row["stop_lon"]), float(row["stop_lat"]))


def reference_week(feed: Feed, today: date) -> list[date]:
    """Pierwszy pełny tydzień pon.–niedz. w zakresie zbioru, nie wcześniej niż dziś."""
    start = max(feed.start, today)
    start += timedelta(days=(7 - start.weekday()) % 7)
    week = [start + timedelta(days=offset) for offset in range(7)]
    if week[-1] > feed.end:
        raise RuntimeError(
            f"Zbiór GTFS ({feed.start}–{feed.end}) nie obejmuje pełnego tygodnia od {start}."
        )
    return week


def trips_on(feed: Feed, shape_ids: list[str], day: date) -> int:
    return sum(
        1
        for shape_id in shape_ids
        for service in feed.trips_by_shape.get(shape_id, [])
        if day in feed.service_dates.get(service, ())
    )


def merge_feeds(feeds: dict[str, Feed]) -> Feed:
    """Łączy zbiory; identyfikatory dostają przedrostek, a zakres dat to część wspólna.

    Część wspólna jest konieczna: dzień spoza zakresu któregoś zbioru dałby dla jego
    linii zero kursów, którego nie da się odróżnić od prawdziwego zera.
    """
    merged = Feed(
        version="; ".join(f"{name}={feed.version}" for name, feed in feeds.items()),
        start=max(feed.start for feed in feeds.values()),
        end=min(feed.end for feed in feeds.values()),
    )
    for name, feed in feeds.items():
        for shape_id, line in feed.shapes.items():
            merged.shapes[f"{name}:{shape_id}"] = line
            merged.trips_by_shape[f"{name}:{shape_id}"] = [
                f"{name}:{service}" for service in feed.trips_by_shape[shape_id]
            ]
            merged.trips[f"{name}:{shape_id}"] = [
                (f"{name}:{trip}", f"{name}:{service}")
                for trip, service in feed.trips.get(shape_id, [])
            ]
        for service, days in feed.service_dates.items():
            merged.service_dates[f"{name}:{service}"] = days
        for trip, rows in feed.stop_times.items():
            merged.stop_times[f"{name}:{trip}"] = [
                (f"{name}:{stop}", arr, dep) for stop, arr, dep in rows
            ]
        for stop, point in feed.stops.items():
            merged.stops[f"{name}:{stop}"] = point
        merged.rail_trips += feed.rail_trips
    return merged
