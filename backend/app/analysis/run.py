"""Przebieg analizy WPO: dane wejściowe z PostGIS → `analysis.*` (RSA-010).

Zakres: zweryfikowane przejazdy drogowe (kategorie inne niż E) w granicach Warszawy.
Przejścia dla pieszych są w ewidencji i na mapie, ale poza rankingiem.
"""

import json
import math
from dataclasses import dataclass

import psycopg

from app.analysis import rps
from app.etl.bdot10k import GROUND_LEVEL
from app.etl.topology_import import ROAD_RADIUS_M

ROAD_NEAR_M = 15.0

INPUTS_SQL = """
WITH base AS (
    SELECT c.crossing_id, c.category, c.geom,
           (SELECT avg(f.train_count)::float FROM rail.crossing_flow f
             WHERE f.crossing_id = c.crossing_id AND f.evidence_type = 'planned'
               AND extract(isodow FROM f.period_start AT TIME ZONE 'Europe/Warsaw') < 6
           ) AS trains_weekday,
           (SELECT r.geom FROM spatial.rail_segments r
             WHERE ST_DWithin(r.geom, c.geom, 15) AND r.level_position = %(ground)s
             ORDER BY ST_Distance(r.geom, c.geom) LIMIT 1) AS rail_geom,
           -- Najnowszy pomiar ZDM z punktu na ulicy przejazdu, blisko niego (RSA-007).
           (SELECT jsonb_build_object(
                       'vehicles', m.vehicles_count, 'station_id', s.station_id,
                       'street', s.street, 'section', s.section,
                       'distance_m', cs.distance_m::float, 'day_type', m.day_type,
                       'period_start', to_char(m.period_start AT TIME ZONE 'Europe/Warsaw',
                                               'YYYY-MM-DD'),
                       'period_end', to_char(m.period_end AT TIME ZONE 'Europe/Warsaw'
                                             - interval '1 day', 'YYYY-MM-DD'),
                       'source', src.code)
              FROM road.crossing_stations cs
              JOIN road.stations s USING (station_pk)
              JOIN system.sources src ON src.source_id = s.source_id
              JOIN road.measurements m
                ON m.source_id = s.source_id AND m.station_id = s.station_id
               AND m.unit = 'vehicles/day' AND m.vehicles_count IS NOT NULL
             WHERE cs.crossing_id = c.crossing_id AND cs.match_type = 'direct'
             ORDER BY m.period_end DESC, cs.distance_m LIMIT 1) AS measured
    FROM spatial.crossings c
    WHERE c.district_id IS NOT NULL AND c.verification_status = 'verified'
      AND c.category IS DISTINCT FROM 'E'
), road AS (
    -- Jezdnia o najwyższej klasie spośród leżących do 15 m od punktu (ulica przejazdu,
    -- a nie boczna dojazdówka); jej oś służy też do wyznaczenia kąta. Gdy bliżej niż 15 m
    -- nie ma żadnej, brana jest najbliższa do 30 m, o ile przecina tor — już bez kąta.
    SELECT DISTINCT ON (b.crossing_id) b.crossing_id, r.road_class, r.geom AS road_geom,
           ST_Distance(r.geom, b.geom) AS road_dist
    FROM base b
    JOIN spatial.road_segments r
      ON r.level_position = %(ground)s
     AND (ST_DWithin(r.geom, b.geom, %(road_near)s)
          -- dalsza jezdnia musi przecinać tor przy przejeździe; ulica równoległa odpada
          OR (ST_DWithin(r.geom, b.geom, %(road_far)s)
              AND ST_DWithin(ST_Intersection(r.geom, b.rail_geom), b.geom, 40)))
    ORDER BY b.crossing_id,
             (ST_Distance(r.geom, b.geom) > %(road_near)s),
             CASE WHEN ST_Distance(r.geom, b.geom) <= %(road_near)s
                  THEN array_position(%(classes)s::text[], r.road_class) END DESC NULLS LAST,
             ST_Distance(r.geom, b.geom)
), az AS (
    SELECT b.*, road.road_class, road.road_geom, road.road_dist,
           pg_temp.analysis_azimuth(b.rail_geom, b.geom) AS rail_az,
           CASE WHEN road.road_dist <= %(road_near)s
                THEN pg_temp.analysis_azimuth(road.road_geom, b.geom) END AS road_az
    FROM base b LEFT JOIN road USING (crossing_id)
)
SELECT crossing_id, category, trains_weekday, road_class,
       rail_az, road_az, road_dist,  -- 0–6
       -- Tory liczone na 30-metrowym przekroju prostopadłym do najbliższego toru.
       (SELECT sum(coalesce(r.track_count, 1))::int FROM spatial.rail_segments r
         WHERE az.rail_az IS NOT NULL AND r.level_position = %(ground)s
           AND ST_Intersects(r.geom, ST_MakeLine(
                 ST_Translate(az.geom, 15 * sin(az.rail_az + pi() / 2),
                              15 * cos(az.rail_az + pi() / 2)),
                 ST_Translate(az.geom, 15 * sin(az.rail_az - pi() / 2),
                              15 * cos(az.rail_az - pi() / 2))))
       ) AS tracks,  -- 7
       measured  -- 8
FROM az ORDER BY crossing_id
"""


