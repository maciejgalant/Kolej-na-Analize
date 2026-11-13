"""Dzielnice i ewidencja przejazdów (RSA-011, część bez analiz).

Geometrie wychodzą jako GeoJSON w WGS84 (EPSG:4326). Domyślnie zwracane są tylko
przejazdy zweryfikowane i leżące w granicach dzielnic Warszawy.
"""

from typing import Annotated, Any, Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.analysis.rps import ROAD_CLASS_VEHICLES
from app.db import get_connection

router = APIRouter(tags=["ewidencja"])

ROAD_CLASSES = list(ROAD_CLASS_VEHICLES)  # od najniższej do najwyższej klasy
LATEST_RUN_SQL = (
    "SELECT run_id FROM analysis.runs WHERE status = 'completed' "
    "ORDER BY finished_at DESC, run_id DESC LIMIT 1"
)
DISCLAIMER = (
    "RPS to autorski priorytet do dalszej oceny, a nie prognoza wypadków ani urzędowa "
    "klasyfikacja przejazdów. Wagi i tabele punktowe są eksperymentalne i niezwalidowane."
)

Connection = Annotated[psycopg.Connection, Depends(get_connection)]
Category = Literal["A", "B", "C", "D", "E", "F"]
StatusFilter = Literal[
    "verified", "unverified", "rejected_grade_separated", "rejected_other", "all"
]


class Feature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: int
    geometry: dict[str, Any]
    properties: dict[str, Any]


class FeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature]


class CrossingCollection(FeatureCollection):
    total: int
    limit: int
    offset: int


class Attribute(BaseModel):
    code: str
    value: str | None
    confidence: str
    source: str


class QualityFlag(BaseModel):
    code: str
    severity: str
    message: str | None


class LinkedRoad(BaseModel):
    name: str | None
    road_class: str | None
    management: str | None
    distance_m: float


class LinkedTrack(BaseModel):
    line_number: str | None
    track_function: str | None
    track_count: int | None
    existence: str | None
    distance_m: float


class SourceInfo(BaseModel):
    name: str
    attribution: str | None
    license_verified: bool


class RailFlow(BaseModel):
    """Planowa liczba pociągów pasażerskich w tygodniu odniesienia."""

    weekday_avg: float
    saturday: int | None
    sunday: int | None
    period_start: str
    period_end: str
    unit: str
    evidence_type: str
    method_version: str
    source: str | None


class PriorityComponent(BaseModel):
    component: Literal["T", "P", "G", "H"]
    value: float | None
    weight: float
    status: str
    detail: dict[str, Any]


class Priority(BaseModel):
    """Wynik RPS z ostatniego zakończonego przebiegu; to priorytet oceny, nie prognoza."""

    run_id: int
    method_version: str
    rps: float | None
    rank: int | None
    rank_best: int | None
    rank_worst: int | None
    ranked_total: int
    completeness_pct: float
    quality_status: str
    components: list[PriorityComponent]


class AnalysisRun(BaseModel):
    run_id: int
    method_version: str
    period_start: str
    period_end: str
    finished_at: str
    is_demo: bool
    weights: dict[str, float]
    scored: int
    ranked: int
    disclaimer: str


class CrossingDetail(BaseModel):
    crossing_id: int
    official_id: str | None
    name: str | None
    category: str | None
    is_pedestrian: bool
    verification_status: str
    verified_at: str | None
    district_id: int | None
    district_name: str | None
    lon: float
    lat: float
    attributes: list[Attribute]
    quality_flags: list[QualityFlag]
    roads: list[LinkedRoad]
    tracks: list[LinkedTrack]
    sources: list[SourceInfo]
    rail_flow: RailFlow | None
    priority: Priority | None


