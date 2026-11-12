"""Planowa liczba pociągów pasażerskich na przejazd (RSA-006 w części planowej + RSA-009).

Metoda `gtfs-shape-2`:
1. Zbiór według zarządcy: obiekty PKP PLK liczone są tylko z rozkładu ogólnopolskiego,
   obiekty WKD tylko z rozkładu WKD, bocznice innych zarządców nie mają kursów pasażerskich.
   Rejestr UTK dzieli jedno fizyczne skrzyżowanie na osobne obiekty zarządców, więc pociągi
   WKD nie mogą być doliczane do obiektu PLK leżącego kilkadziesiąt metrów dalej.
2. Kurs jest liczony, gdy geometria jego trasy przebiega do MATCH_M od punktu przejazdu.
3. Próg rozszerzony FAR_M stosuje się dla obiektów WKD (jedna linia, a położenie obiektu
   bywa wspólne z sąsiednim obiektem PLK) oraz dla obiektów PLK, których punkt leży na
   torach innej linii niż wynika z numeru przejazdu (np. `007 …` na torach linii 506):
   to znak, że zarejestrowany punkt jest na skraju szerokiej grupy torów.

Wynik: liczba kursów na dobę kursowania w tygodniu odniesienia, zapisana w
`rail.crossing_flow` z `evidence_type = 'planned'`.

Ograniczenia: tylko pociągi pasażerskie (bez towarowych, służbowych i manewrów);
0 oznacza „żaden kurs pasażerski z rozkładu”, a nie brak ruchu na torze.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import psycopg

from app.etl.gtfs import GTFS_URL, WKD_GTFS_URL, Feed, trips_on

MATCH_M = 20.0
NEAR_M = 10.0
FAR_M = 50.0
METHOD_VERSION = "gtfs-shape-2"
UNIT = "passenger_trains/day"
GTFS_SOURCE = "gtfs_polish_trains"
WKD_SOURCE = "gtfs_wkd"
SENSITIVE_FLAG = "train_count_sensitive"
EXTENDED_FLAG = "train_count_extended"
# Warstwa rejestru UTK (zarządca) -> przedrostek zbioru GTFS z merge_feeds().
FEED_BY_LAYER = {"PKP_Polskie_Linie_Kolejowe": "PL", "Warszawska_Kolej_Dojazdowa": "WKD"}
WARSAW_TZ = ZoneInfo("Europe/Warsaw")


@dataclass
class FlowSummary:
    job_id: int
    week: list[date]
    crossings: int = 0
    with_trains: int = 0
    sensitive: int = 0
    extended: int = 0
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
    conn.execute(
        """
        INSERT INTO system.licenses (code, name, url, attribution_text,
                                     allows_storage, allows_derivatives, notes)
        VALUES ('cc0-1.0', 'Creative Commons Zero 1.0', 
                'https://creativecommons.org/publicdomain/zero/1.0/',
                'WKD GTFS: M. Kuranowski (CC0)', true, true,
                'Licencja podana przez autora zbioru na mkuran.pl/gtfs.')
        ON CONFLICT (code) DO NOTHING
        """
    )
    conn.execute(
        """
        INSERT INTO system.sources (code, name, provider, url, license_id)
        SELECT %s, 'WKD GTFS - rozkład Warszawskiej Kolei Dojazdowej',
               'WKD; opracowanie M. Kuranowski', %s, license_id
        FROM system.licenses WHERE code = 'cc0-1.0'
        ON CONFLICT (code) DO UPDATE SET url = EXCLUDED.url
        """,
        (WKD_SOURCE, WKD_GTFS_URL),
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


@dataclass
class CrossingContext:
    feed_prefix: str | None  # None = zarządca bez rozkładu pasażerskiego
    own_line: str | None  # numer linii z numeru przejazdu PLK, np. "7"
    track_lines: set[str]  # numery linii torów powiązanych z przejazdem (BDOT10k)
    shapes: list[tuple[str, float]] = field(default_factory=list)  # (shape_id, odległość)

    @property
    def on_foreign_line(self) -> bool:
        """Punkt leży na torach innej linii niż zarejestrowana (i nie na własnej)."""
        return (
            self.own_line is not None
            and bool(self.track_lines)
            and self.own_line not in self.track_lines
        )


def _own_line(layer: str, name: str | None) -> str | None:
    head = (name or "").split(" ")[0]
    if layer == "PKP_Polskie_Linie_Kolejowe" and head.isdigit():
        return head.lstrip("0") or "0"
    return None


def _match_shapes(conn: psycopg.Connection, feed: Feed) -> dict[int, CrossingContext]:
    """Dla każdego przejazdu w Warszawie: kontekst i trasy w zasięgu FAR_M."""
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
    contexts: dict[int, CrossingContext] = {}
    for crossing_id, source_object_id, name, lines in conn.execute(
        """
        SELECT c.crossing_id, c.source_object_id, c.name,
               ARRAY(SELECT DISTINCT ltrim(r.line_number, '0')
                     FROM spatial.crossing_rail_segments l
                     JOIN spatial.rail_segments r USING (segment_id)
                     WHERE l.crossing_id = c.crossing_id AND r.line_number IS NOT NULL)
        FROM spatial.crossings c WHERE c.district_id IS NOT NULL
        """
    ):
        layer = source_object_id.split(":", 1)[0]
        contexts[crossing_id] = CrossingContext(
            feed_prefix=FEED_BY_LAYER.get(layer),
            own_line=_own_line(layer, name),
            track_lines={line for line in lines if line},
        )
    for crossing_id, shape_id, distance in conn.execute(
        "SELECT c.crossing_id, s.shape_id, ST_Distance(c.geom, s.geom) "
        "FROM spatial.crossings c JOIN tmp_shapes s ON ST_DWithin(c.geom, s.geom, %s) "
        "WHERE c.district_id IS NOT NULL",
        (FAR_M,),
    ):
        context = contexts[crossing_id]
        if context.feed_prefix and shape_id.startswith(context.feed_prefix + ":"):
            context.shapes.append((shape_id, distance))
    return contexts


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
        contexts = _match_shapes(conn, feed)
        conn.execute(
            "DELETE FROM system.quality_flags WHERE code = ANY(%s) AND resolved_at IS NULL",
            ([SENSITIVE_FLAG, EXTENDED_FLAG],),
        )
        conn.execute(
            "DELETE FROM rail.crossing_flow WHERE evidence_type = 'planned' "
            "AND method_version LIKE 'gtfs-shape-%%' AND crossing_id = ANY(%s)",
            (list(contexts),),
        )

        def flag(crossing_id: int, code: str, severity: str, message: str) -> None:
            conn.execute(
                "INSERT INTO system.quality_flags (entity_schema, entity_table, entity_id, "
                "code, severity, message, job_id) VALUES ('spatial', 'crossings', %s, %s, %s, "
                "%s, %s)",
                (str(crossing_id), code, severity, message, job_id),
            )

        flows = []
        for crossing_id, context in contexts.items():

            def weekly(limit: float, context=context) -> list[int]:
                ids = [shape for shape, distance in context.shapes if distance <= limit]
                return [trips_on(feed, ids, day) for day in week]

            near, base, far = sum(weekly(NEAR_M)), weekly(MATCH_M), weekly(FAR_M)
            extended = sum(far) > sum(base) and (
                context.feed_prefix == "WKD" or (sum(base) == 0 and context.on_foreign_line)
            )
            daily = far if extended else base
            nearest = min((distance for _shape, distance in context.shapes), default=None)
            sensitive = sum(far) > 0 and (sum(far) - sum(daily)) / sum(far) > 0.1
            if extended:
                summary.extended += 1
                reason = (
                    "obiekt WKD"
                    if context.feed_prefix == "WKD"
                    else f"punkt leży na torach linii {', '.join(sorted(context.track_lines))}, "
                    f"a numer wskazuje linię {context.own_line}"
                )
                flag(
                    crossing_id,
                    EXTENDED_FLAG,
                    "info",
                    f"Zastosowano próg {FAR_M:.0f} m ({reason}): {sum(daily)} kursów w tygodniu "
                    f"zamiast {sum(base)} przy {MATCH_M:.0f} m.",
                )
            if sensitive:
                summary.sensitive += 1
                flag(
                    crossing_id,
                    SENSITIVE_FLAG,
                    "warning",
                    f"W tygodniu przyjęto {sum(daily)} kursów (próg {MATCH_M:.0f} m), ale do "
                    f"{FAR_M:.0f} m przebiega {sum(far)} — możliwa linia równoległa.",
                )
            for day, count in zip(week, daily, strict=True):
                start = datetime.combine(day, time.min, tzinfo=WARSAW_TZ)
                end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=WARSAW_TZ)
                flows.append((crossing_id, start, end, count, UNIT, METHOD_VERSION))
            summary.crossings += 1
            summary.with_trains += any(daily)
            summary.rows.append(
                {
                    "crossing_id": crossing_id,
                    "daily": daily,
                    "nearest_m": nearest,
                    "sensitive": sensitive,
                    "extended": extended,
                    "week_near": near,
                    "week_base": sum(base),
                    "week_far": sum(far),
                }
            )
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
            [
                name,
                category,
                district,
                round(sum(daily[:5]) / 5),
                daily[5],
                daily[6],
                "—" if row["nearest_m"] is None else f"{row['nearest_m']:.1f}",
                "wrażliwy" if row["sensitive"] else ("próg 50 m" if row["extended"] else ""),
            ]
        )
    week = summary.week
    parts = [
        "# Audyt planowego ruchu pociągów pasażerskich (RSA-006/009)",
        f"Zadanie importu nr {summary.job_id}. Raport tworzony automatycznie przez "
        "`worker import-schedule`.",
        "## Źródło i metoda",
        f"- Zbiory GTFS z mkuran.pl: ogólnopolski (dane PKP PLK i Kolei Mazowieckich) oraz WKD. "
        f"Wersje: `{feed.version}`; wspólny zakres dat {feed.start} – {feed.end}.",
        f"- Tydzień odniesienia: {week[0]} (pon.) – {week[-1]} (niedz.).",
        f"- Metoda `{METHOD_VERSION}`: obiekty PLK liczone z rozkładu ogólnopolskiego, obiekty "
        f"WKD z rozkładu WKD; kurs liczony, gdy trasa przebiega do {MATCH_M:.0f} m od punktu.",
        f"- Próg rozszerzony {FAR_M:.0f} m: obiekty WKD oraz obiekty PLK, których punkt leży "
        "na torach innej linii niż wynika z numeru przejazdu.",
        f"- Tras kolejowych w obszarze: {len(feed.shapes)}; kursów kolejowych w zbiorze: "
        f"{feed.rail_trips}.",
        "## Wynik",
        f"Przejazdów w Warszawie: **{summary.crossings}**, z co najmniej jednym kursem "
        f"pasażerskim w tygodniu: **{summary.with_trains}**, bez kursów: "
        f"**{summary.crossings - summary.with_trains}**, z progiem rozszerzonym: "
        f"**{summary.extended}**, wrażliwych na próg: **{summary.sensitive}**.",
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
        ),
        *_sensitive_section(summary, info),
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


def _sensitive_section(summary: FlowSummary, info: dict) -> list[str]:
    from app.etl.crossing_report import _table

    rows = [
        [
            info[row["crossing_id"]][0],
            row["week_near"],
            row["week_base"],
            row["week_far"],
            sum(row["daily"]),
            "—" if row["nearest_m"] is None else f"{row['nearest_m']:.1f}",
            "próg rozszerzony" if row["extended"] else "możliwa linia równoległa",
        ]
        for row in summary.rows
        if row["sensitive"] or row["extended"]
    ]
    if not rows:
        return []
    return [
        "## Przejazdy z niejednoznacznym dopasowaniem (do ręcznej oceny)",
        "Liczba kursów w całym tygodniu dla trzech progów, liczona tylko z rozkładu zarządcy "
        "danego obiektu.",
        _table(
            [
                "Numer",
                f"do {NEAR_M:.0f} m",
                f"do {MATCH_M:.0f} m",
                f"do {FAR_M:.0f} m",
                "Przyjęto",
                "Najbliższa trasa [m]",
                "Uwaga",
            ],
            sorted(rows, key=lambda r: -r[3]),
        ),
    ]
