"""Schemat system: źródła, licencje, zadania importu, flagi jakości.

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE SCHEMA system")
    op.execute(
        """
        CREATE TABLE system.licenses (
            license_id       integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            code             text NOT NULL UNIQUE,
            name             text NOT NULL,
            url              text,
            attribution_text text,
            -- NULL = jeszcze niezweryfikowane; nie traktować jak zgody.
            allows_storage     boolean,
            allows_derivatives boolean,
            retention_days   integer CHECK (retention_days > 0),
            notes            text,
            verified_at      timestamptz
        )
        """
    )
    op.execute(
        """
        CREATE TABLE system.sources (
            source_id   integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            code        text NOT NULL UNIQUE,
            name        text NOT NULL,
            provider    text,
            url         text,
            license_id  integer REFERENCES system.licenses (license_id),
            -- Dane syntetyczne/demonstracyjne muszą być odróżnialne od rzeczywistych.
            is_demo     boolean NOT NULL DEFAULT false,
            created_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE system.import_jobs (
            job_id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_id       integer NOT NULL REFERENCES system.sources (source_id),
            status          text NOT NULL DEFAULT 'running'
                            CHECK (status IN ('running', 'succeeded', 'failed')),
            snapshot_label  text,
            params          jsonb NOT NULL DEFAULT '{}'::jsonb,
            records_read    integer CHECK (records_read >= 0),
            records_written integer CHECK (records_written >= 0),
            error           text,
            started_at      timestamptz NOT NULL DEFAULT now(),
            finished_at     timestamptz,
            CHECK (status = 'running' OR finished_at IS NOT NULL)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE system.quality_flags (
            flag_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            entity_schema text NOT NULL,
            entity_table  text NOT NULL,
            entity_id     text NOT NULL,
            code          text NOT NULL,
            severity      text NOT NULL CHECK (severity IN ('info', 'warning', 'error')),
            message       text,
            job_id        bigint REFERENCES system.import_jobs (job_id) ON DELETE SET NULL,
            created_at    timestamptz NOT NULL DEFAULT now(),
            resolved_at   timestamptz
        )
        """
    )
    op.execute(
        "CREATE INDEX quality_flags_entity_idx "
        "ON system.quality_flags (entity_schema, entity_table, entity_id)"
    )


def downgrade() -> None:
    # Rozszerzenie postgis zostaje: mogą z niego korzystać inne obiekty bazy.
    op.execute("DROP SCHEMA system CASCADE")
