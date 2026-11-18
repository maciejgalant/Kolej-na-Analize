"""Pomiary ruchu ZDM na skrzyżowaniach (RSA-017), metoda `zdm-intersection-1`.

Źródło: publiczne warstwy ArcGIS ZDM „Pomiary na skrzyżowaniach 2023–2026”:
- warstwa podsumowań (jeden rekord na skrzyżowanie: nazwa, położenie, data, klasy dróg),
- warstwa godzinowa (kilka godzin pomiaru: pojazdy według rodzaju, piesi, rowerzyści).

Dopasowanie: skrzyżowanie leży na ulicy przejazdu (nazwy po normalizacji, jak w RSA-007)
i nie dalej niż MAX_M od niego; przejazd dostaje najbliższe takie skrzyżowanie.

Liczby opisują CAŁE skrzyżowanie (wszystkie wloty) w pojedynczych godzinach, a nie
ruch przez przejazd w ciągu doby. Dlatego nie zastępują natężenia w WPO. Służą do:
udziału pojazdów ciężkich, liczby pieszych i rowerzystów oraz górnego ograniczenia
natężenia na wlocie, z którym porównujemy szacunek z klasy drogi.
"""

import json
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import httpx
import psycopg

from app.analysis.rps import ROAD_CLASS_VEHICLES
from app.etl import road_counts as rc
from app.etl.remote_zip import RemoteFileUnavailable
from app.etl.zdm_apr import WARSAW_TZ

SERVICE = "https://services7.arcgis.com/gpQ1tnydOYYnGpcS/arcgis/rest/services/"
SUMMARY_URL = SERVICE + "pomiary_skrzyzowania_2023_2/FeatureServer/0"
HOURLY_URL = SERVICE + "pomiary_skrzyzowania_2023/FeatureServer/0"
PAGE_SIZE = 1000
RETRY_DELAYS_S = (2.0, 6.0, 15.0)

METHOD_VERSION = "zdm-intersection-1"
SOURCE_CODE = "zdm_skrzyzowania"
STATION_PREFIX = "SKRZ-"
MAX_M = 300.0
UNIT = "vehicles/hour"
DIRECTION = "all"  # suma wszystkich wlotów skrzyżowania
# Rodzaje pojazdów w warstwie godzinowej ZDM.
VEHICLE_CLASSES = {
    "SO": "osobowe",
    "SD": "dostawcze",
    "S_C_": "ciężarowe",
    "SCP": "ciężarowe z przyczepą",
    "BUS": "autobusy",
    "M": "motocykle",
    "Rower": "rowery na jezdni",
}
HEAVY = ("S_C_", "SCP", "BUS")
# ZAŁOŻENIE: najbardziej ruchliwa godzina to ok. 8% ruchu dobowego (pomiar APR na
# Radzymińskiej: 7%). Służy tylko do górnego ograniczenia w raporcie, nie do WPO.
PEAK_SHARE = 0.08

SUMMARY_FIELDS = (
    "ID,Nazwa_skrzyżowania,Szerokość_geograficzna,Długość_geograficzna,Data_wykonania,"
    "Liczba_godzin_pomiaru,Klasa_drogi_nadrzędnej,Klasa_drogi_podrzędnej,"
    "Sygnalizacja_świetlna,Raport"
)
HOURLY_FIELDS = "ID,GG,M,SO,SD,BUS,S_C_,SCP,Rower,suma,Piesi,Rowerzyści,Data_wykonania"


@dataclass(frozen=True)
class HourCount:
    start: tuple[int, int]  # godzina i minuta rozpoczęcia (czas lokalny)
    vehicles: int
    composition: dict[str, int]
    pedestrians: int | None
    cyclists: int | None

    @property
    def label(self) -> str:
        h, m = self.start
        return f"{h}:{m:02d}–{h + 1}:{m:02d}"

    @property
    def heavy(self) -> int:
        return sum(self.composition.get(code, 0) for code in HEAVY)


@dataclass
class Intersection:
    point_id: str
    name: str
    lon: float
    lat: float
    measured_on: date | None
    road_class: str | None
    signals: bool | None
    report_url: str | None
    hours: list[HourCount] = field(default_factory=list)

    @property
    def streets(self) -> frozenset[str]:
        return frozenset(
            n for n in (rc.normalize_street(part) for part in split_streets(self.name)) if n
        )

    @property
    def peak(self) -> HourCount | None:
        return max(self.hours, key=lambda h: h.vehicles) if self.hours else None

    @property
    def heavy_share(self) -> float | None:
        total = sum(h.vehicles for h in self.hours)
        return sum(h.heavy for h in self.hours) / total if total else None

    @property
    def pedestrians_max(self) -> int | None:
        values = [h.pedestrians for h in self.hours if h.pedestrians is not None]
        return max(values) if values else None

    @property
    def cyclists_max(self) -> int | None:
        values = [h.cyclists for h in self.hours if h.cyclists is not None]
        return max(values) if values else None


