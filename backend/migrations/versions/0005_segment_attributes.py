"""Atrybuty odcinków torów i dróg potrzebne do weryfikacji przejazdów (BDOT10k).

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE spatial.rail_segments
            -- położenie względem gruntu wg BDOT10k; NULL = nieznane
            ADD COLUMN level_position text,
            ADD COLUMN existence      text,
            ADD COLUMN track_function text,
            ADD COLUMN track_count    smallint CHECK (track_count > 0)
        """
    )
    op.execute(
        """
        ALTER TABLE spatial.road_segments
            ADD COLUMN level_position      text,
            ADD COLUMN existence           text,
            ADD COLUMN management_category text,
            ADD COLUMN road_number         text
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE spatial.road_segments DROP COLUMN level_position, DROP COLUMN existence, "
        "DROP COLUMN management_category, DROP COLUMN road_number"
    )
    op.execute(
        "ALTER TABLE spatial.rail_segments DROP COLUMN level_position, DROP COLUMN existence, "
        "DROP COLUMN track_function, DROP COLUMN track_count"
    )
