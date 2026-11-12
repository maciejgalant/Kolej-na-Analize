"""Planowa liczba pociągów pasażerskich na przejazd (RSA-006 w części planowej + RSA-009).

Kurs jest przypisywany do przejazdu, gdy geometria jego trasy z GTFS przebiega nie dalej
niż MATCH_M od punktu przejazdu. Wynik to liczba kursów na dobę kursowania w tygodniu
odniesienia, zapisana w `rail.crossing_flow` z `evidence_type = 'planned'`.

Ograniczenia: tylko pociągi pasażerskie (bez towarowych, służbowych i manewrów);
0 oznacza „żaden kurs pasażerski z rozkładu”, a nie brak ruchu na torze.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import psycopg

from app.etl.gtfs import GTFS_URL, Feed, trips_on

MATCH_M = 20.0
NEAR_M = 10.0
FAR_M = 50.0
METHOD_VERSION = "gtfs-shape-1"
UNIT = "passenger_trains/day"
GTFS_SOURCE = "gtfs_polish_trains"
SENSITIVE_FLAG = "train_count_sensitive"
WARSAW_TZ = ZoneInfo("Europe/Warsaw")


@dataclass
class FlowSummary:
    job_id: int
    week: list[date]
    crossings: int = 0
    with_trains: int = 0
    sensitive: int = 0
    rows: list[dict] = field(default_factory=list)


def ensure_source(conn: psycopg.Connection) -> int:
    conn.execute(
        """
        INSERT INTO system.licenses (code, name, url, attribution_text,
                                     allows_storage, allows_derivatives, notes)
        VALUES ('plk-km-reuse', 'Ponowne wykorzystywanie informacji sektora publicznego (PLK, KM)',
                'https://bip.plk-sa.pl/ponowne-wykorzystywanie',
                'Dane: PKP Polskie Linie Kolejowe S.A., Koleje Mazowieckie; GTFS: M. Kuranowski',
                NULL, NULL, 'Warunki ponownego wykorzystania do przeczytania i potwierdzenia.')
        ON CONFLICT (code) DO NOTHING
        """
    )
    return conn.execute(
        """
        INSERT INTO system.sources (code, name, provider, url, license_id)
        SELECT %s, 'Polish Trains GTFS - rozkład pociągów pasażerskich',
               'PKP PLK / KM; opracowanie M. Kuranowski', %s, license_id
        FROM system.licenses WHERE code = 'plk-km-reuse'
        ON CONFLICT (code) DO UPDATE SET url = EXCLUDED.url
        RETURNING source_id
        """,
        (GTFS_SOURCE, GTFS_URL),
    ).fetchone()[0]


def _match_shapes(conn: psycopg.Connection, feed: Feed) -> dict[int, list[tuple[str, float]]]:
    """Dla każdego przejazdu w Warszawie: trasy w zasięgu FAR_M z odległością w metrach."""
    conn.execute(
        "CREATE TEMP TABLE tmp_shapes (shape_id text PRIMARY KEY, "
        "geom geometry(LineString, 2180)) ON COMMIT DROP"
    )
    with conn.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO tmp_shapes VALUES (%s, ST_Transform(ST_GeomFromText(%s, 4326), 2180))",
            [
                (shape_id, "LINESTRING(" + ",".join(f"{lon} {lat}" for lon, lat in line) + ")")
                for shape_id, line in feed.shapes.items()
            ],
        )
    conn.execute("CREATE INDEX ON tmp_shapes USING gist (geom)")
    matches: dict[int, list[tuple[str, float]]] = {
        row[0]: []
        for row in conn.execute(
            "SELECT crossing_id FROM spatial.crossings WHERE district_id IS NOT NULL"
        )
    }
    for crossing_id, shape_id, distance in conn.execute(
        "SELECT c.crossing_id, s.shape_id, ST_Distance(c.geom, s.geom) "
        "FROM spatial.crossings c JOIN tmp_shapes s ON ST_DWithin(c.geom, s.geom, %s) "
        "WHERE c.district_id IS NOT NULL",
        (FAR_M,),
    ):
        matches[crossing_id].append((shape_id, distance))
    return matches


def import_train_flow(
    conn: psycopg.Connection, feed: Feed, week: list[date], feed_last_modified: str | None = None
) -> FlowSummary:
    with conn.transaction():
        source_id = ensure_source(conn)
        job_id = conn.execute(
            "INSERT INTO system.import_jobs (source_id, snapshot_label, params) "
            "VALUES (%s, %s, %s) RETURNING job_id",
            (
                source_id,
                feed.version[:10] or None,
                json.dumps(
                    {
                        "feed_version": feed.version,
                        "feed_last_modified": feed_last_modified,
                        "week": [day.isoformat() for day in week],
                        "match_m": MATCH_M,
                        "method_version": METHOD_VERSION,
                    }
                ),
            ),
        ).fetchone()[0]
        summary = FlowSummary(job_id=job_id, week=week)
        matches = _match_shapes(conn, feed)
        conn.execute(
            "DELETE FROM system.quality_flags WHERE code = %s AND resolved_at IS NULL",
            (SENSITIVE_FLAG,),
        )
        conn.execute(
            "DELETE FROM rail.crossing_flow WHERE evidence_type = 'planned' "
            "AND method_version = %s AND crossing_id = ANY(%s)",
            (METHOD_VERSION, list(matches)),
        )
        flows = []
        for crossing_id, found in matches.items():

            def within(limit: float, found=found) -> list[str]:
                return [shape_id for shape_id, distance in found if distance <= limit]

            daily = [trips_on(feed, within(MATCH_M), day) for day in week]
            near = sum(trips_on(feed, within(NEAR_M), day) for day in week)
            far = sum(trips_on(feed, within(FAR_M), day) for day in week)
            nearest = min((distance for _shape, distance in found), default=None)
            sensitive = far > 0 and (far - near) / far > 0.1
            if sensitive:
                summary.sensitive += 1
                conn.execute(
                    "INSERT INTO system.quality_flags (entity_schema, entity_table, entity_id, "
                    "code, severity, message, job_id) VALUES ('spatial', 'crossings', %s, %s, "
                    "'warning', %s, %s)",
                    (
                        str(crossing_id),
                        SENSITIVE_FLAG,
                        f"Liczba kursów zależy od progu dopasowania: {near} przy "
                        f"{NEAR_M:.0f} m, {far} przy {FAR_M:.0f} m (tydzień).",
                        job_id,
                    ),
                )
            for day, count in zip(week, daily, strict=True):
                start = datetime.combine(day, time.min, tzinfo=WARSAW_TZ)
                end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=WARSAW_TZ)
                flows.append((crossing_id, start, end, count, UNIT, METHOD_VERSION))
            summary.crossings += 1
            summary.with_trains += any(daily)
            summary.rows.append(
                {"crossing_id": crossing_id, "daily": daily, "nearest_m": nearest,
                 "sensitive": sensitive}
            )  # fmt: skip
        with conn.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO rail.crossing_flow (crossing_id, period_start, period_end, "
                "train_count, unit, evidence_type, method_version) "
                "VALUES (%s, %s, %s, %s, %s, 'planned', %s)",
                flows,
            )
        conn.execute(
            "UPDATE system.import_jobs SET status = 'succeeded', finished_at = now(), "
            "records_read = %s, records_written = %s WHERE job_id = %s",
            (feed.rail_trips, len(flows), job_id),
        )
    return summary


def build_flow_report(conn: psycopg.Connection, feed: Feed, summary: FlowSummary) -> str:
    from app.etl.crossing_report import _table

    info = {
        row[0]: row[1:]
        for row in conn.execute(
            "SELECT c.crossing_id, c.name, coalesce(c.category, '?'), d.name "
            "FROM spatial.crossings c JOIN spatial.districts d USING (district_id)"
        )
    }
    rows = []
    for row in sorted(summary.rows, key=lambda r: -sum(r["daily"][:5])):
        name, category, district = info[row["crossing_id"]]
        daily = row["daily"]
        rows.append(
            [name, category, district, round(sum(daily[:5]) / 5), daily[5], daily[6],
             "—" if row["nearest_m"] is None else f"{row['nearest_m']:.1f}",
             "tak" if row["sensitive"] else ""]
        )  # fmt: skip
    week = summary.week
    parts = [
        "# Audyt planowego ruchu pociągów pasażerskich (RSA-006/009)",
        f"Zadanie importu nr {summary.job_id}. Raport tworzony automatycznie przez "
        "`worker import-schedule`.",
        "## Źródło i metoda",
        f"- Zbiór: Polish Trains GTFS (mkuran.pl), wersja `{feed.version}`, zakres "
        f"{feed.start} – {feed.end}; dane rozkładowe PKP PLK i Kolei Mazowieckich.",
        f"- Tydzień odniesienia: {week[0]} (pon.) – {week[-1]} (niedz.).",
        f"- Kurs liczony dla przejazdu, gdy trasa kursu przebiega do {MATCH_M:.0f} m od niego. "
        f"Kontrola wrażliwości: progi {NEAR_M:.0f} m i {FAR_M:.0f} m.",
        f"- Tras kolejowych w obszarze: {len(feed.shapes)}; kursów kolejowych w zbiorze: "
        f"{feed.rail_trips}.",
        "## Wynik",
        f"Przejazdów w Warszawie: **{summary.crossings}**, z co najmniej jednym kursem "
        f"pasażerskim w tygodniu: **{summary.with_trains}**, bez kursów: "
        f"**{summary.crossings - summary.with_trains}**, wrażliwych na próg: "
        f"**{summary.sensitive}**.",
        _table(
            [
                "Numer",
                "Kat.",
                "Dzielnica",
                "Śr. dzień roboczy",
                "Sobota",
                "Niedziela",
                "Odległość trasy [m]",
                "Wrażliwy",
            ],
            rows,
        ),  # fmt: skip
        "## Ograniczenia",
        "- Tylko pociągi pasażerskie z rozkładu; ruch towarowy, służbowy i manewry nie są "
        "ujęte. Zero oznacza brak kursów pasażerskich, a nie brak ruchu na torze.",
        "- To plan, nie wykonanie: odwołania i opóźnienia będą dostępne po uzyskaniu "
        "klucza do API PKP PLK.",
        "- Geometrie tras pochodzą z mapy utrzymywanej przez autora zbioru GTFS; "
        "na rozjazdach i liniach równoległych przypisanie może być niejednoznaczne.",
        "- Kursy liczone według dnia kursowania z rozkładu (kursy po północy należą do "
        "dnia, w którym się rozpoczęły).",
        "- Warunki ponownego wykorzystania danych PLK/KM nie zostały jeszcze potwierdzone.",
    ]
    return "\n\n".join(parts) + "\n"
