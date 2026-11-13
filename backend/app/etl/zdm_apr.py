"""Klient systemu Automatycznych Pomiarów Ruchu (APR) ZDM Warszawa.

Korzysta z tego samego publicznego interfejsu co narzędzie „Analiza ruchu na drogach
online” na stronie ZDM: lista lokalizacji, zlecenie raportu i odczyt gotowego raportu.
Raport dla punktu (przekrój, oba kierunki) zawiera średnią dobową liczbę pojazdów
i średni profil godzinowy dla wybranego typu dni.

Zasady korzystania: jedno zlecenie naraz, przerwy między zapytaniami, identyfikujący
nagłówek User-Agent, ponowienia przy błędach serwera. ZDM nie podaje warunków ponownego
wykorzystania; dane są informacją sektora publicznego i są opisywane źródłem
„ZDM Warszawa, system APR” (DATA_SOURCES.md).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.etl.remote_zip import RemoteFileUnavailable

BASE_URL = "https://zdm.waw.pl/apr/api/ccor/wpss/"
WARSAW_TZ = ZoneInfo("Europe/Warsaw")
# Raport natężenia pojazdów (formularz ZDM: „001A”; inny typ ruchu to „006A”).
REPORT_ID = "001A"
# Typ dni ZDM „miarodajny”: dzień roboczy bez zakłóceń pomiaru.
REPRESENTATIVE_DAYS = {"dayTypeColor": "green", "dayTypeName": "miarodajny", "loid": 1}
RETRY_DELAYS_S = (2.0, 6.0, 15.0)
POLL_INTERVAL_S = 1.5
REPORT_TIMEOUT_S = 180.0
PAUSE_BETWEEN_REPORTS_S = 2.0


class ZdmReportError(RuntimeError):
    """Raport nie powstał (błąd serwera lub przekroczony czas)."""


@dataclass(frozen=True)
class PointReport:
    """Wynik raportu dla jednego punktu pomiarowego (oba kierunki łącznie)."""

    point_id: str
    street: str | None
    section: str | None
    lon: float
    lat: float
    vehicles_per_day: int | None  # średnia dobowa; None = brak pomiaru
    max_per_day: int | None
    days: int | None
    hourly: list[int] | None  # 24 średnie wartości pojazdów/h, godziny 0–23
    period_start: date
    period_end: date  # włącznie

    @property
    def peak_hour(self) -> int | None:
        if not self.hourly:
            return None
        return max(range(24), key=lambda hour: self.hourly[hour])


def _number(value) -> int | None:
    """ZDM oznacza brak wartości kreską; zero przy braku pomiaru też traktujemy jako brak."""
    if value in (None, "-", ""):
        return None
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _period(text: str) -> tuple[date, date]:
    start, _, end = (part.strip() for part in text.partition(" - "))
    return date.fromisoformat(start), date.fromisoformat(end or start)


def parse_report(payload: dict) -> list[PointReport]:
    """Odpowiedź `getReportProgress` ze statusem FINISHED → lista wyników punktów."""
    if payload.get("status") != "FINISHED":
        raise ZdmReportError(f"raport nie jest gotowy (status: {payload.get('status')})")
    results = []
    for section in (payload.get("data") or {}).get("sections") or []:
        lon, lat = (float(part) for part in str(section["coordinates"]).split())
        start, end = _period(section["date"])
        average = _number(section.get("average"))
        total = _number(section.get("summary"))
        values = section.get("values") or []
        hourly = None
        if len(values) == 24:
            by_hour = {int(item["date"]): _number(item.get("value")) or 0 for item in values}
            hourly = [by_hour.get(hour, 0) for hour in range(24)]
        results.append(
            PointReport(
                point_id=str(section.get("pointId") or section.get("sectionName")),
                street=section.get("street"),
                section=section.get("section"),
                lon=lon,
                lat=lat,
                vehicles_per_day=average,
                max_per_day=_number(section.get("maximum")),
                days=round(total / average) if total and average else None,
                hourly=hourly if hourly and any(hourly) else None,
                period_start=start,
                period_end=end,
            )
        )
    return results


def report_request(locations: list[dict], start: date, end: date) -> dict:
    """Treść zlecenia raportu w formacie formularza ZDM (średnia, profil godzinowy)."""
    first = datetime.combine(start, datetime.min.time(), WARSAW_TZ)
    last = datetime.combine(end + timedelta(days=1), datetime.min.time(), WARSAW_TZ)
    return {
        "locations": locations,
        "density": 60,
        "groupByPoint": "POINT",
        "timeAxis": "TIME",
        "aggregationFunction": "AVG",
        "groupByTime": "PERIOD",
        "dataPresentationWay": "HOURLY",
        "dayTypes": [REPRESENTATIVE_DAYS],
        "startDate": int(first.timestamp() * 1000),
        "endDate": int(last.timestamp() * 1000) - 1000,
        "reportId": REPORT_ID,
    }


class ZdmClient:
    def __init__(
        self,
        http: httpx.Client,
        base_url: str = BASE_URL,
        retry_delays_s: tuple[float, ...] = RETRY_DELAYS_S,
        poll_interval_s: float = POLL_INTERVAL_S,
        timeout_s: float = REPORT_TIMEOUT_S,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._http = http
        self._base = base_url
        self._retry_delays_s = retry_delays_s
        self._poll_interval_s = poll_interval_s
        self._timeout_s = timeout_s
        self._sleep = sleep or time.sleep
        self.requests_made = 0

    def _call(self, method: str, name: str, **kwargs) -> dict | list:
        url = self._base + name
        last_error: Exception | None = None
        for delay in (0.0, *self._retry_delays_s):
            if delay:
                self._sleep(delay)
            self.requests_made += 1
            try:
                response = self._http.request(method, url, **kwargs)
                if response.status_code < 500 and response.status_code != 429:
                    response.raise_for_status()
                    return response.json()
                last_error = RuntimeError(f"HTTP {response.status_code}")
            except httpx.TransportError as error:
                last_error = error
        raise RemoteFileUnavailable(
            f"Serwer ZDM nie odpowiada ({url}): {last_error}. Spróbuj ponownie za kilka minut."
        ) from last_error

    def locations(self) -> list[dict]:
        """Wszystkie lokalizacje (kierunki) punktów pomiarowych."""
        return list(self._call("POST", "getLocations.ccor", json={}))

    def report(self, locations: list[dict], start: date, end: date) -> dict:
        """Zleca raport i czeka na wynik; zwraca odpowiedź ze statusem FINISHED."""
        started = self._call(
            "POST", "generateReport.ccor", json=report_request(locations, start, end)
        )
        uuid = started.get("uuid")
        if not uuid:
            raise ZdmReportError(f"serwer nie zwrócił identyfikatora raportu: {started}")
        waited = 0.0
        status = started
        while status.get("status") != "FINISHED":
            if status.get("status") in ("FAILED", "ERROR"):
                raise ZdmReportError(f"raport {uuid} zakończony błędem")
            if waited >= self._timeout_s:
                raise ZdmReportError(f"raport {uuid} nie powstał w {self._timeout_s:.0f} s")
            self._sleep(self._poll_interval_s)
            waited += self._poll_interval_s
            status = self._call("GET", "getReportProgress.ccor", params={"uuid": uuid})
        return status

    def pause(self) -> None:
        self._sleep(PAUSE_BETWEEN_REPORTS_S)