def split_streets(name: str) -> list[str]:
    """'ul. Marsa - ul. Żołnierska - ul. Rekrucka' → trzy ulice."""
    return [part.strip() for part in re.split(r"\s+[-–]\s+|\s*/\s*", name) if part.strip()]


def _number(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _count(value) -> int | None:
    number = _number(value)
    return None if number is None or number < 0 else int(round(number))


def _hour(text) -> tuple[int, int] | None:
    match = re.match(r"\s*(\d{1,2})[.:](\d{2})", str(text or ""))
    return (int(match.group(1)), int(match.group(2))) if match else None


def _date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, int | float):  # pola daty ArcGIS: milisekundy od 1970
        return datetime.fromtimestamp(value / 1000, WARSAW_TZ).date()
    text = str(value).strip()
    for pattern in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text[:10], pattern).date()
        except ValueError:
            continue
    return None


def parse(summary_rows: list[dict], hourly_rows: list[dict]) -> list[Intersection]:
    """Rekordy obu warstw (atrybuty) → skrzyżowania z godzinami pomiaru."""
    hours: dict[str, list[dict]] = {}
    for row in hourly_rows:
        hours.setdefault(str(row.get("ID")), []).append(row)
    result = []
    for row in summary_rows:
        point_id = str(row.get("ID") or "").strip()
        lon = _number(row.get("Długość_geograficzna"))
        lat = _number(row.get("Szerokość_geograficzna"))
        name = (row.get("Nazwa_skrzyżowania") or "").strip()
        if not point_id or lon is None or lat is None or not name:
            continue
        rows = hours.get(point_id, [])
        signals = row.get("Sygnalizacja_świetlna")
        item = Intersection(
            point_id=point_id,
            name=name,
            lon=lon,
            lat=lat,
            measured_on=_date(row.get("Data_wykonania"))
            or next((_date(r.get("Data_wykonania")) for r in rows if r.get("Data_wykonania")),
                    None),
            road_class=row.get("Klasa_drogi_nadrzędnej") or None,
            signals=None if signals is None else str(signals).strip().lower() == "tak",
            report_url=row.get("Raport") or None,
        )  # fmt: skip
        for hour_row in rows:
            start = _hour(hour_row.get("GG"))
            composition = {
                code: value
                for code in VEHICLE_CLASSES
                if (value := _count(hour_row.get(code))) is not None
            }
            total = _count(hour_row.get("suma"))
            if total is None:
                total = sum(composition.values()) or None
            if start is None or total is None:
                continue
            item.hours.append(
                HourCount(
                    start,
                    total,
                    composition,
                    _count(hour_row.get("Piesi")),
                    _count(hour_row.get("Rowerzyści")),
                )
            )
        item.hours.sort(key=lambda h: h.start)
        result.append(item)
    return result


