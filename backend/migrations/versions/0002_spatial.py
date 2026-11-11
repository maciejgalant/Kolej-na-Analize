"""Schemat spatial: dzielnice, przejazdy, odcinki i relacje M:N.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SEGMENT_TABLE = """
CREATE TABLE spatial.{name} (
    segment_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id         integer NOT NULL REFERENCES system.sources (source_id),
    source_object_id  text NOT NULL,
    {extra}
    geom              geometry(LineString, 2180) NOT NULL CHECK (ST_IsValid(geom)),
    topology_verified boolean NOT NULL DEFAULT false,
    created_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, source_object_id)
)
"""

LINK_TABLE = """
CREATE TABLE spatial.{name} (
    crossing_id      bigint NOT NULL REFERENCES spatial.crossings (crossing_id) ON DELETE CASCADE,
    segment_id       bigint NOT NULL REFERENCES spatial.{segments} (segment_id) ON DELETE CASCADE,
    -- Sama bliskość geometryczna to tylko kandydat, nie potwierdzone powiązanie.
    match_method     text NOT NULL
                     CHECK (match_method IN ('manual', 'topology', 'proximity_candidate')),
    match_confidence numeric(3, 2) CHECK (match_confidence BETWEEN 0 AND 1),
    created_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (crossing_id, segment_id)
)
"""


def upgrade() -> None:
    op.execute("CREATE SCHEMA spatial")
    op.execute(
        """
        CREATE TABLE spatial.districts (
            district_id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            name        text NOT NULL UNIQUE,
            teryt       text UNIQUE,
            source_id   integer REFERENCES system.sources (source_id),
            geom        geometry(MultiPolygon, 2180) NOT NULL CHECK (ST_IsValid(geom))
        )
        """
    )
    op.execute("CREATE INDEX districts_geom_idx ON spatial.districts USING gist (geom)")
    op.execute(
        """
        CREATE TABLE spatial.crossings (
            crossing_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            official_id      text UNIQUE,
            name             text,
            source_id        integer NOT NULL REFERENCES system.sources (source_id),
            source_object_id text NOT NULL,
            geom             geometry(Point, 2180) NOT NULL,
            district_id      smallint REFERENCES spatial.districts (district_id),
            -- NULL = kategoria nieznana (nie zgadywać).
            category         text CHECK (category IN ('A', 'B', 'C', 'D', 'E', 'F')),
            verification_status text NOT NULL DEFAULT 'unverified'
                CHECK (verification_status IN
                       ('unverified', 'verified', 'rejected_grade_separated', 'rejected_other')),
            verified_at      timestamptz,
            created_at       timestamptz NOT NULL DEFAULT now(),
            updated_at       timestamptz NOT NULL DEFAULT now(),
            UNIQUE (source_id, source_object_id),
            CHECK (verification_status = 'unverified' OR verified_at IS NOT NULL)
        )
        """
    )
    op.execute("CREATE INDEX crossings_geom_idx ON spatial.crossings USING gist (geom)")
    op.execute("CREATE INDEX crossings_district_idx ON spatial.crossings (district_id)")
    op.execute(SEGMENT_TABLE.format(name="rail_segments", extra="line_number       text,"))
    op.execute(
        SEGMENT_TABLE.format(
            name="road_segments",
            extra="road_name         text,\n    road_class        text,",
        )
    )
    op.execute("CREATE INDEX rail_segments_geom_idx ON spatial.rail_segments USING gist (geom)")
    op.execute("CREATE INDEX road_segments_geom_idx ON spatial.road_segments USING gist (geom)")
    op.execute(LINK_TABLE.format(name="crossing_rail_segments", segments="rail_segments"))
    op.execute(LINK_TABLE.format(name="crossing_road_segments", segments="road_segments"))


def downgrade() -> None:
    op.execute("DROP SCHEMA spatial CASCADE")