@dataclass
class RunSummary:
    run_id: int
    scored: int
    ranked: int
    period: tuple[str, str] | None


def _create_helpers(conn: psycopg.Connection) -> None:
    # Azymut osi linii w pobliżu punktu (±5 m wzdłuż linii), w radianach.
    conn.execute(
        """
        CREATE OR REPLACE FUNCTION pg_temp.analysis_azimuth(line geometry, pt geometry)
        RETURNS double precision LANGUAGE sql IMMUTABLE AS $$
            SELECT CASE WHEN line IS NULL OR ST_Length(line) = 0 THEN NULL ELSE
                ST_Azimuth(
                    ST_LineInterpolatePoint(line, greatest(0, f - d)),
                    ST_LineInterpolatePoint(line, least(1, f + d)))
            END
            FROM (SELECT ST_LineLocatePoint(line, pt) AS f,
                         least(0.5, 5 / nullif(ST_Length(line), 0)) AS d) t
        $$
        """
    )


def _acute_angle_deg(rail_az: float | None, road_az: float | None) -> float | None:
    if rail_az is None or road_az is None:
        return None
    diff = abs(rail_az - road_az) % math.pi
    return math.degrees(min(diff, math.pi - diff))


def load_inputs(conn: psycopg.Connection) -> list[rps.CrossingInputs]:
    _create_helpers(conn)
    rows = conn.execute(
        INPUTS_SQL,
        {
            "ground": GROUND_LEVEL,
            "classes": list(rps.ROAD_CLASS_VEHICLES),
            "road_near": ROAD_NEAR_M,
            "road_far": ROAD_RADIUS_M,
        },
    ).fetchall()
    return [
        rps.CrossingInputs(
            crossing_id=row[0],
            category=row[1],
            trains_weekday=row[2],
            road_class=row[3],
            tracks=row[7],
            road_distance_m=None if row[6] is None else round(row[6], 1),
            angle_deg=_acute_angle_deg(row[4], row[5]),
            vehicles_measured=None if row[8] is None else row[8]["vehicles"],
            measurement=None
            if row[8] is None
            else {k: v for k, v in row[8].items() if k != "vehicles"},
        )
        for row in rows
    ]


