"""Dzielnice, tory i drogi w PostGIS oraz weryfikacja geometryczna przejazdów (RSA-005).

Reguła weryfikacji: przejazd z rejestru UTK leżący w granicach Warszawy dostaje status
`verified`, gdy w zasięgu RAIL_RADIUS_M jest tor kolejowy na poziomie gruntu, a dla
kategorii innych niż E także jezdnia na poziomie gruntu w zasięgu ROAD_RADIUS_M.
Import tylko podnosi status `unverified` → `verified`; nie obniża go i nie rusza `rejected_*`.

Reguła dzielnicy: punkt w poligonie; gdy punkt leży dokładnie na granicy, wygrywa
dzielnica o niższym kodzie TERYT. Przejazdy bliżej niż BOUNDARY_M od granicy są flagowane.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass, field

import psycopg

from app.etl.bdot10k import BDOT_URL, GROUND_LEVEL, Segment
from app.etl.crossing_import import UTK_SOURCE
from app.etl.prg import PRG_WFS_URL, District

RAIL_RADIUS_M = 15.0
ROAD_RADIUS_M = 30.0
BOUNDARY_M = 10.0
ROAD_PREFILTER_M = 100.0
PRG_SOURCE = "prg_jednostki_ewidencyjne"
BDOT_SOURCE = "bdot10k_1465"
FLAG_CODES = [
    "outside_warsaw",
    "near_district_boundary",
    "no_track_nearby",
    "no_road_nearby",
    "grade_separation_suspected",
    "track_inactive",
]


@dataclass
class TopologySummary:
    job_id: int
    districts: int = 0
    rail_segments: int = 0
    road_segments: int = 0
    newly_verified: int = 0
    flags: dict[str, int] = field(default_factory=dict)


def ensure_sources(conn: psycopg.Connection) -> tuple[int, int]:
    conn.execute(
        """
        INSERT INTO system.licenses (code, name, url, attribution_text,
                                     allows_storage, allows_derivatives, notes)
        VALUES ('gugik-pzgik-open', 'Dane PZGiK udostępniane nieodpłatnie (PRG, BDOT10k)',
                'https://www.geoportal.gov.pl/pl/dane/', 'Źródło: GUGiK (PRG, BDOT10k)',
                true, true,
                'Dane udostępniane bez opłat do dowolnego wykorzystania; podawać źródło.')
        ON CONFLICT (code) DO NOTHING
        """
    )
    conn.execute(
        """
        INSERT INTO system.sources (code, name, provider, url, license_id)
        SELECT v.code, v.name, 'GUGiK', v.url, l.license_id
        FROM (VALUES (%s, 'PRG - granice jednostek ewidencyjnych (dzielnice Warszawy)', %s),
                     (%s, 'BDOT10k - tory i jezdnie, powiat 1465 (Warszawa)', %s)
             ) AS v(code, name, url)
        JOIN system.licenses l ON l.code = 'gugik-pzgik-open'
        ON CONFLICT (code) DO NOTHING
        """,
        (PRG_SOURCE, PRG_WFS_URL, BDOT_SOURCE, BDOT_URL),
    )
    rows = dict(
        conn.execute(
            "SELECT code, source_id FROM system.sources WHERE code = ANY(%s)",
            ([PRG_SOURCE, BDOT_SOURCE],),
        ).fetchall()
    )
    return rows[PRG_SOURCE], rows[BDOT_SOURCE]


def start_job(conn: psycopg.Connection, source_id: int, params: dict) -> int:
    return conn.execute(
        "INSERT INTO system.import_jobs (source_id, snapshot_label, params) "
        "VALUES (%s, to_char(now(), 'YYYY-MM-DD'), %s) RETURNING job_id",
        (source_id, json.dumps(params)),
    ).fetchone()[0]


def load_districts(conn: psycopg.Connection, districts: list[District], source_id: int) -> int:
    for district in districts:
        conn.execute(
            """
            INSERT INTO spatial.districts (name, teryt, source_id, geom)
            VALUES (%s, %s, %s, ST_Multi(ST_CollectionExtract(
                        ST_MakeValid(ST_GeomFromText(%s, 2180)), 3)))
            ON CONFLICT (teryt) DO UPDATE
            SET name = EXCLUDED.name, geom = EXCLUDED.geom, source_id = EXCLUDED.source_id
            """,
            (district.name, district.teryt, source_id, district.wkt),
        )
    return len(districts)


def _int_or_none(value: str | None) -> int | None:
    return int(value) if value and value.isdigit() and int(value) > 0 else None


def load_rail_segments(
    conn: psycopg.Connection, segments: Iterable[Segment], source_id: int
) -> int:
    rows = [
        (
            source_id,
            s.local_id,
            s.attributes.get("numerLinii"),
            s.attributes.get("polozenie"),
            s.attributes.get("kategoriaIstnienia"),
            s.attributes.get("funkcjaToru"),
            _int_or_none(s.attributes.get("liczbaTorow")),
            s.wkt,
        )
        for s in segments
    ]
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO spatial.rail_segments
                (source_id, source_object_id, line_number, level_position, existence,
                 track_function, track_count, geom)
            VALUES (%s, %s, %s, %s, %s, %s, %s, ST_GeomFromText(%s, 2180))
            ON CONFLICT (source_id, source_object_id) DO UPDATE
            SET line_number = EXCLUDED.line_number, level_position = EXCLUDED.level_position,
                existence = EXCLUDED.existence, track_function = EXCLUDED.track_function,
                track_count = EXCLUDED.track_count, geom = EXCLUDED.geom
            """,
            rows,
        )
    return len(rows)


