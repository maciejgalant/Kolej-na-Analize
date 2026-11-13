"""Punkty pomiarowe ruchu drogowego i ich powiązanie z przejazdami (RSA-007).

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        -- Punkt pomiarowy zarządcy drogi (np. ZDM APR: jeden punkt = przekrój, oba kierunki).
        CREATE TABLE road.stations (
            station_pk  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_id   integer NOT NULL REFERENCES system.sources (source_id),
            station_id  text NOT NULL,
            street      text,
            section     text,
            road_class  text,
            geom        geometry(Point, 2180) NOT NULL,
            UNIQUE (source_id, station_id)
        )
        """
    )
    op.execute("CREATE INDEX stations_geom_idx ON road.stations USING gist (geom)")
    op.execute(
        """
        -- 'direct'     — ta sama ulica, punkt na tyle blisko, że pomiar zastępuje model;
        -- 'validation' — ta sama ulica dalej od przejazdu: tylko do porównania z modelem.
        CREATE TABLE road.crossing_stations (
            crossing_id    bigint NOT NULL
                           REFERENCES spatial.crossings (crossing_id) ON DELETE CASCADE,
            station_pk     bigint NOT NULL REFERENCES road.stations (station_pk) ON DELETE CASCADE,
            distance_m     numeric(8, 1) NOT NULL CHECK (distance_m >= 0),
            match_type     text NOT NULL CHECK (match_type IN ('direct', 'validation')),
            method_version text NOT NULL,
            PRIMARY KEY (crossing_id, station_pk)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE road.measurements
            -- typ dni ujęty w średniej, np. 'miarodajny' (dzień roboczy bez zakłóceń)
            ADD COLUMN day_type text,
            -- średni profil dobowy: 24 liczby pojazdów na godzinę (0–23, czas lokalny)
            ADD COLUMN hourly_profile jsonb
                CHECK (hourly_profile IS NULL OR jsonb_array_length(hourly_profile) = 24),
            -- liczba dni w średniej
            ADD COLUMN days_count integer CHECK (days_count > 0)
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE road.measurements DROP COLUMN day_type, DROP COLUMN hourly_profile, "
        "DROP COLUMN days_count"
    )
    op.execute("DROP TABLE road.crossing_stations")
    op.execute("DROP TABLE road.stations")