class ArcGisClient:
    """Zapytania do publicznej warstwy ArcGIS FeatureServer, ze stronicowaniem."""

    def __init__(
        self,
        http: httpx.Client,
        retry_delays_s: tuple[float, ...] = RETRY_DELAYS_S,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._http = http
        self._retry_delays_s = retry_delays_s
        self._sleep = sleep or time.sleep
        self.requests_made = 0

    def _get(self, url: str, params: dict) -> dict:
        last_error: Exception | None = None
        for delay in (0.0, *self._retry_delays_s):
            if delay:
                self._sleep(delay)
            self.requests_made += 1
            try:
                response = self._http.get(url, params=params)
                if response.status_code < 500 and response.status_code != 429:
                    response.raise_for_status()
                    payload = response.json()
                    if "error" in payload:
                        raise RuntimeError(f"ArcGIS: {payload['error']}")
                    return payload
                last_error = RuntimeError(f"HTTP {response.status_code}")
            except httpx.TransportError as error:
                last_error = error
        raise RemoteFileUnavailable(
            f"Usługa ArcGIS ZDM nie odpowiada ({url}): {last_error}. Spróbuj ponownie później."
        ) from last_error

    def features(self, layer_url: str, fields: str) -> list[dict]:
        rows: list[dict] = []
        offset = 0
        while True:
            payload = self._get(
                layer_url + "/query",
                {
                    "where": "1=1",
                    "outFields": fields,
                    "returnGeometry": "false",
                    "orderByFields": "fid",
                    "resultOffset": offset,
                    "resultRecordCount": PAGE_SIZE,
                    "f": "json",
                },
            )
            page = [feature["attributes"] for feature in payload.get("features", [])]
            rows += page
            if not payload.get("exceededTransferLimit") or not page:
                return rows
            offset += len(page)


@dataclass(frozen=True)
class IntersectionMatch:
    crossing_id: int
    point_id: str
    distance_m: float


def match(
    conn: psycopg.Connection,
    intersections: list[Intersection],
    crossings: list[rc.CrossingStreet],
) -> list[IntersectionMatch]:
    """Najbliższe skrzyżowanie na ulicy przejazdu, do MAX_M."""
    stations = {
        i.point_id: rc.Station(i.point_id, i.name, None, i.road_class, i.lon, i.lat)
        for i in intersections
    }
    xy = rc._projected(conn, stations)
    by_street: dict[str, list[str]] = {}
    for item in intersections:
        for street in item.streets:
            by_street.setdefault(street, []).append(item.point_id)
    result = []
    for crossing in crossings:
        candidates = sorted(
            (math.dist((crossing.east, crossing.north), xy[pid]), pid)
            for street in crossing.streets
            for pid in by_street.get(street, [])
        )
        if candidates and candidates[0][0] <= MAX_M:
            distance, point_id = candidates[0]
            result.append(IntersectionMatch(crossing.crossing_id, point_id, round(distance, 1)))
    return result


def ensure_source(conn: psycopg.Connection) -> int:
    rc.ensure_source(conn)  # licencja ZDM (informacja sektora publicznego)
    return conn.execute(
        """
        INSERT INTO system.sources (code, name, provider, url, license_id)
        SELECT %s, 'ZDM - pomiary ruchu na skrzyżowaniach 2023-2026',
               'Zarząd Dróg Miejskich w Warszawie', %s, license_id
        FROM system.licenses WHERE code = %s
        ON CONFLICT (code) DO UPDATE SET url = EXCLUDED.url
        RETURNING source_id
        """,
        (SOURCE_CODE, SUMMARY_URL, rc.LICENSE_CODE),
    ).fetchone()[0]


@dataclass
class IntersectionSummary:
    job_id: int
    intersections: list[Intersection]
    matches: list[IntersectionMatch]
    written: int = 0


def save(conn: psycopg.Connection, source_id: int, summary: IntersectionSummary) -> None:
    """Zapisuje dopasowane skrzyżowania, powiązania z przejazdami i godziny pomiaru."""
    by_id = {i.point_id: i for i in summary.intersections}
    used = sorted({m.point_id for m in summary.matches})
    pks = {}
    for point_id in used:
        item = by_id[point_id]
        pks[point_id] = conn.execute(
            """
            INSERT INTO road.stations (source_id, station_id, street, section, road_class, geom)
            VALUES (%s, %s, %s, NULL, %s,
                    ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 2180))
            ON CONFLICT (source_id, station_id) DO UPDATE
            SET street = EXCLUDED.street, road_class = EXCLUDED.road_class, geom = EXCLUDED.geom
            RETURNING station_pk
            """,
            (source_id, STATION_PREFIX + point_id, item.name, item.road_class, item.lon,
             item.lat),
        ).fetchone()[0]  # fmt: skip
    conn.execute(
        "DELETE FROM road.crossing_stations cs USING road.stations s "
        "WHERE cs.station_pk = s.station_pk AND s.source_id = %s",
        (source_id,),
    )
    for m in summary.matches:
        conn.execute(
            "INSERT INTO road.crossing_stations (crossing_id, station_pk, distance_m, "
            "match_type, method_version) VALUES (%s, %s, %s, 'intersection', %s)",
            (m.crossing_id, pks[m.point_id], m.distance_m, METHOD_VERSION),
        )
    for point_id in used:
        item = by_id[point_id]
        if item.measured_on is None:
            continue
        for hour in item.hours:
            start = datetime.combine(item.measured_on, datetime.min.time(), WARSAW_TZ).replace(
                hour=hour.start[0], minute=hour.start[1]
            )
            conn.execute(
                """
                INSERT INTO road.measurements (source_id, import_job_id, station_id,
                    period_start, period_end, vehicles_count, unit, direction, quality_status,
                    composition, pedestrians, cyclists)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ok', %s, %s, %s)
                ON CONFLICT (source_id, station_id, period_start, period_end, direction)
                DO UPDATE SET vehicles_count = EXCLUDED.vehicles_count,
                    import_job_id = EXCLUDED.import_job_id,
                    composition = EXCLUDED.composition,
                    pedestrians = EXCLUDED.pedestrians, cyclists = EXCLUDED.cyclists
                """,
                (
                    source_id, summary.job_id, STATION_PREFIX + point_id, start,
                    start + timedelta(hours=1), hour.vehicles, UNIT, DIRECTION,
                    json.dumps(hour.composition), hour.pedestrians, hour.cyclists,
                ),
            )  # fmt: skip
            summary.written += 1
    conn.execute(
        "UPDATE system.import_jobs SET status = 'succeeded', finished_at = now(), "
        "records_read = %s, records_written = %s WHERE job_id = %s",
        (len(summary.intersections), summary.written, summary.job_id),
    )


def _int(value: int | float | None) -> str:
    return "—" if value is None else f"{round(value):,}".replace(",", " ")


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def build_report(summary: IntersectionSummary, crossings: list[rc.CrossingStreet]) -> str:
    from app.etl.crossing_report import _table

    by_crossing = {c.crossing_id: c for c in crossings}
    by_id = {i.point_id: i for i in summary.intersections}
    with_hours = sum(1 for i in summary.intersections if i.hours)
    rows = []
    above = 0
    for m in sorted(summary.matches, key=lambda m: by_crossing[m.crossing_id].name):
        crossing = by_crossing[m.crossing_id]
        item = by_id[m.point_id]
        peak = item.peak
        model = ROAD_CLASS_VEHICLES.get(crossing.road_class or "")
        bound = peak.vehicles / PEAK_SHARE if peak else None
        exceeds = model is not None and bound is not None and model > bound
        above += exceeds
        rows.append(
            [
                crossing.name,
                crossing.street_label or "?",
                item.name,
                f"{m.distance_m:.0f}",
                str(item.measured_on or "?"),
                f"{_int(peak.vehicles)} ({peak.label})" if peak else "—",
                _pct(item.heavy_share),
                _int(item.pedestrians_max),
                _int(item.cyclists_max),
                _int(model),
                _int(bound) + (" ⚠" if exceeds else ""),
            ]
        )
    return (
        "\n\n".join(
            [
                "# Audyt pomiarów ZDM na skrzyżowaniach (RSA-017)",
                f"Metoda `{METHOD_VERSION}`. Źródło: Zarząd Dróg Miejskich w Warszawie, "
                "warstwy „Pomiary na skrzyżowaniach 2023–2026”. Raport tworzony przez "
                "`worker import-intersection-counts`.",
                "## Pokrycie",
                f"Skrzyżowań w danych: **{len(summary.intersections)}**, z godzinami pomiaru: "
                f"**{with_hours}**. Przejazdów drogowych w rankingu: **{len(crossings)}**, "
                f"z pomiarem skrzyżowania na tej samej ulicy do {MAX_M:.0f} m: "
                f"**{len(summary.matches)}**.",
                "## Skrzyżowania przy przejazdach",
                "Szczyt to najbardziej ruchliwa zmierzona godzina dla całego skrzyżowania "
                "(wszystkie wloty). Udział ciężkich: samochody ciężarowe, z przyczepą i "
                "autobusy. „Górna granica” ≈ szczyt / "
                f"{PEAK_SHARE:.2f} — rząd wielkości ruchu dobowego całego węzła, więc ruch "
                "na jednym wlocie (przez przejazd) jest mniejszy. ⚠ = szacunek WPO z klasy "
                "drogi przekracza tę granicę, czyli model zawyża natężenie.",
                _table(
                    [
                        "Przejazd",
                        "Ulica (BDOT10k)",
                        "Skrzyżowanie ZDM",
                        "Odl. [m]",
                        "Data",
                        "Szczyt [poj./h]",
                        "Ciężkie",
                        "Piesi max [/h]",
                        "Rowerzyści max [/h]",
                        "Model WPO [poj./dobę]",
                        "Górna granica [poj./dobę]",
                    ],
                    rows,
                ),  # fmt: skip
                f"Przejazdów, dla których model przekracza górną granicę: **{above}**.",
                "## Zasady i ograniczenia",
                "- Pomiar dotyczy kilku godzin jednego dnia (zwykle szczyty i międzyszczyt), "
                "a nie średniej z wielu dni.",
                "- Liczby obejmują wszystkie wloty skrzyżowania; WPO nadal używa pomiaru APR "
                "albo szacunku z klasy drogi.",
                "- Skrzyżowanie jest przypisywane tylko na tej samej ulicy co przejazd.",
            ]
        )
        + "\n"
    )