def load_road_segments(
    conn: psycopg.Connection, segments: Iterable[Segment], source_id: int
) -> int:
    rows = [
        (
            source_id,
            s.local_id,
            " ".join(
                part
                for part in (s.attributes.get("ulicaCecha"), s.attributes.get("ulicaNazwa1"))
                if part
            )
            or None,
            s.attributes.get("klasaDrogi"),
            s.attributes.get("polozenie"),
            s.attributes.get("kategoriaIstnienia"),
            s.attributes.get("kategoriaZarzadzania"),
            s.attributes.get("numerDrogi"),
            s.wkt,
        )
        for s in segments
    ]
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO spatial.road_segments
                (source_id, source_object_id, road_name, road_class, level_position, existence,
                 management_category, road_number, geom)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, ST_GeomFromText(%s, 2180))
            ON CONFLICT (source_id, source_object_id) DO UPDATE
            SET road_name = EXCLUDED.road_name, road_class = EXCLUDED.road_class,
                level_position = EXCLUDED.level_position, existence = EXCLUDED.existence,
                management_category = EXCLUDED.management_category,
                road_number = EXCLUDED.road_number, geom = EXCLUDED.geom
            """,
            rows,
        )
    return len(rows)


def crossing_points(conn: psycopg.Connection) -> list[tuple[float, float]]:
    return [
        (row[0], row[1])
        for row in conn.execute("SELECT ST_X(geom), ST_Y(geom) FROM spatial.crossings")
    ]


METRICS_SQL = """
SELECT c.crossing_id, c.category,
  (SELECT d.district_id FROM spatial.districts d
    WHERE ST_Intersects(d.geom, c.geom) ORDER BY d.teryt LIMIT 1) AS district_id,
  (SELECT min(ST_Distance(ST_Boundary(d.geom), c.geom)) FROM spatial.districts d
    WHERE ST_DWithin(d.geom, c.geom, %(boundary)s)) AS boundary_m,
  (SELECT min(ST_Distance(r.geom, c.geom)) FROM spatial.rail_segments r
    WHERE ST_DWithin(r.geom, c.geom, %(rail)s) AND r.level_position = %(ground)s) AS rail_ground_m,
  (SELECT min(ST_Distance(r.geom, c.geom)) FROM spatial.rail_segments r
    WHERE ST_DWithin(r.geom, c.geom, %(rail)s)
      AND r.level_position IS DISTINCT FROM %(ground)s) AS rail_other_m,
  (SELECT r.existence FROM spatial.rail_segments r
    WHERE ST_DWithin(r.geom, c.geom, %(rail)s) AND r.level_position = %(ground)s
    ORDER BY ST_Distance(r.geom, c.geom) LIMIT 1) AS rail_existence,
  (SELECT min(ST_Distance(r.geom, c.geom)) FROM spatial.road_segments r
    WHERE ST_DWithin(r.geom, c.geom, %(road)s) AND r.level_position = %(ground)s) AS road_ground_m,
  (SELECT min(ST_Distance(r.geom, c.geom)) FROM spatial.road_segments r
    WHERE ST_DWithin(r.geom, c.geom, %(road)s)
      AND r.level_position IS DISTINCT FROM %(ground)s) AS road_other_m
FROM spatial.crossings c
JOIN system.sources s ON s.source_id = c.source_id AND s.code = %(utk)s
"""

LINK_SQL = """
INSERT INTO spatial.{links} (crossing_id, segment_id, match_method, match_confidence)
SELECT c.crossing_id, r.segment_id, 'proximity_candidate',
       round(greatest(0, 1 - ST_Distance(r.geom, c.geom) / %(radius)s)::numeric, 2)