def run_analysis(conn: psycopg.Connection, is_demo: bool = False) -> RunSummary:
    with conn.transaction():
        period = conn.execute(
            "SELECT min(period_start), max(period_end) FROM rail.crossing_flow "
            "WHERE evidence_type = 'planned'"
        ).fetchone()
        if period[0] is None:
            raise RuntimeError("Brak danych o ruchu pociągów — najpierw uruchom import-schedule.")
        inputs = load_inputs(conn)
        scores = rps.score_crossings(inputs)
        run_id = conn.execute(
            "INSERT INTO analysis.runs (method_version, period_start, period_end, parameters, "
            "input_snapshot, is_demo) VALUES (%s, %s, %s, %s, %s, %s) RETURNING run_id",
            (
                rps.METHOD_VERSION,
                period[0],
                period[1],
                json.dumps(
                    {
                        "weights": rps.WEIGHTS,
                        "key_components": rps.KEY_COMPONENTS,
                        "road_class_vehicles": rps.ROAD_CLASS_VEHICLES,
                        "road_measurement": {
                            "source": "zdm_apr",
                            "match": "direct",
                            "method": "zdm-street-1",
                        },
                        "exposure_reference": rps.EXPOSURE_REFERENCE,
                        "category_score": rps.CATEGORY_SCORE,
                        "sensitivity_step": 0.2,
                    }
                ),
                json.dumps(
                    {
                        "crossings": len(inputs),
                        "with_road_measurement": sum(
                            1 for item in inputs if item.vehicles_measured
                        ),
                        "flow_methods": [
                            row[0]
                            for row in conn.execute(
                                "SELECT DISTINCT method_version FROM rail.crossing_flow "
                                "WHERE evidence_type = 'planned'"
                            )
                        ],
                    }
                ),
                is_demo,
            ),
        ).fetchone()[0]
        with conn.cursor() as cursor:
            for score in scores:
                statuses = {c.status for c in score.components.values() if c.value is not None}
                quality = (
                    "partial"
                    if score.rps is None
                    else ("modelled" if "modelled" in statuses else "ok")
                )
                cursor.execute(
                    "INSERT INTO analysis.risk_scores (run_id, crossing_id, rps, rank, "
                    "is_partial, completeness_pct, quality_status, rank_best, rank_worst) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        run_id,
                        score.crossing_id,
                        score.rps,
                        score.rank,
                        score.is_partial,
                        score.completeness_pct,
                        quality,
                        score.rank_best,
                        score.rank_worst,
                    ),
                )
                for name, component in score.components.items():
                    cursor.execute(
                        "INSERT INTO analysis.components (run_id, crossing_id, component, "
                        "value, weight, status, detail) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (
                            run_id,
                            score.crossing_id,
                            name,
                            component.value,
                            rps.WEIGHTS[name],
                            component.status,
                            json.dumps(component.detail),
                        ),
                    )
        conn.execute(
            "UPDATE analysis.runs SET status = 'completed', finished_at = now() WHERE run_id = %s",
            (run_id,),
        )
    ranked = sum(1 for s in scores if s.rank is not None)
    local = conn.execute(
        "SELECT to_char(period_start AT TIME ZONE 'Europe/Warsaw', 'YYYY-MM-DD'), "
        "to_char(period_end AT TIME ZONE 'Europe/Warsaw' - interval '1 day', 'YYYY-MM-DD') "
        "FROM analysis.runs WHERE run_id = %s",
        (run_id,),
    ).fetchone()
    return RunSummary(run_id, len(scores), ranked, (local[0], local[1]))