@router.get("/districts", response_model=FeatureCollection)
def districts(conn: Connection) -> FeatureCollection:
    rows = conn.execute(
        """
        SELECT d.district_id, d.name, d.teryt,
               ST_AsGeoJSON(ST_Transform(ST_Multi(
                   ST_SimplifyPreserveTopology(d.geom, 10)), 4326), 6)::json AS geometry,
               count(c.*) FILTER (WHERE c.verification_status = 'verified') AS crossings_verified,
               count(c.*) FILTER (WHERE c.verification_status = 'verified'
                                    AND c.category IS DISTINCT FROM 'E') AS road_crossings,
               count(c.*) FILTER (WHERE c.verification_status = 'verified'
                                    AND c.category = 'E') AS pedestrian_crossings
        FROM spatial.districts d
        LEFT JOIN spatial.crossings c ON c.district_id = d.district_id
        GROUP BY d.district_id ORDER BY d.name
        """
    ).fetchall()
    return FeatureCollection(
        features=[
            Feature(
                id=row["district_id"],
                geometry=row.pop("geometry"),
                properties=row,
            )
            for row in rows
        ]
    )


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    try:
        west, south, east, north = (float(part) for part in bbox.split(","))
    except ValueError as error:
        raise HTTPException(422, "bbox: oczekiwano 'minLon,minLat,maxLon,maxLat'.") from error
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise HTTPException(422, "bbox: nieprawidłowy zakres współrzędnych.")
    return west, south, east, north


