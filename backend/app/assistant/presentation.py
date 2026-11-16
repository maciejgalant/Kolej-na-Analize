"""Typed UI payloads built from successful read tools, never parsed from model prose."""

from collections.abc import Callable
from typing import Annotated, Literal

import psycopg
from pydantic import BaseModel, ConfigDict, Field

from app.api.crossings import DISCLAIMER, CrossingDetail, crossing_detail

CrossingId = Annotated[int, Field(strict=True, gt=0)]
Number = Annotated[float, Field(allow_inf_nan=False)]


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Card(Payload):
    crossing_id: CrossingId
    title: str
    district: str | None = None
    category: str | None = None
    rps: Number | None = None
    rank: int | None = None
    trains: Number | None = None


class Table(Payload):
    title: str
    columns: list[str]
    rows: list[list[str | Number | None]]


class Point(Payload):
    label: str
    value: Number | None
    status: Literal["ok", "modelled", "unknown", "planned", "measured"]


class Chart(Payload):
    title: str
    unit: str
    points: list[Point]


class Evidence(Payload):
    presentation: Literal["full", "ranking_summary"] = "full"
    cards: list[Card] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    charts: list[Chart] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    map_ids: list[CrossingId] = Field(default_factory=list, max_length=60)


COMPONENTS = {"T": "Ekspozycja", "P": "Zabezpieczenia", "G": "Geometria", "H": "Historia"}


