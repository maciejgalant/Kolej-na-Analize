"""Zapis ewidencji przejazdów do PostGIS i kontrola krzyżowa z OpenStreetMap (RSA-004).

Reguła weryfikacji: przejazd z rejestru UTK dostaje status `verified`, gdy w odległości
do MATCH_RADIUS_M leży punkt przejazdu/przejścia z OSM (dwa niezależne źródła wskazują
to samo miejsce). Pozostałe zostają `unverified` z flagą jakości do ręcznego przeglądu.
Statusy `rejected_*` nadane ręcznie nie są nadpisywane.
"""

import json
from dataclasses import dataclass

import psycopg

from app.etl.crossing_scan import Bbox, ScanResult
from app.etl.overpass import OsmCrossing

MATCH_RADIUS_M = 40.0
VALID_CATEGORIES = {"A", "B", "C", "D", "E", "F"}
UTK_SOURCE = "utk_przejazdy_wms"
OSM_SOURCE = "osm_overpass"
FLAG_CODES = [
    "category_unrecognised",
    "position_approximate",
    "duplicate_official_id",
    "no_osm_confirmation",
    "osm_type_mismatch",
    "osm_without_official_match",
    "wms_symbol_unidentified",
]


@dataclass
class ImportSummary:
    job_id: int
    written: int
    osm_points: int | None
    matched: int


def _ensure_sources(conn: psycopg.Connection) -> tuple[int, int]:
    conn.execute(
        """
        INSERT INTO system.licenses (code, name, url, attribution_text,
                                     allows_storage, allows_derivatives, notes)
        VALUES
          ('utk-geoportal-wms', 'Usługa WMS Przejazdy kolejowe (UTK/GUGiK)',
           'https://mapy.geoportal.gov.pl/wss/service/sdi/Przejazdy/get',
           'Dane: Urząd Transportu Kolejowego, zarządcy infrastruktury; usługa GUGiK',
           NULL, NULL,
           'Usługa nie deklaruje warunków ponownego wykorzystania - do potwierdzenia.'),
          ('odbl-1.0', 'Open Database License 1.0', 'https://www.openstreetmap.org/copyright',
           '© autorzy OpenStreetMap', true, true,
           'Wymagana atrybucja; baza pochodna na tej samej licencji.')
        ON CONFLICT (code) DO NOTHING
        """
    )
    conn.execute(
        """
        INSERT INTO system.sources (code, name, provider, url, license_id)
        SELECT v.code, v.name, v.provider, v.url, l.license_id
        FROM (VALUES
          ('utk_przejazdy_wms', 'Przejazdy kolejowe - warstwa UTK w Geoportalu',
           'UTK / GUGiK', 'https://mapy.geoportal.gov.pl/wss/service/sdi/Przejazdy/get',
           'utk-geoportal-wms'),
          ('osm_overpass', 'OpenStreetMap - przejazdy i przejścia (Overpass API)',
           'OpenStreetMap', 'https://overpass-api.de/', 'odbl-1.0')
        ) AS v(code, name, provider, url, license_code)
        JOIN system.licenses l ON l.code = v.license_code
        ON CONFLICT (code) DO NOTHING
        """
    )
    rows = dict(
        conn.execute(
            "SELECT code, source_id FROM system.sources WHERE code = ANY(%s)",
            ([UTK_SOURCE, OSM_SOURCE],),
        ).fetchall()
    )
    return rows[UTK_SOURCE], rows[OSM_SOURCE]


def bbox_to_wgs84(conn: psycopg.Connection, bbox: Bbox) -> tuple[float, float, float, float]:
    """Zwraca (south, west, north, east) w stopniach dla prostokąta w EPSG:2180."""
    row = conn.execute(
        "SELECT ST_YMin(g), ST_XMin(g), ST_YMax(g), ST_XMax(g) FROM "
        "(SELECT ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 2180), 4326) AS g) AS t",
        (bbox.e_min, bbox.n_min, bbox.e_max, bbox.n_max),
    ).fetchone()
    return float(row[0]), float(row[1]), float(row[2]), float(row[3])


def _flag(conn, job_id, table, entity_id, code, severity, message, schema="spatial") -> None:
    conn.execute(
        "INSERT INTO system.quality_flags "
        "(entity_schema, entity_table, entity_id, code, severity, message, job_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (schema, table, str(entity_id), code, severity, message, job_id),
    )


