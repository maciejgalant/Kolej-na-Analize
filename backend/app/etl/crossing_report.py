"""Raport audytu ewidencji przejazdów (Markdown) na podstawie stanu bazy."""

import psycopg

from app.etl.crossing_import import MATCH_RADIUS_M, OSM_SOURCE, UTK_SOURCE, ImportSummary
from app.etl.crossing_scan import ScanResult

CATEGORIES = ["A", "B", "C", "D", "E", "F", None]


def _table(header: list[str], rows: list[list[object]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def build_report(conn: psycopg.Connection, scan: ScanResult, summary: ImportSummary) -> str:
    job = conn.execute(
        "SELECT to_char(finished_at AT TIME ZONE 'Europe/Warsaw', 'YYYY-MM-DD HH24:MI'), params "
        "FROM system.import_jobs WHERE job_id = %s",
        (summary.job_id,),
    ).fetchone()
    by_manager = conn.execute(
        """
        SELECT coalesce(a.value_text, '(brak)'), c.category, count(*)
        FROM spatial.crossings c
        JOIN system.sources s ON s.source_id = c.source_id AND s.code = %s
        LEFT JOIN safety.crossing_attributes a
               ON a.crossing_id = c.crossing_id AND a.attribute_code = 'manager'
              AND a.source_id = c.source_id
        GROUP BY 1, 2
        """,
        (UTK_SOURCE,),
    ).fetchall()
    statuses = conn.execute(
        "SELECT c.verification_status, count(*) FROM spatial.crossings c "
        "JOIN system.sources s ON s.source_id = c.source_id AND s.code = %s GROUP BY 1 ORDER BY 1",
        (UTK_SOURCE,),
    ).fetchall()
    distance = conn.execute(
        """
        SELECT count(*), percentile_cont(0.5) WITHIN GROUP (ORDER BY d),
               percentile_cont(0.9) WITHIN GROUP (ORDER BY d), max(d)
        FROM (SELECT a.value_text::numeric AS d FROM safety.crossing_attributes a
              JOIN system.sources s ON s.source_id = a.source_id AND s.code = %s
              WHERE a.attribute_code = 'osm_distance_m') t
        """,
        (OSM_SOURCE,),
    ).fetchone()
    devices = conn.execute(
        """
        SELECT a.attribute_code, count(*) FROM safety.crossing_attributes a
        JOIN system.sources s ON s.source_id = a.source_id AND s.code = %s
        WHERE a.attribute_code LIKE 'osm:crossing:%%' GROUP BY 1 ORDER BY 1
        """,
        (OSM_SOURCE,),
    ).fetchall()
    flags = conn.execute(
        "SELECT code, severity, count(*) FROM system.quality_flags "
        "WHERE job_id = %s GROUP BY 1, 2 ORDER BY 1",
        (summary.job_id,),
    ).fetchall()
    unconfirmed = conn.execute(
        """
        SELECT c.name, coalesce(c.category, '?'), round(ST_X(c.geom))::int, round(ST_Y(c.geom))::int
        FROM system.quality_flags f
        JOIN spatial.crossings c ON c.crossing_id::text = f.entity_id
        WHERE f.job_id = %s AND f.code = 'no_osm_confirmation' ORDER BY c.name
        """,
        (summary.job_id,),
    ).fetchall()
    orphans = conn.execute(
        "SELECT entity_id, message FROM system.quality_flags "
        "WHERE job_id = %s AND code = 'osm_without_official_match' ORDER BY entity_id",
        (summary.job_id,),
    ).fetchall()

    managers = sorted({row[0] for row in by_manager})
    counts = {(row[0], row[1]): row[2] for row in by_manager}
    matrix = [
        [
            m,
            *[counts.get((m, c), 0) for c in CATEGORIES],
            sum(counts.get((m, c), 0) for c in CATEGORIES),
        ]
        for m in managers
    ]
    total = sum(row[-1] for row in matrix)

    parts = [
        "# Audyt ewidencji przejazdów (RSA-004)",
        f"Wygenerowano: {job[0]} (zadanie importu nr {summary.job_id}). "
        "Raport tworzony automatycznie przez `worker import-crossings`.",
        "## Zakres i metoda",
        f"- Obszar: prostokąt EPSG:2180 {job[1]['bbox_2180']} (Warszawa z otoczeniem; "
        "przypisanie do dzielnic i odcięcie obiektów spoza miasta nastąpi w RSA-005).",
        "- Źródło podstawowe: warstwa „Przejazdy kolejowe” UTK w Geoportalu (WMS). "
        "Położenie = środek symbolu na mapie w skali 1 m/px (dokładność rzędu kilku metrów), "
        "numer, kategoria i zarządca z GetFeatureInfo.",
        f"- Kontrola krzyżowa: punkty `railway=level_crossing|crossing` z OpenStreetMap; "
        f"status `verified` przy wzajemnie najbliższym punkcie OSM do {MATCH_RADIUS_M:.0f} m.",
        f"- Zapytań do WMS: {job[1]['wms_requests']}; kafli przeglądu: {scan.coarse_tiles}; "
        f"punktów startowych: {scan.seeds}.",
        "## Liczba obiektów według zarządcy i kategorii",
        _table(["Zarządca", "A", "B", "C", "D", "E", "F", "nieznana", "Razem"], matrix),
        f"Razem obiektów: **{total}**.",
        "## Status weryfikacji",
        _table(["Status", "Liczba"], [list(row) for row in statuses]),
    ]
    if summary.osm_points is None:
        parts.append(
            "**Dane OSM nie zostały pobrane** — wszystkie obiekty mają status `unverified`. "
            "Uruchom import ponownie, gdy Overpass API będzie dostępne."
        )
    else:
        parts += [
            f"Punktów OSM w obszarze: {summary.osm_points}; dopasowanych: {summary.matched}.",
            "## Zgodność położenia z OSM",
            (
                f"Odległość UTK ↔ OSM dla {distance[0]} par: mediana {distance[1]:.1f} m, "
                f"90. percentyl {distance[2]:.1f} m, maksimum {distance[3]:.1f} m."
                if distance[0]
                else "Brak dopasowanych par."
            ),
            "## Dostępność cech zabezpieczeń (tagi OSM)",
            _table(["Cecha", "Liczba przejazdów"], [list(r) for r in devices])
            if devices
            else "Żaden dopasowany punkt OSM nie ma tagów `crossing:*`.",
        ]
    parts += [
        "## Flagi jakości",
        _table(["Kod", "Waga", "Liczba"], [list(r) for r in flags]) if flags else "Brak flag.",
    ]
    if unconfirmed:
        parts += [
            "## Obiekty UTK bez potwierdzenia w OSM (do ręcznego przeglądu)",
            _table(["Numer", "Kat.", "E", "N"], [list(r) for r in unconfirmed]),
        ]
    if orphans:
        parts += [
            "## Punkty OSM bez odpowiednika w rejestrze UTK",
            "Możliwe przyczyny: bocznica innego zarządcy, przejście nieformalne, "
            "błąd w OSM albo brak w rejestrze.",
            _table(["Węzeł OSM", "Położenie i typ"], [list(r) for r in orphans]),
        ]
    if scan.unidentified:
        parts += [
            "## Symbole bez odpowiedzi usługi",
            _table(["E", "N"], [[f"{e:.0f}", f"{n:.0f}"] for e, n in scan.unidentified]),
        ]
    parts += [
        "## Ograniczenia",
        "- Rejestr UTK nie zawiera szczegółów urządzeń ani widoczności — tylko kategorię.",
        "- Warunki ponownego wykorzystania usługi UTK/GUGiK nie są zadeklarowane "
        "(`system.licenses.allows_storage = NULL`) — do potwierdzenia przed publikacją danych.",
        "- Kategoria pochodzi z rejestru i nie była sprawdzana w terenie.",
    ]
    return "\n\n".join(parts) + "\n"
