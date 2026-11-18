"""Pomiary natężenia ruchu ZDM (APR) przy przejazdach (RSA-007), metoda `zdm-street-1`.

Dopasowanie punktu pomiarowego do przejazdu:
1. Ulica przejazdu = nazwy jezdni BDOT10k do ROAD_NEAR_M od punktu przejazdu (gdy brak,
   jezdnie powiązane z przejazdem do 30 m). Nazwy są porównywane po normalizacji
   („ul. Radzymińska” = „Radzymińska”).
2. Punkt ZDM musi leżeć na tej samej ulicy i nie dalej niż MAX_M od przejazdu.
3. Najbliższy taki punkt do DIRECT_M dostaje typ `direct`: jego średnia dobowa zastępuje
   w WPO szacunek z klasy drogi. Pozostałe mają typ `validation` i służą tylko do
   porównania z modelem, bo między punktem a przejazdem mogą być skrzyżowania, które
   zmieniają natężenie.

Sama bliskość nie wystarcza (DATA_SOURCES.md, zasada 4): punkt na innej ulicy nigdy
nie jest przypisywany, nawet jeśli leży kilkadziesiąt metrów od przejazdu.
"""

import json
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import psycopg

from app.analysis.rps import ROAD_CLASS_VEHICLES
from app.etl.zdm_apr import BASE_URL, WARSAW_TZ, PointReport

METHOD_VERSION = "zdm-street-1"
SOURCE_CODE = "zdm_apr"
LICENSE_CODE = "zdm-apr-psi"
ROAD_NEAR_M = 15.0
DIRECT_M = 300.0
MAX_M = 1500.0
UNIT = "vehicles/day"
STREET_PREFIXES = ("ulica", "ul", "aleja", "aleje", "al", "plac", "pl", "rondo", "most")


def normalize_street(name: str | None) -> str | None:
    """'ul. Gen. Sowińskiego' i 'Gen. Sowińskiego' → 'gen sowińskiego'."""
    if not name:
        return None
    words = re.sub(r"[.,\-–]", " ", name.lower()).split()
    while words and words[0] in STREET_PREFIXES:
        words = words[1:]
    return " ".join(words) or None


@dataclass(frozen=True)
class Station:
    point_id: str
    street: str | None
    section: str | None
    road_class: str | None  # klasa drogi według ZDM (np. Z, G, GP)
    lon: float
    lat: float


@dataclass(frozen=True)
class CrossingStreet:
    crossing_id: int
    name: str
    streets: frozenset[str]  # znormalizowane nazwy ulic przejazdu
    street_label: str | None
    road_class: str | None  # klasa jezdni z BDOT10k (do porównania z modelem)
    east: float
    north: float


@dataclass(frozen=True)
class Match:
    crossing_id: int
    point_id: str
    distance_m: float
    match_type: str  # direct | validation


@dataclass
class RoadCountsSummary:
    job_id: int
    start: date
    end: date
    day_type: str | None
    stations_seen: int = 0
    matches: list[Match] = field(default_factory=list)
    reports: dict[str, PointReport] = field(default_factory=dict)
    written: int = 0


def stations_from_locations(locations: list[dict]) -> dict[str, Station]:
    """Lokalizacje ZDM (po jednej na kierunek) → punkty pomiarowe."""
    stations: dict[str, Station] = {}
    for location in locations:
        point = location.get("point") or {}
        point_id = str(point.get("pointId") or "")
        if not point_id or point_id in stations or not location.get("forPortal", True):
            continue
        stations[point_id] = Station(
            point_id=point_id,
            street=point.get("pointStreet"),
            section=point.get("pointSection"),
            road_class=location.get("roadClass"),
            lon=float(point.get("longitude") or location["longitude"]),
            lat=float(point.get("latitude") or location["latitude"]),
        )
    return stations


def stations_from_reports(reports: list[PointReport]) -> dict[str, Station]:
    return {
        r.point_id: Station(r.point_id, r.street, r.section, None, r.lon, r.lat) for r in reports
    }