def _attribute(conn, crossing_id, code, value, confidence, source_id) -> None:
    conn.execute(
        """
        INSERT INTO safety.crossing_attributes
            (crossing_id, attribute_code, value_text, confidence_status, source_id, observed_at)
        VALUES (%s, %s, %s, %s, %s, now())
        ON CONFLICT (crossing_id, attribute_code, source_id)
        DO UPDATE SET value_text = EXCLUDED.value_text,
                      confidence_status = EXCLUDED.confidence_status,
                      observed_at = EXCLUDED.observed_at
        """,
        (crossing_id, code, value, confidence, source_id),
    )


def import_crossings(
    conn: psycopg.Connection,
    scan: ScanResult,
    osm: list[OsmCrossing] | None,
    bbox: Bbox,
    wms_requests: int = 0,
) -> ImportSummary:
    """Zapisuje wynik skanu w jednej transakcji. `osm=None` oznacza brak danych OSM."""
    with conn.transaction():
        utk_id, osm_id = _ensure_sources(conn)
        job_id = conn.execute(
            "INSERT INTO system.import_jobs (source_id, snapshot_label, params) "
            "VALUES (%s, to_char(now(), 'YYYY-MM-DD'), %s) RETURNING job_id",
            (
                utk_id,
                json.dumps(
                    {
                        "bbox_2180": [bbox.e_min, bbox.n_min, bbox.e_max, bbox.n_max],
                        "match_radius_m": MATCH_RADIUS_M,
                        "wms_requests": wms_requests,
                        "osm_used": osm is not None,
                    }
                ),
            ),
        ).fetchone()[0]
        conn.execute(
            "DELETE FROM system.quality_flags WHERE code = ANY(%s) AND resolved_at IS NULL",
            (FLAG_CODES,),
        )

        names: dict[str, int] = {}
        for crossing in scan.crossings:
            names[crossing.feature.name] = names.get(crossing.feature.name, 0) + 1

        ids: dict[str, int] = {}
        for crossing in scan.crossings:
            feature = crossing.feature
            category = feature.category_raw.strip().upper() or None
            category_ok = category in VALID_CATEGORIES
            unique_name = names[feature.name] == 1
            crossing_id = conn.execute(
                """
                INSERT INTO spatial.crossings
                    (official_id, name, source_id, source_object_id, geom, category)
                VALUES (%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 2180), %s)
                ON CONFLICT (source_id, source_object_id) DO UPDATE
                SET official_id = EXCLUDED.official_id, name = EXCLUDED.name,
                    geom = EXCLUDED.geom, category = EXCLUDED.category, updated_at = now()
                RETURNING crossing_id
                """,
                (
                    feature.name if unique_name else None,
                    feature.name,
                    utk_id,
                    feature.key,
                    round(crossing.east, 1),
                    round(crossing.north, 1),
                    category if category_ok else None,
                ),
            ).fetchone()[0]
            ids[feature.key] = crossing_id
            _attribute(conn, crossing_id, "manager", feature.manager or None, "confirmed", utk_id)
            _attribute(
                conn,
                crossing_id,
                "location_type",
                feature.location_type or None,
                "confirmed" if feature.location_type else "unknown",
                utk_id,
            )
            if not category_ok:
                _flag(
                    conn,
                    job_id,
                    "crossings",
                    crossing_id,
                    "category_unrecognised",
                    "warning",
                    f"Kategoria w źródle: '{feature.category_raw}'",
                )
            if crossing.approximate:
                _flag(
                    conn,
                    job_id,
                    "crossings",
                    crossing_id,
                    "position_approximate",
                    "info",
                    "Symbol zlewał się z sąsiednim; położenie z dokładnością ok. 10 m.",
                )
            if not unique_name:
                _flag(
                    conn,
                    job_id,
                    "crossings",
                    crossing_id,
                    "duplicate_official_id",
                    "warning",
                    f"Numer '{feature.name}' występuje u kilku zarządców.",
                )

        for east, north in scan.unidentified:
            _flag(
                conn,
                job_id,
                "wms_symbol",
                f"{east:.0f},{north:.0f}",
                "wms_symbol_unidentified",
                "warning",
                "Symbol na mapie UTK bez odpowiedzi GetFeatureInfo (EPSG:2180: E,N).",
                schema="external",
            )

        matched = 0
        if osm is not None:
            conn.execute(
                "CREATE TEMP TABLE tmp_osm (node_id bigint PRIMARY KEY, "
                "geom geometry(Point, 2180), tags jsonb) ON COMMIT DROP"
            )
            for node in osm:
                conn.execute(
                    "INSERT INTO tmp_osm VALUES (%s, ST_Transform(ST_SetSRID("
                    "ST_MakePoint(%s, %s), 4326), 2180), %s) ON CONFLICT DO NOTHING",
                    (node.node_id, node.lon, node.lat, json.dumps(node.tags)),
                )
            current = list(ids.values())
            pairs = conn.execute(
                """
                WITH pairs AS (
                    SELECT c.crossing_id, c.category, o.node_id, o.tags,
                           ST_Distance(c.geom, o.geom) AS dist,
                           row_number() OVER (PARTITION BY c.crossing_id
                                              ORDER BY ST_Distance(c.geom, o.geom)) AS rc,
                           row_number() OVER (PARTITION BY o.node_id
                                              ORDER BY ST_Distance(c.geom, o.geom)) AS ro
                    FROM spatial.crossings c
                    JOIN tmp_osm o ON ST_DWithin(c.geom, o.geom, %s)
                    WHERE c.crossing_id = ANY(%s)
                )
                SELECT crossing_id, category, node_id, tags, dist FROM pairs WHERE rc = 1 AND ro = 1
                """,
                (MATCH_RADIUS_M, current),
            ).fetchall()
            conn.execute(
                "DELETE FROM safety.crossing_attributes WHERE source_id = %s "
                "AND crossing_id = ANY(%s)",
                (osm_id, current),
            )
            matched_ids, matched_nodes = set(), set()
            for crossing_id, category, node_id, tags, dist in pairs:
                matched_ids.add(crossing_id)
                matched_nodes.add(node_id)
                _attribute(conn, crossing_id, "osm_node_id", str(node_id), "confirmed", osm_id)
                _attribute(conn, crossing_id, "osm_distance_m", f"{dist:.1f}", "confirmed", osm_id)
                for key, value in tags.items():
                    _attribute(conn, crossing_id, f"osm:{key}", value, "probable", osm_id)
                osm_pedestrian = tags.get("railway") == "crossing"
                if category is not None and osm_pedestrian != (category == "E"):
                    _flag(
                        conn,
                        job_id,
                        "crossings",
                        crossing_id,
                        "osm_type_mismatch",
                        "info",
                        f"Kategoria {category}, a w OSM railway={tags.get('railway')}.",
                    )
            matched = len(matched_ids)
            conn.execute(
                "UPDATE spatial.crossings SET verification_status = 'verified', "
                "verified_at = now() WHERE crossing_id = ANY(%s) "
                "AND verification_status = 'unverified'",
                (list(matched_ids),),
            )
            for crossing_id in set(current) - matched_ids:
                _flag(
                    conn,
                    job_id,
                    "crossings",
                    crossing_id,
                    "no_osm_confirmation",
                    "warning",
                    f"Brak punktu przejazdu w OSM w promieniu {MATCH_RADIUS_M:.0f} m.",
                )
            orphans = conn.execute(
                "SELECT node_id, round(ST_X(geom)), round(ST_Y(geom)), tags FROM tmp_osm "
                "WHERE node_id <> ALL(%s) AND geom && ST_MakeEnvelope(%s, %s, %s, %s, 2180)",
                (list(matched_nodes), bbox.e_min, bbox.n_min, bbox.e_max, bbox.n_max),
            ).fetchall()
            for node_id, east, north, tags in orphans:
                _flag(
                    conn,
                    job_id,
                    "osm_node",
                    node_id,
                    "osm_without_official_match",
                    "info",
                    f"E={east:.0f} N={north:.0f} railway={tags.get('railway')}",
                    schema="external",
                )

        conn.execute(
            "UPDATE system.import_jobs SET status = 'succeeded', finished_at = now(), "
            "records_read = %s, records_written = %s WHERE job_id = %s",
            (len(scan.crossings) + len(scan.unidentified), len(ids), job_id),
        )
    return ImportSummary(job_id, len(ids), None if osm is None else len(osm), matched)
