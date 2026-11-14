"""Pomiary ZDM na skrzyżowaniach: struktura pojazdów, piesi, rowerzyści (RSA-017).

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE road.measurements
            -- liczba pojazdów według rodzaju, np. {"SO": 3222, "SD": 260, "BUS": 27}
            ADD COLUMN composition jsonb,
            ADD COLUMN pedestrians integer CHECK (pedestrians >= 0),
            ADD COLUMN cyclists integer CHECK (cyclists >= 0)
        """
    )
    # 'intersection' — skrzyżowanie na ulicy przejazdu: liczby dotyczą całego węzła
    # (wszystkie wloty), więc nie zastępują natężenia w RPS.
    op.execute(
        "ALTER TABLE road.crossing_stations DROP CONSTRAINT crossing_stations_match_type_check"
    )
    op.execute(
        "ALTER TABLE road.crossing_stations ADD CONSTRAINT crossing_stations_match_type_check "
        "CHECK (match_type IN ('direct', 'validation', 'intersection'))"
    )


def downgrade() -> None:
    op.execute("DELETE FROM road.crossing_stations WHERE match_type = 'intersection'")
    op.execute(
        "ALTER TABLE road.crossing_stations DROP CONSTRAINT crossing_stations_match_type_check"
    )
    op.execute(
        "ALTER TABLE road.crossing_stations ADD CONSTRAINT crossing_stations_match_type_check "
        "CHECK (match_type IN ('direct', 'validation'))"
    )
    op.execute(
        "ALTER TABLE road.measurements DROP COLUMN composition, DROP COLUMN pedestrians, "
        "DROP COLUMN cyclists"
    )