def locations_by_point(locations: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for location in locations:
        point_id = str((location.get("point") or {}).get("pointId") or "")
        if point_id:
            grouped.setdefault(point_id, []).append(location)
    return grouped


def crossing_streets(conn: psycopg.Connection) -> list[CrossingStreet]:
    """Przejazdy drogowe objęte rankingiem z nazwami ulic i klasą jezdni."""
    rows = conn.execute(
        """
        SELECT c.crossing_id, c.name, ST_X(c.geom), ST_Y(c.geom),
               coalesce(near.names, linked.names), coalesce(near.road_class, linked.road_class)
        FROM spatial.crossings c
        LEFT JOIN LATERAL (
            SELECT array_agg(DISTINCT r.road_name) FILTER (WHERE r.road_name IS NOT NULL)
                       AS names,
                   (array_agg(r.road_class ORDER BY
                        array_position(%(classes)s::text[], r.road_class) DESC NULLS LAST))[1]
                       AS road_class
            FROM spatial.road_segments r
            WHERE ST_DWithin(r.geom, c.geom, %(near)s)
        ) near ON true
        LEFT JOIN LATERAL (
            SELECT array_agg(DISTINCT r.road_name) FILTER (WHERE r.road_name IS NOT NULL)
                       AS names,
                   (array_agg(r.road_class ORDER BY
                        array_position(%(classes)s::text[], r.road_class) DESC NULLS LAST))[1]
                       AS road_class
            FROM spatial.crossing_road_segments l
            JOIN spatial.road_segments r USING (segment_id)
            WHERE l.crossing_id = c.crossing_id
        ) linked ON true
        WHERE c.district_id IS NOT NULL AND c.verification_status = 'verified'
          AND c.category IS DISTINCT FROM 'E'
        ORDER BY c.crossing_id
        """,
        {"classes": list(ROAD_CLASS_VEHICLES), "near": ROAD_NEAR_M},
    ).fetchall()
    result = []
    for crossing_id, name, east, north, names, road_class in rows:
        normalized = frozenset(n for n in (normalize_street(x) for x in names or []) if n)
        result.append(
            CrossingStreet(
                crossing_id, name, normalized, ", ".join(sorted(names or [])) or None,
                road_class, east, north,
            )
        )  # fmt: skip
    return result


def _projected(conn: psycopg.Connection, stations: dict[str, Station]) -> dict[str, tuple]:
    if not stations:
        return {}
    ids = list(stations)
    rows = conn.execute(
        """
        SELECT id, ST_X(p), ST_Y(p) FROM (
            SELECT id, ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 2180) AS p
            FROM unnest(%s::text[], %s::float8[], %s::float8[]) AS t(id, lon, lat)) s
        """,
        (ids, [stations[i].lon for i in ids], [stations[i].lat for i in ids]),
    ).fetchall()
    return {row[0]: (row[1], row[2]) for row in rows}


def match_stations(
    conn: psycopg.Connection, stations: dict[str, Station], crossings: list[CrossingStreet]
) -> list[Match]:
    xy = _projected(conn, stations)
    by_street: dict[str, list[str]] = {}
    for point_id, station in stations.items():
        street = normalize_street(station.street)
        if street:
            by_street.setdefault(street, []).append(point_id)
    matches = []
    for crossing in crossings:
        candidates = sorted(
            (math.dist((crossing.east, crossing.north), xy[pid]), pid)
            for street in crossing.streets
            for pid in by_street.get(street, [])
        )
        candidates = [(d, pid) for d, pid in candidates if d <= MAX_M]
        for index, (distance, point_id) in enumerate(candidates):
            kind = "direct" if index == 0 and distance <= DIRECT_M else "validation"
            matches.append(Match(crossing.crossing_id, point_id, round(distance, 1), kind))
    return matches


def ensure_source(conn: psycopg.Connection) -> int:
    conn.execute(
        """
        INSERT INTO system.licenses (code, name, url, attribution_text,
                                     allows_storage, allows_derivatives, notes)
        VALUES (%s, 'Informacja sektora publicznego - ZDM Warszawa (APR)',
                'https://zdm.waw.pl/dzialania/badania-i-analizy/analiza-ruchu-na-drogach/',
                'Źródło: Zarząd Dróg Miejskich w Warszawie, system APR', NULL, NULL,
                'ZDM nie podaje warunków ponownego wykorzystania. Dane publikowane na stronie '
                'zarządcy drogi (ustawa o otwartych danych i PSI); do potwierdzenia z ZDM.')
        ON CONFLICT (code) DO NOTHING
        """,
        (LICENSE_CODE,),
    )
    return conn.execute(
        """
        INSERT INTO system.sources (code, name, provider, url, license_id)
        SELECT %s, 'ZDM APR - automatyczne pomiary ruchu', 'Zarząd Dróg Miejskich w Warszawie',
               %s, license_id FROM system.licenses WHERE code = %s
        ON CONFLICT (code) DO UPDATE SET url = EXCLUDED.url
        RETURNING source_id
        """,
        (SOURCE_CODE, BASE_URL, LICENSE_CODE),
    ).fetchone()[0]


def start_job(conn: psycopg.Connection, source_id: int, params: dict) -> int:
    return conn.execute(
        "INSERT INTO system.import_jobs (source_id, snapshot_label, params) "
        "VALUES (%s, to_char(now(), 'YYYY-MM-DD'), %s) RETURNING job_id",
        (source_id, json.dumps(params, default=str)),
    ).fetchone()[0]


def _local_midnight(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), WARSAW_TZ)


