"""Schematy safety i analysis: cechy przejazdów, zdarzenia, przebiegi analiz i RPS.

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA safety")
    op.execute("CREATE SCHEMA analysis")
    op.execute(
        """
        CREATE TABLE safety.crossing_attributes (
            attribute_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            crossing_id    bigint NOT NULL
                           REFERENCES spatial.crossings (crossing_id) ON DELETE CASCADE,
            attribute_code text NOT NULL,
            value_text     text,
            value_num      numeric,
            unit           text,
            confidence_status text NOT NULL DEFAULT 'unknown'
                           CHECK (confidence_status IN ('confirmed', 'probable', 'unknown')),
            source_id      integer NOT NULL REFERENCES system.sources (source_id),
            observed_at    timestamptz,
            UNIQUE (crossing_id, attribute_code, source_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE safety.incidents (
            incident_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_id        integer NOT NULL REFERENCES system.sources (source_id),
            source_object_id text NOT NULL,
            -- NULL, gdy zdarzenia nie da się wiarygodnie przypisać do przejazdu.
            crossing_id      bigint REFERENCES spatial.crossings (crossing_id) ON DELETE SET NULL,
            occurred_on      date NOT NULL,
            incident_type    text,
            severity         text,
            location_confidence text NOT NULL DEFAULT 'unknown'
                             CHECK (location_confidence IN ('exact', 'approximate', 'unknown')),
            confirmed        boolean NOT NULL DEFAULT false,
            geom             geometry(Point, 2180),
            UNIQUE (source_id, source_object_id)
        )
        """
    )
    op.execute("CREATE INDEX incidents_crossing_idx ON safety.incidents (crossing_id)")
    op.execute(
        """
        CREATE TABLE analysis.runs (
            run_id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            status         text NOT NULL DEFAULT 'running'
                           CHECK (status IN ('running', 'completed', 'failed')),
            method_version text NOT NULL,
            period_start   timestamptz NOT NULL,
            period_end     timestamptz NOT NULL,
            parameters     jsonb NOT NULL DEFAULT '{}'::jsonb,
            input_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
            is_demo        boolean NOT NULL DEFAULT false,
            started_at     timestamptz NOT NULL DEFAULT now(),
            finished_at    timestamptz,
            CHECK (period_end > period_start),
            CHECK (status = 'running' OR finished_at IS NOT NULL)
        )
        """
    )
    op.execute(
        "CREATE INDEX runs_latest_completed_idx ON analysis.runs (finished_at DESC) "
        "WHERE status = 'completed'"
    )
    op.execute(
        """
        CREATE TABLE analysis.risk_scores (
            run_id      bigint NOT NULL REFERENCES analysis.runs (run_id) ON DELETE CASCADE,
            crossing_id bigint NOT NULL
                        REFERENCES spatial.crossings (crossing_id) ON DELETE CASCADE,
            -- NULL = brak kluczowych danych; obiekt nie dostaje pozycji w rankingu.
            rps         numeric(5, 2) CHECK (rps BETWEEN 0 AND 100),
            rank        integer CHECK (rank >= 1),
            is_partial  boolean NOT NULL DEFAULT false,
            completeness_pct numeric(5, 2) CHECK (completeness_pct BETWEEN 0 AND 100),
            quality_status text NOT NULL DEFAULT 'unknown'
                        CHECK (quality_status IN ('ok', 'partial', 'modelled', 'unknown')),
            PRIMARY KEY (run_id, crossing_id),
            CHECK (rps IS NOT NULL OR rank IS NULL)
        )
        """
    )
    op.execute("CREATE INDEX risk_scores_rank_idx ON analysis.risk_scores (run_id, rank)")
    op.execute(
        """
        CREATE TABLE analysis.components (
            run_id      bigint NOT NULL,
            crossing_id bigint NOT NULL,
            component   text NOT NULL CHECK (component IN ('T', 'P', 'G', 'H')),
            -- NULL ze statusem 'unknown' zamiast 0.
            value       numeric(5, 2) CHECK (value BETWEEN 0 AND 100),
            weight      numeric(4, 3) NOT NULL CHECK (weight BETWEEN 0 AND 1),
            status      text NOT NULL CHECK (status IN ('ok', 'modelled', 'unknown')),
            detail      jsonb NOT NULL DEFAULT '{}'::jsonb,
            PRIMARY KEY (run_id, crossing_id, component),
            FOREIGN KEY (run_id, crossing_id)
                REFERENCES analysis.risk_scores (run_id, crossing_id) ON DELETE CASCADE,
            CHECK ((status = 'unknown') = (value IS NULL))
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP SCHEMA analysis CASCADE")
    op.execute("DROP SCHEMA safety CASCADE")