def build_evidence(
    conn: psycopg.Connection,
    results: list[tuple[str, dict]],
    *,
    load_detail: Callable = crossing_detail,
) -> Evidence:
    """IDs come only from tool SQL results. Only those objects are loaded for charts/sources."""
    evidence = Evidence()
    cards: dict[int, Card] = {}
    detailed: set[int] = set()
    for name, result in results:
        rows: list[dict] = []
        if name == "get_ranking":
            rows = result.get("ranking", [])
            if result.get("uwaga"):
                evidence.notes.append(result["uwaga"])
            evidence.notes.append(
                "Pozycje rankingu dotyczą całej Warszawy, także po filtrze dzielnicy."
            )
        elif name in ("get_crossing", "attached_crossing"):
            rows = [result]
        elif name == "compare_crossings":
            rows = [result["a"], result["b"]]
            parts = result.get("skladniki_porownania", [])
            if parts:
                statuses = {"ok": "dostępny", "modelled": "modelowany", "unknown": "brak danych"}
                evidence.tables.append(
                    Table(
                        title="Porównanie składników: A minus B",
                        columns=[
                            "Składnik",
                            f"A: {result['a'].get('numer')}",
                            "Status A",
                            f"B: {result['b'].get('numer')}",
                            "Status B",
                            "Różnica A−B",
                            "Wkład do RPS A",
                            "Wkład do RPS B",
                        ],
                        rows=[
                            [
                                statuses.get(p.get(k), p.get(k))
                                if k.startswith("status_")
                                else p.get(k)
                                for k in (
                                    "skladnik",
                                    "a",
                                    "status_a",
                                    "b",
                                    "status_b",
                                    "roznica_a_minus_b",
                                    "wklad_do_rps_a",
                                    "wklad_do_rps_b",
                                )
                            ]
                            for p in parts
                        ],
                    )
                )
                evidence.tables.append(
                    Table(
                        title="Jakość danych porównywanych przejazdów",
                        columns=[
                            "Przejazd",
                            "Kompletność składników (%)",
                            "Ruch drogowy",
                            "Brakujące składniki",
                        ],
                        rows=[
                            [
                                result[key].get("numer"),
                                result[f"jakosc_{key}"]["kompletnosc_proc"],
                                result[f"jakosc_{key}"]["ruch_drogowy"],
                                ", ".join(
                                    COMPONENTS[k]
                                    for k in result[f"jakosc_{key}"]["brakujace_skladniki"]
                                )
                                or "Brak",
                            ]
                            for key in ("a", "b")
                        ],
                    )
                )
                a, b = rows
                evidence.notes.extend(
                    [
                        f"A: {a.get('numer')}; B: {b.get('numer')}.",
                        result["uwaga"],
                        "Różnica RPS A−B: "
                        + (
                            str(result["roznica_rps_a_minus_b"])
                            if result.get("roznica_rps_a_minus_b") is not None
                            else "brak porównania liczbowego — przejazd poza rankingiem."
                        ),
                    ]
                )
        elif name == "get_data_quality":
            rows = result.get("przejazdy", [])
            evidence.tables.append(
                Table(
                    title="Jakość danych — lista do weryfikacji",
                    columns=[
                        "Przejazd",
                        "Kompletność składników (%)",
                        "Ruch drogowy",
                        "Składniki modelowane",
                        "Brakujące składniki",
                    ],
                    rows=[
                        [
                            r.get("numer"),
                            r["jakosc_danych"]["kompletnosc_proc"],
                            r["jakosc_danych"]["ruch_drogowy"],
                            ", ".join(
                                COMPONENTS[k]
                                for k in r["jakosc_danych"]["modelowane_skladniki"]
                                if k in COMPONENTS
                            )
                            or "Brak",
                            ", ".join(
                                COMPONENTS[k]
                                for k in r["jakosc_danych"]["brakujace_skladniki"]
                                if k in COMPONENTS
                            )
                            or "Brak",
                        ]
                        for r in rows
                    ],
                )
            )
            evidence.notes.append(result["uwaga"])
        elif name == "list_districts":
            evidence.tables.append(
                Table(
                    title="Dzielnice z przejazdami",
                    columns=["Dzielnica", "Przejazdy drogowe", "Przejścia piesze", "W rankingu"],
                    rows=[
                        [
                            r.get(k)
                            for k in (
                                "dzielnica",
                                "przejazdy_drogowe",
                                "przejscia_dla_pieszych",
                                "przejazdy_w_rankingu",
                            )
                        ]
                        for r in result.get("dzielnice_z_przejazdami", [])
                    ],
                )
            )
        elif name == "get_method":
            evidence.notes.extend(result.get("ograniczenia", []))
            if result.get("wzor"):
                evidence.notes.append(result["wzor"])
            evidence.notes.extend(f"{k}: {v}" for k, v in result.get("skladniki", {}).items())
        for row in rows:
            crossing_id = row.get("crossing_id")
            if type(crossing_id) is not int or crossing_id <= 0:
                continue  # no mapping by guessed IDs, names or model text
            if crossing_id not in cards and len(cards) >= 60:
                continue
            card = Card(
                crossing_id=crossing_id,
                title=str(row.get("numer") or f"#{crossing_id}"),
                district=row.get("dzielnica"),
                category=row.get("kategoria"),
                rps=row.get("rps"),
                rank=row.get("pozycja"),
                trains=row.get(
                    "pociagi_pasazerskie_dzien_roboczy_plan", row.get("pociagi_dzien_roboczy_plan")
                ),
            )
            cards[crossing_id] = card
            if name not in ("get_ranking", "get_data_quality"):
                detailed.add(crossing_id)
            evidence.notes.extend(row.get("ostrzezenia", []))
    evidence.cards = list(cards.values())
    evidence.map_ids = list(cards)
    if cards:
        evidence.tables.append(
            Table(
                title="Przejazdy odczytane dla tej odpowiedzi",
                columns=[
                    "Przejazd",
                    "Dzielnica",
                    "Kategoria",
                    "Pozycja",
                    "RPS",
                    "Pociągi / dzień roboczy (plan)",
                ],
                rows=[
                    [c.title, c.district, c.category, c.rank, c.rps, c.trains]
                    for c in cards.values()
                ],
            )
        )
        evidence.charts.append(
            Chart(
                title="Planowy ruch pociągów pasażerskich",
                unit="pociągi / dzień roboczy",
                points=[
                    Point(
                        label=c.title,
                        value=c.trains,
                        status="planned" if c.trains is not None else "unknown",
                    )
                    for c in cards.values()
                ],
            )
        )
    for crossing_id, card in cards.items():
        detail: CrossingDetail = load_detail(crossing_id, conn)
        for source in detail.sources:
            evidence.sources.append(
                source.name + (f" — {source.attribution}" if source.attribution else "")
            )
        flow = detail.rail_flow
        if flow and flow.source:
            evidence.sources.append(flow.source)
        if detail.priority:
            evidence.notes.append(
                f"{card.title}: metoda {detail.priority.method_version}, "
                f"kompletność danych {detail.priority.completeness_pct:g}%."
            )
        if crossing_id not in detailed:
            continue
        if detail.priority:
            evidence.charts.append(
                Chart(
                    title=f"Składniki RPS — {card.title}",
                    unit="pkt / 100",
                    points=[
                        Point(label=COMPONENTS[c.component], value=c.value, status=c.status)
                        for c in detail.priority.components
                    ],
                )
            )
            for component in detail.priority.components:
                if component.component == "T":
                    traffic = component.detail
                    measured = traffic.get("vehicles_source") == "measured"
                    measurement = traffic.get("measurement") or {}
                    source_label = (
                        "pomiar ZDM"
                        if measurement.get("source") == "zdm_apr"
                        else "pomiar fikcyjny (demo)"
                        if str(measurement.get("source", "")).startswith("demo")
                        else "pomiar ze źródła przypisanego do przejazdu"
                    )
                    vehicles = traffic.get(
                        "vehicles_per_day_measured" if measured else "vehicles_per_day_model"
                    )
                    if isinstance(vehicles, int | float):
                        evidence.charts.append(
                            Chart(
                                title=f"Ruch drogowy — {card.title}",
                                unit="pojazdy / dobę",
                                points=[
                                    Point(
                                        label="Natężenie dobowe",
                                        value=vehicles,
                                        status="measured" if measured else "modelled",
                                    )
                                ],
                            )
                        )
                    evidence.notes.append(
                        f"{card.title}: ruch drogowy — "
                        + (
                            "brak danych."
                            if vehicles is None
                            else source_label + "."
                            if measured
                            else "model z klasy drogi, nie pomiar."
                        )
                    )
                    if measured and measurement.get("period_start"):
                        evidence.notes.append(
                            f"{card.title}: {source_label}, "
                            f"{measurement.get('street') or 'ulica nieznana'}, "
                            f"{measurement['period_start']} – {measurement.get('period_end', '?')}."
                        )
        if flow:
            evidence.charts.append(
                Chart(
                    title=f"Planowy ruch pasażerski — {card.title}",
                    unit="pociągi / dzień",
                    points=[
                        Point(
                            label=label, value=v, status="planned" if v is not None else "unknown"
                        )
                        for label, v in (
                            ("Dzień roboczy (średnio)", flow.weekday_avg),
                            ("Sobota", flow.saturday),
                            ("Niedziela", flow.sunday),
                        )
                    ],
                )
            )
            evidence.notes.append(
                f"{card.title}: rozkład {flow.period_start} – {flow.period_end}; "
                "bez ruchu towarowego i manewrowego."
            )
    if results:
        evidence.notes.append(DISCLAIMER)
    evidence.sources = list(dict.fromkeys(evidence.sources))
    evidence.notes = list(dict.fromkeys(evidence.notes))
    # Repeated tool calls should not multiply identical tables.
    evidence.tables = list({t.model_dump_json(): t for t in evidence.tables}.values())
    return evidence