def save(
    conn: psycopg.Connection,
    source_id: int,
    summary: RoadCountsSummary,
    stations: dict[str, Station],
) -> None:
    """Zapisuje dopasowane punkty, powiązania i pomiary. Powtórny import aktualizuje dane."""
    used = {m.point_id for m in summary.matches}
    pks: dict[str, int] = {}
    for point_id in sorted(used):
        station = stations[point_id]
        pks[point_id] = conn.execute(
            """
            INSERT INTO road.stations (source_id, station_id, street, section, road_class, geom)
            VALUES (%s, %s, %s, %s, %s,
                    ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 2180))
            ON CONFLICT (source_id, station_id) DO UPDATE
            SET street = EXCLUDED.street, section = EXCLUDED.section,
                road_class = coalesce(EXCLUDED.road_class, road.stations.road_class),
                geom = EXCLUDED.geom
            RETURNING station_pk
            """,
            (source_id, point_id, station.street, station.section, station.road_class,
             station.lon, station.lat),
        ).fetchone()[0]  # fmt: skip
    conn.execute(
        "DELETE FROM road.crossing_stations cs USING road.stations s "
        "WHERE cs.station_pk = s.station_pk AND s.source_id = %s",
        (source_id,),
    )
    for match in summary.matches:
        conn.execute(
            "INSERT INTO road.crossing_stations (crossing_id, station_pk, distance_m, "
            "match_type, method_version) VALUES (%s, %s, %s, %s, %s)",
            (match.crossing_id, pks[match.point_id], match.distance_m, match.match_type,
             METHOD_VERSION),
        )  # fmt: skip
    for point_id, report in summary.reports.items():
        if point_id not in used:
            continue
        conn.execute(
            """
            INSERT INTO road.measurements (source_id, import_job_id, station_id, period_start,
                period_end, vehicles_count, unit, direction, quality_status, day_type,
                hourly_profile, days_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'both', %s, %s, %s, %s)
            ON CONFLICT (source_id, station_id, period_start, period_end, direction) DO UPDATE
            SET vehicles_count = EXCLUDED.vehicles_count, import_job_id = EXCLUDED.import_job_id,
                quality_status = EXCLUDED.quality_status, day_type = EXCLUDED.day_type,
                hourly_profile = EXCLUDED.hourly_profile, days_count = EXCLUDED.days_count
            """,
            (
                source_id,
                summary.job_id,
                point_id,
                _local_midnight(report.period_start),
                _local_midnight(report.period_end + timedelta(days=1)),
                report.vehicles_per_day,
                UNIT,
                "ok" if report.vehicles_per_day is not None else "unknown",
                summary.day_type,
                None if report.hourly is None else json.dumps(report.hourly),
                report.days,
            ),
        )
        summary.written += 1
    conn.execute(
        "UPDATE system.import_jobs SET status = 'succeeded', finished_at = now(), "
        "records_read = %s, records_written = %s WHERE job_id = %s",
        (summary.stations_seen, summary.written, summary.job_id),
    )