@router.get("/crossings", response_model=CrossingCollection)
def crossings(
    conn: Connection,
    district_id: Annotated[int | None, Query(ge=1)] = None,
    bbox: Annotated[str | None, Query(description="minLon,minLat,maxLon,maxLat (WGS84)")] = None,
    verification_status: StatusFilter = "verified",
    category: Annotated[list[Category] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CrossingCollection:
    box = _parse_bbox(bbox)
    where = ["c.district_id IS NOT NULL"]
    params: dict[str, Any] = {"limit": limit, "offset": offset, "classes": ROAD_CLASSES}
    if district_id is not None:
        where.append("c.district_id = %(district_id)s")
        params["district_id"] = district_id
    if verification_status != "all":
        where.append("c.verification_status = %(status)s")
        params["status"] = verification_status
    if category:
        where.append("c.category = ANY(%(categories)s)")
        params["categories"] = list(category)
    if box:
        where.append(
            "c.geom && ST_Transform(ST_MakeEnvelope(%(w)s, %(s)s, %(e)s, %(n)s, 4326), 2180)"
        )
        params.update(w=box[0], s=box[1], e=box[2], n=box[3])
    condition = " AND ".join(where)
    total = conn.execute(
        f"SELECT count(*) AS n FROM spatial.crossings c WHERE {condition}", params
    ).fetchone()["n"]
    rows = conn.execute(
        f"""
        SELECT c.crossing_id, c.official_id, c.name, c.category,
               coalesce(c.category = 'E', false) AS is_pedestrian,
               c.verification_status, c.district_id, d.name AS district_name,
               (SELECT a.value_text FROM safety.crossing_attributes a
                 WHERE a.crossing_id = c.crossing_id AND a.attribute_code = 'manager'
                 LIMIT 1) AS manager,
               (SELECT count(*) FROM system.quality_flags f
                 WHERE f.entity_schema = 'spatial' AND f.entity_table = 'crossings'
                   AND f.entity_id = c.crossing_id::text AND f.resolved_at IS NULL
                   AND f.severity <> 'info') AS warnings,
               (SELECT round(avg(f.train_count))::int FROM rail.crossing_flow f
                 WHERE f.crossing_id = c.crossing_id AND f.evidence_type = 'planned'
                   AND extract(isodow FROM f.period_start AT TIME ZONE 'Europe/Warsaw') < 6
               ) AS trains_weekday,
               s.rank, s.rps::float AS rps,
               -- Ulica przejazdu do opisu na liście: jezdnia o najwyższej klasie do 15 m,
               -- a gdy takiej nie ma, najbliższa nazwana do 30 m.
               (SELECT r.road_name FROM spatial.road_segments r
                 WHERE r.road_name IS NOT NULL AND ST_DWithin(r.geom, c.geom, 30)
                 ORDER BY ST_Distance(r.geom, c.geom) > 15,
                          array_position(%(classes)s::text[], r.road_class) DESC NULLS LAST,
                          ST_Distance(r.geom, c.geom)
                 LIMIT 1) AS street,
               ST_AsGeoJSON(ST_Transform(c.geom, 4326), 6)::json AS geometry
        FROM spatial.crossings c
        JOIN spatial.districts d ON d.district_id = c.district_id
        LEFT JOIN analysis.risk_scores s
               ON s.crossing_id = c.crossing_id AND s.run_id = ({LATEST_RUN_SQL})
        WHERE {condition}
        ORDER BY d.name, c.name, c.crossing_id
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        params,
    ).fetchall()
    return CrossingCollection(
        total=total,
        limit=limit,
        offset=offset,
        features=[
            Feature(id=row["crossing_id"], geometry=row.pop("geometry"), properties=row)
            for row in rows
        ],
    )


@router.get("/crossings/{crossing_id}", response_model=CrossingDetail)
def crossing_detail(crossing_id: int, conn: Connection) -> CrossingDetail:
    row = conn.execute(
        """
        SELECT c.crossing_id, c.official_id, c.name, c.category,
               coalesce(c.category = 'E', false) AS is_pedestrian, c.verification_status,
               to_char(c.verified_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
                   AS verified_at,
               c.district_id, d.name AS district_name,
               ST_X(ST_Transform(c.geom, 4326)) AS lon, ST_Y(ST_Transform(c.geom, 4326)) AS lat
        FROM spatial.crossings c
        LEFT JOIN spatial.districts d ON d.district_id = c.district_id
        WHERE c.crossing_id = %s
        """,
        (crossing_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Nie ma przejazdu o takim identyfikatorze.")
    attributes = conn.execute(
        """
        SELECT a.attribute_code AS code, a.value_text AS value,
               a.confidence_status AS confidence, s.name AS source
        FROM safety.crossing_attributes a JOIN system.sources s USING (source_id)
        WHERE a.crossing_id = %s ORDER BY s.name, a.attribute_code
        """,
        (crossing_id,),
    ).fetchall()
    flags = conn.execute(
        """
        SELECT code, severity, message FROM system.quality_flags
        WHERE entity_schema = 'spatial' AND entity_table = 'crossings'
          AND entity_id = %s AND resolved_at IS NULL ORDER BY severity DESC, code
        """,
        (str(crossing_id),),
    ).fetchall()
    roads = conn.execute(
        """
        SELECT DISTINCT ON (r.road_name, r.road_class)
               r.road_name AS name, r.road_class, r.management_category AS management,
               round(ST_Distance(r.geom, c.geom)::numeric, 1)::float AS distance_m
        FROM spatial.crossing_road_segments l
        JOIN spatial.road_segments r USING (segment_id)
        JOIN spatial.crossings c USING (crossing_id)
        WHERE l.crossing_id = %s
        ORDER BY r.road_name, r.road_class, ST_Distance(r.geom, c.geom)
        """,
        (crossing_id,),
    ).fetchall()
    tracks = conn.execute(
        """
        SELECT r.line_number, r.track_function, r.track_count, r.existence,
               round(ST_Distance(r.geom, c.geom)::numeric, 1)::float AS distance_m
        FROM spatial.crossing_rail_segments l
        JOIN spatial.rail_segments r USING (segment_id)
        JOIN spatial.crossings c USING (crossing_id)
        WHERE l.crossing_id = %s ORDER BY ST_Distance(r.geom, c.geom)
        """,
        (crossing_id,),
    ).fetchall()
    sources = conn.execute(
        """
        SELECT DISTINCT s.name, l.attribution_text AS attribution,
               coalesce(l.allows_storage, false) AS license_verified
        FROM system.sources s LEFT JOIN system.licenses l USING (license_id)
        WHERE s.source_id IN (
            SELECT source_id FROM spatial.crossings WHERE crossing_id = %(id)s
            UNION SELECT source_id FROM safety.crossing_attributes WHERE crossing_id = %(id)s
            UNION SELECT r.source_id FROM spatial.crossing_rail_segments l
                  JOIN spatial.rail_segments r USING (segment_id) WHERE l.crossing_id = %(id)s
            UNION SELECT r.source_id FROM spatial.crossing_road_segments l
                  JOIN spatial.road_segments r USING (segment_id) WHERE l.crossing_id = %(id)s)
        ORDER BY s.name
        """,
        {"id": crossing_id},
    ).fetchall()
    flow = conn.execute(
        """
        SELECT round(avg(f.train_count) FILTER (WHERE dow < 6)::numeric, 1)::float
                   AS weekday_avg,
               max(f.train_count) FILTER (WHERE dow = 6) AS saturday,
               max(f.train_count) FILTER (WHERE dow = 7) AS sunday,
               to_char(min(local_start), 'YYYY-MM-DD') AS period_start,
               to_char(max(local_start), 'YYYY-MM-DD') AS period_end,
               min(f.unit) AS unit, min(f.evidence_type) AS evidence_type,
               min(f.method_version) AS method_version
        FROM (SELECT *, period_start AT TIME ZONE 'Europe/Warsaw' AS local_start,
                     extract(isodow FROM period_start AT TIME ZONE 'Europe/Warsaw') AS dow
              FROM rail.crossing_flow
              WHERE crossing_id = %s AND evidence_type = 'planned') f
        HAVING count(*) FILTER (WHERE dow < 6) > 0
        """,
        (crossing_id,),
    ).fetchone()
    if flow is not None:
        flow["source"] = (
            conn.execute(
                "SELECT name FROM system.sources WHERE code = 'gtfs_polish_trains'"
            ).fetchone()
            or {}
        ).get("name")
    priority = conn.execute(
        f"""
        SELECT s.run_id, r.method_version, s.rps::float AS rps, s.rank, s.rank_best,
               s.rank_worst, s.completeness_pct::float AS completeness_pct, s.quality_status,
               (SELECT count(*) FROM analysis.risk_scores x
                 WHERE x.run_id = s.run_id AND x.rank IS NOT NULL) AS ranked_total
        FROM analysis.risk_scores s JOIN analysis.runs r USING (run_id)
        WHERE s.crossing_id = %s AND s.run_id = ({LATEST_RUN_SQL})
        """,
        (crossing_id,),
    ).fetchone()
    if priority is not None:
        priority["components"] = conn.execute(
            "SELECT component, value::float AS value, weight::float AS weight, status, detail "
            "FROM analysis.components WHERE run_id = %s AND crossing_id = %s "
            "ORDER BY array_position(ARRAY['T', 'P', 'G', 'H'], component)",
            (priority["run_id"], crossing_id),
        ).fetchall()
    return CrossingDetail(
        **row,
        priority=priority,
        rail_flow=flow,
        attributes=attributes,
        quality_flags=flags,
        roads=roads,
        tracks=tracks,
        sources=sources,
    )


@router.get("/analysis/latest", response_model=AnalysisRun)
def latest_analysis(conn: Connection) -> AnalysisRun:
    row = conn.execute(
        f"""
        SELECT r.run_id, r.method_version, r.is_demo, r.parameters -> 'weights' AS weights,
               to_char(r.period_start AT TIME ZONE 'Europe/Warsaw', 'YYYY-MM-DD') AS period_start,
               to_char(r.period_end AT TIME ZONE 'Europe/Warsaw' - interval '1 day',
                       'YYYY-MM-DD') AS period_end,
               to_char(r.finished_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
                   AS finished_at,
               (SELECT count(*) FROM analysis.risk_scores s WHERE s.run_id = r.run_id) AS scored,
               (SELECT count(*) FROM analysis.risk_scores s
                 WHERE s.run_id = r.run_id AND s.rank IS NOT NULL) AS ranked
        FROM analysis.runs r WHERE r.run_id = ({LATEST_RUN_SQL})
        """
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Nie ma jeszcze zakończonego przebiegu analizy.")
    return AnalysisRun(**row, disclaimer=DISCLAIMER)
