"""Raport audytu dzielnic, torów, dróg i weryfikacji przejazdów (Markdown)."""

import psycopg

from app.etl.crossing_import import UTK_SOURCE
from app.etl.crossing_report import _table
from app.etl.topology_import import (
    BOUNDARY_M,
    RAIL_RADIUS_M,
    ROAD_RADIUS_M,
    TopologySummary,
)

REVIEW_CODES = ("grade_separation_suspected", "no_track_nearby", "no_road_nearby")


def build_topology_report(conn: psycopg.Connection, summary: TopologySummary) -> str:
    when = conn.execute(
        "SELECT to_char(coalesce(finished_at, now()) AT TIME ZONE 'Europe/Warsaw', "
        "'YYYY-MM-DD HH24:MI') FROM system.import_jobs WHERE job_id = %s",
        (summary.job_id,),
    ).fetchone()[0]
    per_district = conn.execute(
        """
        SELECT coalesce(d.name, '(poza Warszawą)'),
               count(*) FILTER (WHERE c.category IS DISTINCT FROM 'E'),
               count(*) FILTER (WHERE c.category = 'E'),
               count(*),
               count(*) FILTER (WHERE c.verification_status = 'verified')
        FROM spatial.crossings c
        JOIN system.sources s ON s.source_id = c.source_id AND s.code = %s
        LEFT JOIN spatial.districts d ON d.district_id = c.district_id
        GROUP BY d.name ORDER BY d.name NULLS LAST
        """,
        (UTK_SOURCE,),
    ).fetchall()
    in_city = conn.execute(
        """
        SELECT c.category, count(*), count(*) FILTER (WHERE c.verification_status = 'verified')
        FROM spatial.crossings c
        JOIN system.sources s ON s.source_id = c.source_id AND s.code = %s
        WHERE c.district_id IS NOT NULL GROUP BY 1 ORDER BY 1 NULLS LAST
        """,
        (UTK_SOURCE,),
    ).fetchall()
    distances = conn.execute(
        """
        SELECT count(*), percentile_cont(0.5) WITHIN GROUP (ORDER BY d),
               percentile_cont(0.9) WITHIN GROUP (ORDER BY d), max(d)
        FROM (SELECT (SELECT min(ST_Distance(r.geom, c.geom)) FROM spatial.rail_segments r
                      WHERE ST_DWithin(r.geom, c.geom, %s)) AS d
              FROM spatial.crossings c WHERE c.district_id IS NOT NULL) t WHERE d IS NOT NULL
        """,
        (RAIL_RADIUS_M,),
    ).fetchone()
    review = conn.execute(
        """
        SELECT c.name, coalesce(c.category, '?'), coalesce(d.name, ''), f.code, f.message,
               round(ST_X(c.geom))::int, round(ST_Y(c.geom))::int
        FROM system.quality_flags f
        JOIN spatial.crossings c ON c.crossing_id::text = f.entity_id
        LEFT JOIN spatial.districts d ON d.district_id = c.district_id
        WHERE f.job_id = %s AND f.code = ANY(%s) ORDER BY c.name, f.code
        """,
        (summary.job_id, list(REVIEW_CODES)),
    ).fetchall()

    total_city = sum(row[1] for row in in_city)
    verified_city = sum(row[2] for row in in_city)
    parts = [
        "# Audyt dzielnic, torów i dróg oraz weryfikacji przejazdów (RSA-005)",
        f"Wygenerowano: {when} (zadanie importu nr {summary.job_id}). "
        "Raport tworzony automatycznie przez `worker import-topology`.",
        "## Wczytane dane",
        _table(
            ["Zbiór", "Źródło", "Liczba"],
            [
                ["Dzielnice Warszawy", "PRG, jednostki ewidencyjne", summary.districts],
                [
                    "Odcinki torów kolejowych",
                    "BDOT10k OT_SKTR_L (bez tramwaju i metra)",
                    summary.rail_segments,
                ],
                ["Odcinki jezdni przy przejazdach", "BDOT10k OT_SKJZ_L", summary.road_segments],
            ],
        ),
        "## Reguły",
        f"- Weryfikacja: tor kolejowy na poziomie gruntu do {RAIL_RADIUS_M:.0f} m oraz — poza "
        f"kategorią E — jezdnia na poziomie gruntu do {ROAD_RADIUS_M:.0f} m.",
        "- Dzielnica: punkt w poligonie; na granicy wygrywa niższy kod TERYT. "
        f"Flaga, gdy do granicy jest mniej niż {BOUNDARY_M:.0f} m.",
        "- Obiekty poza granicami dzielnic zostają w ewidencji bez dzielnicy i bez weryfikacji.",
        "## Przejazdy w granicach Warszawy",
        f"Razem **{total_city}**, zweryfikowanych **{verified_city}**.",
        _table(
            ["Kategoria", "Liczba", "Zweryfikowane"],
            [[row[0] or "nieznana", row[1], row[2]] for row in in_city],
        ),
        "## Według dzielnic",
        _table(
            ["Dzielnica", "Przejazdy drogowe", "Przejścia (E)", "Razem", "Zweryfikowane"],
            [list(row) for row in per_district],
        ),
        "## Zgodność położenia z torami BDOT10k",
        (
            f"Odległość przejazd ↔ najbliższy tor dla {distances[0]} obiektów: mediana "
            f"{distances[1]:.1f} m, 90. percentyl {distances[2]:.1f} m, maksimum "
            f"{distances[3]:.1f} m."
            if distances[0]
            else "Brak przejazdów z torem w zasięgu."
        ),
        "## Flagi jakości",
        _table(["Kod", "Liczba"], [[k, v] for k, v in sorted(summary.flags.items())])
        if summary.flags
        else "Brak flag.",
    ]
    if review:
        parts += [
            "## Do ręcznego przeglądu",
            _table(
                ["Numer", "Kat.", "Dzielnica", "Kod", "Opis", "E", "N"],
                [list(row) for row in review],
            ),
        ]
    parts += [
        "## Ograniczenia",
        "- BDOT10k ma własny cykl aktualizacji; nowe lub zlikwidowane tory i drogi mogą "
        "nie zgadzać się z rejestrem UTK.",
        "- Powiązania przejazd ↔ odcinek wynikają z bliskości geometrycznej "
        "(`proximity_candidate`), nie z ręcznego potwierdzenia.",
        "- Dla przejść kategorii E sprawdzany jest tylko tor, bez ciągu pieszego.",
    ]
    return "\n\n".join(parts) + "\n"