def build_run_report(conn: psycopg.Connection, summary: RunSummary) -> str:
    from app.etl.crossing_report import _table

    rows = conn.execute(
        """
        SELECT s.rank, c.name, c.category, d.name, s.rps, s.rank_best, s.rank_worst,
               s.completeness_pct,
               max(k.value) FILTER (WHERE k.component = 'T'),
               max(k.value) FILTER (WHERE k.component = 'P'),
               max(k.value) FILTER (WHERE k.component = 'G'),
               max(k.detail ->> 'reason') FILTER (WHERE k.component = 'T')
        FROM analysis.risk_scores s
        JOIN spatial.crossings c USING (crossing_id)
        JOIN spatial.districts d USING (district_id)
        JOIN analysis.components k USING (run_id, crossing_id)
        WHERE s.run_id = %s
        GROUP BY s.rank, c.name, c.category, d.name, s.rps, s.rank_best, s.rank_worst,
                 s.completeness_pct
        ORDER BY s.rank NULLS LAST, c.name
        """,
        (summary.run_id,),
    ).fetchall()

    def fmt(value) -> str:
        return "—" if value is None else f"{float(value):.1f}"

    measured = conn.execute(
        "SELECT count(*) FROM analysis.components WHERE run_id = %s AND component = 'T' "
        "AND detail ->> 'vehicles_source' = 'measured'",
        (summary.run_id,),
    ).fetchone()[0]
    ranked = [r for r in rows if r[0] is not None]
    unranked = [r for r in rows if r[0] is None]
    stable = sum(1 for r in ranked if r[6] - r[5] <= 1)
    parts = [
        "# Raport przebiegu WPO (RSA-010)",
        f"Przebieg nr {summary.run_id}, metoda `{rps.METHOD_VERSION}`, okres danych o ruchu "
        f"{summary.period[0]} – {summary.period[1]}. Raport tworzony przez `worker run-analysis`.",
        "**WPO to priorytet do dalszej oceny w przyjętej metodzie, a nie prognoza wypadków "
        "ani urzędowa klasyfikacja. Wagi i tabele są eksperymentalne i niezwalidowane.**",
        "## Metoda w skrócie",
        "- `WPO = 0,40·T + 0,30·P + 0,20·G + 0,10·H`; średnia ważona po dostępnych składnikach.",
        "- T: planowe pociągi pasażerskie × pojazdy na dobę (pomiar ZDM, gdy punkt leży na "
        "ulicy przejazdu blisko niego; w pozostałych przypadkach szacunek z klasy drogi), skala "
        "logarytmiczna. P: kategoria przejazdu. G: liczba torów i kąt skrzyżowania. "
        "H: brak danych dla wszystkich obiektów.",
        "- Bez T lub P obiekt nie dostaje pozycji. Kompletność 90% oznacza brak tylko H.",
        "- Wrażliwość: każda waga zmieniana o ±20%; kolumna „zakres” to najlepsza i "
        "najgorsza pozycja w tych wariantach.",
        "## Ranking",
        f"Obiektów ocenianych: **{summary.scored}**, z pozycją: **{summary.ranked}**, "
        f"w tym stabilnych (zakres do 1 pozycji): **{stable}**.",
        _table(
            ["Poz.", "Numer", "Kat.", "Dzielnica", "WPO", "Zakres", "T", "P", "G", "Kompl. %"],
            [[r[0], r[1], r[2] or "?", r[3], fmt(r[4]), f"{r[5]}–{r[6]}", fmt(r[8]), fmt(r[9]),
              fmt(r[10]), fmt(r[7])] for r in ranked],
        ),
    ]  # fmt: skip
    if unranked:
        parts += [
            "## Bez pozycji w rankingu",
            _table(
                ["Numer", "Kat.", "Dzielnica", "P", "G", "Powód braku T"],
                [[r[1], r[2] or "?", r[3], fmt(r[9]), fmt(r[10]), r[11] or "brak P"]
                 for r in unranked],
            ),
        ]  # fmt: skip
    parts += [
        "## Ograniczenia",
        f"- Natężenie ruchu drogowego z pomiaru ZDM ma {measured} z {summary.scored} "
        "ocenianych przejazdów; pozostałe mają szacunek z klasy drogi BDOT10k "
        "(porównanie: reports/DATA_AUDIT_road.md).",
        "- Liczba pociągów to plan przewozów pasażerskich; ruch towarowy nie jest ujęty.",
        "- G nie zawiera widoczności ani stanu nawierzchni; H jest puste.",
        "- Tabele punktowe (kategoria, tory, kąt) są założeniami autorskimi.",
    ]
    return "\n\n".join(parts) + "\n"
