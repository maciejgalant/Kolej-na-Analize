"""Zakres pozycji w rankingu z analizy wrażliwości wag (RSA-010).

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE analysis.risk_scores
            -- najlepsza i najgorsza pozycja przy zaburzeniu wag; NULL, gdy brak pozycji
            ADD COLUMN rank_best  integer CHECK (rank_best >= 1),
            ADD COLUMN rank_worst integer CHECK (rank_worst >= 1),
            ADD CHECK (rank_best IS NULL OR rank_worst IS NULL OR rank_best <= rank_worst),
            ADD CHECK (rank IS NOT NULL OR (rank_best IS NULL AND rank_worst IS NULL))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE analysis.risk_scores DROP COLUMN rank_best, DROP COLUMN rank_worst")
