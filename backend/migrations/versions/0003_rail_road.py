"""Schematy rail i road: zdarzenia rozkładowe/wykonane, przepływy, pomiary drogowe.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

EVENT_COLUMNS = """
    event_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id       integer NOT NULL REFERENCES system.sources (source_id),
    import_job_id   bigint REFERENCES system.import_jobs (job_id) ON DELETE SET NULL,
    source_train_id text NOT NULL,
    service_date    date NOT NULL,
    sequence_no     integer NOT NULL CHECK (sequence_no >= 0),
    station_ref     text,
    segment_id      bigint REFERENCES spatial.rail_segments (segment_id)
"""


def upgrade() -> None:
    op.execute("CREATE SCHEMA rail")
    op.execute("CREATE SCHEMA road")
    op.execute(
        f"""
        CREATE TABLE rail.schedule_events (
            {EVENT_COLUMNS},
            planned_arrival   timestamptz,
            planned_departure timestamptz,
            UNIQUE (source_id, source_train_id, service_date, sequence_no),
            CHECK (planned_arrival IS NOT NULL OR planned_departure IS NOT NULL)
        )
        """
    )
    op.execute(
        f"""
        -- Zdarzenia raportowane przez źródło (stacje/posterunki), nie surowe pozycje GPS.
        CREATE TABLE rail.operation_events (
            {EVENT_COLUMNS},
            observed_arrival   timestamptz,
            observed_departure timestamptz,
            status  text NOT NULL DEFAULT 'unknown'
                    CHECK (status IN ('on_time', 'delayed', 'cancelled', 'partial', 'unknown')),
            delay_s integer,
            UNIQUE (source_id, source_train_id, service_date, sequence_no)
        )
        """
    )
    op.execute(
        "CREATE INDEX schedule_events_segment_idx "
        "ON rail.schedule_events (segment_id, service_date)"
    )
    op.execute(
        "CREATE INDEX operation_events_segment_idx "
        "ON rail.operation_events (segment_id, service_date)"
    )
    op.execute(
        """
        CREATE TABLE rail.crossing_flow (
            flow_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            crossing_id    bigint NOT NULL
                           REFERENCES spatial.crossings (crossing_id) ON DELETE CASCADE,
            period_start   timestamptz NOT NULL,
            period_end     timestamptz NOT NULL,
            -- NULL = brak danych; 0 oznacza potwierdzony brak pociągów w okresie.
            train_count    integer CHECK (train_count >= 0),
            unit           text NOT NULL DEFAULT 'trains/period',
            evidence_type  text NOT NULL
                           CHECK (evidence_type IN ('planned', 'observed', 'modelled')),
            coverage_pct   numeric(5, 2) CHECK (coverage_pct BETWEEN 0 AND 100),
            method_version text NOT NULL,
            created_at     timestamptz NOT NULL DEFAULT now(),
            CHECK (period_end > period_start),
            UNIQUE (crossing_id, period_start, period_end, evidence_type, method_version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE road.measurements (
            measurement_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_id      integer NOT NULL REFERENCES system.sources (source_id),
            import_job_id  bigint REFERENCES system.import_jobs (job_id) ON DELETE SET NULL,
            station_id     text NOT NULL,
            -- NULL do czasu zweryfikowanego dopasowania stanowiska do odcinka.
            segment_id     bigint REFERENCES spatial.road_segments (segment_id),
            period_start   timestamptz NOT NULL,
            period_end     timestamptz NOT NULL,
            -- NULL = brak pomiaru; nigdy nie wypełniać zerem.
            vehicles_count integer CHECK (vehicles_count >= 0),
            unit           text NOT NULL DEFAULT 'vehicles/period',
            direction      text NOT NULL DEFAULT 'both',
            quality_status text NOT NULL DEFAULT 'unknown'
                           CHECK (quality_status IN ('ok', 'partial', 'modelled', 'unknown')),
            CHECK (period_end > period_start),
            UNIQUE (source_id, station_id, period_start, period_end, direction)
        )
        """
    )
    op.execute("CREATE INDEX measurements_segment_idx ON road.measurements (segment_id)")
    op.execute(
        """
        -- Prędkości (km/h), nie natężenie. Tylko dane, które licencja pozwala buforować.
        CREATE TABLE road.live_flow (
            live_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_id     integer NOT NULL REFERENCES system.sources (source_id),
            segment_id    bigint NOT NULL
                          REFERENCES spatial.road_segments (segment_id) ON DELETE CASCADE,
            observed_at   timestamptz NOT NULL,
            speed_kmh     numeric(5, 1) CHECK (speed_kmh >= 0),
            free_flow_kmh numeric(5, 1) CHECK (free_flow_kmh >= 0),
            expires_at    timestamptz NOT NULL,
            CHECK (expires_at > observed_at)
        )
        """
    )
    op.execute("CREATE INDEX live_flow_expires_idx ON road.live_flow (expires_at)")


def downgrade() -> None:
    op.execute("DROP SCHEMA road CASCADE")
    op.execute("DROP SCHEMA rail CASCADE")