def _int(value: int | None) -> str:
    return "—" if value is None else f"{value:,}".replace(",", "\u00a0")


def _dec(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def build_road_report(
    conn: psycopg.Connection, summary: RoadCountsSummary, crossings: list[CrossingStreet]
) -> str:
    from app.etl.crossing_report import _table

    by_id = {c.crossing_id: c for c in crossings}
    rows = []
    ratios = []
    for match in sorted(summary.matches, key=lambda m: (by_id[m.crossing_id].name, m.distance_m)):
        crossing = by_id[match.crossing_id]
        report = summary.reports.get(match.point_id)
        measured = None if report is None else report.vehicles_per_day
        model = ROAD_CLASS_VEHICLES.get(crossing.road_class or "")
        ratio = measured / model if measured and model else None
        if ratio is not None and match.match_type == "direct":
            ratios.append((crossing.road_class, ratio))
        rows.append(
            [
                crossing.name,
                crossing.street_label or "?",
                f"{match.point_id} ({report.section if report else '?'})",
                f"{match.distance_m:.0f}",
                "pomiar w WPO" if match.match_type == "direct" else "walidacja",
                _int(measured),
                "—" if report is None or report.peak_hour is None else f"{report.peak_hour}:00",
                f"{crossing.road_class or '?'} → {_int(model)}",
                "—" if ratio is None else f"{_dec(ratio)}×",
            ]
        )
    covered = {m.crossing_id for m in summary.matches}
    direct = {m.crossing_id for m in summary.matches if m.match_type == "direct"}
    day_type = summary.day_type or "nieokreślony (raport z pliku)"
    parts = [
        "# Audyt pomiarów ruchu drogowego ZDM (RSA-007)",
        f"Okres pomiaru: {summary.start} – {summary.end}, typ dni: {day_type}. "
        f"Metoda dopasowania `{METHOD_VERSION}`. Źródło: Zarząd Dróg Miejskich w Warszawie, "
        "system Automatycznych Pomiarów Ruchu (APR). Raport tworzony przez "
        "`worker import-road-counts`.",
        "## Pokrycie",
        f"Przejazdów drogowych w rankingu: **{len(crossings)}**. Z punktem ZDM na tej samej "
        f"ulicy do {_dec(MAX_M / 1000)} km: **{len(covered)}**, w tym z pomiarem użytym w WPO "
        f"(do {DIRECT_M:.0f} m): **{len(direct)}**. Punktów ZDM w danych: "
        f"{summary.stations_seen}.",
        "## Pomiar a model z klasy drogi",
        "Kolumna „model” to szacunek WPO z klasy jezdni BDOT10k (pojazdy/dobę), „pomiar / "
        "model” — ile razy pomiar jest większy od szacunku.",
        _table(
            [
                "Przejazd",
                "Ulica (BDOT10k)",
                "Punkt ZDM",
                "Odl. [m]",
                "Użycie",
                "Pomiar [poj./dobę]",
                "Szczyt",
                "Klasa → model",
                "Pomiar / model",
            ],
            rows,
        ),  # fmt: skip
        "## Zasady i ograniczenia",
        f"- Punkt przypisywany jest tylko na tej samej ulicy. Typ „walidacja” (dalej niż "
        f"{DIRECT_M:.0f} m albo nie najbliższy) nie zmienia WPO: między punktem a przejazdem "
        "mogą być skrzyżowania.",
        "- Wartość to średnia dobowa dla obu kierunków łącznie, z dni wybranego typu.",
        "- Kilka punktów nie wystarcza do kalibracji tabeli klas drogi; porównanie pokazuje "
        "skalę rozbieżności, a nie nowe współczynniki.",
    ]
    if ratios:
        mean = sum(r for _, r in ratios) / len(ratios)
        parts.insert(
            -4,
            f"Średnio pomiar / model dla przejazdów z pomiarem w WPO: **{_dec(mean)}×** "
            f"(n = {len(ratios)}).",
        )
    return "\n\n".join(parts) + "\n"