FROM spatial.crossings c
JOIN spatial.{segments} r
  ON ST_DWithin(r.geom, c.geom, %(radius)s) AND r.level_position = %(ground)s
WHERE c.district_id IS NOT NULL
ON CONFLICT (crossing_id, segment_id) DO UPDATE
SET match_confidence = EXCLUDED.match_confidence
WHERE spatial.{links}.match_method = 'proximity_candidate'
"""


def verify_crossings(conn: psycopg.Connection, summary: TopologySummary) -> None:
    conn.execute(
        "DELETE FROM system.quality_flags WHERE code = ANY(%s) AND resolved_at IS NULL",
        (FLAG_CODES,),
    )
    params = {
        "boundary": BOUNDARY_M,
        "rail": RAIL_RADIUS_M,
        "road": ROAD_RADIUS_M,
        "ground": GROUND_LEVEL,
        "utk": UTK_SOURCE,
    }

    def flag(crossing_id: int, code: str, severity: str, message: str) -> None:
        summary.flags[code] = summary.flags.get(code, 0) + 1
        conn.execute(
            "INSERT INTO system.quality_flags "
            "(entity_schema, entity_table, entity_id, code, severity, message, job_id) "
            "VALUES ('spatial', 'crossings', %s, %s, %s, %s, %s)",
            (str(crossing_id), code, severity, message, summary.job_id),
        )

    confirmed: list[int] = []
    for row in conn.execute(METRICS_SQL, params).fetchall():
        (
            crossing_id,
            category,
            district_id,
            boundary_m,
            rail_ground,
            rail_other,
            rail_existence,
            road_ground,
            road_other,
        ) = row
        conn.execute(
            "UPDATE spatial.crossings SET district_id = %s WHERE crossing_id = %s "
            "AND district_id IS DISTINCT FROM %s",
            (district_id, crossing_id, district_id),
        )
        if district_id is None:
            flag(crossing_id, "outside_warsaw", "info", "Poza granicami dzielnic Warszawy.")
            continue
        if boundary_m is not None and boundary_m < BOUNDARY_M:
            flag(
                crossing_id,
                "near_district_boundary",
                "info",
                f"{boundary_m:.1f} m od granicy dzielnicy; przypisanie do sprawdzenia.",
            )
        needs_road = category != "E"
        rail_ok = rail_ground is not None
        road_ok = road_ground is not None or not needs_road
        if not rail_ok:
            if rail_other is not None:
                flag(
                    crossing_id,
                    "grade_separation_suspected",
                    "warning",
                    f"Najbliższy tor ({rail_other:.1f} m) nie leży na poziomie gruntu.",
                )
            else:
                flag(
                    crossing_id,
                    "no_track_nearby",
                    "warning",
                    f"Brak toru kolejowego w promieniu {RAIL_RADIUS_M:.0f} m.",
                )
        elif rail_existence and rail_existence != "eksploatowany":
            flag(crossing_id, "track_inactive", "info", f"Tor w BDOT10k: {rail_existence}.")
        if needs_road and road_ground is None:
            if road_other is not None:
                flag(
                    crossing_id,
                    "grade_separation_suspected",
                    "warning",
                    f"Najbliższa jezdnia ({road_other:.1f} m) nie leży na poziomie gruntu.",
                )
            else:
                flag(
                    crossing_id,
                    "no_road_nearby",
                    "warning",
                    f"Brak jezdni w promieniu {ROAD_RADIUS_M:.0f} m.",
                )
        if rail_ok and road_ok:
            confirmed.append(crossing_id)

    summary.newly_verified = conn.execute(
        "UPDATE spatial.crossings SET verification_status = 'verified', verified_at = now() "
        "WHERE crossing_id = ANY(%s) AND verification_status = 'unverified'",
        (confirmed,),
    ).rowcount
    for links, segments, radius in (
        ("crossing_rail_segments", "rail_segments", RAIL_RADIUS_M),
        ("crossing_road_segments", "road_segments", ROAD_RADIUS_M),
    ):
        conn.execute(
            LINK_SQL.format(links=links, segments=segments),
            {"radius": radius, "ground": GROUND_LEVEL},
        )


def finish_job(conn: psycopg.Connection, summary: TopologySummary) -> None:
    written = summary.districts + summary.rail_segments + summary.road_segments
    conn.execute(
        "UPDATE system.import_jobs SET status = 'succeeded', finished_at = now(), "
        "records_read = %s, records_written = %s WHERE job_id = %s",
        (written, written, summary.job_id),
    )
