"""Profil godzinowy planowych pociągów na przejeździe (RSA-018).

Revision ID: 0009
Revises: 0008
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE rail.crossing_flow
            -- liczba pociągów w każdej godzinie dnia kalendarzowego (0–23, czas lokalny)
            ADD COLUMN hourly_profile jsonb
                CHECK (hourly_profile IS NULL OR jsonb_array_length(hourly_profile) = 24),
            -- kursy, dla których nie dało się wyznaczyć godziny przejazdu
            ADD COLUMN hourly_unplaced integer CHECK (hourly_unplaced >= 0)
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE rail.crossing_flow DROP COLUMN hourly_profile, DROP COLUMN hourly_unplaced"
    )
