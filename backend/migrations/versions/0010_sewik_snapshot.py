"""Częściowy wykaz 20 rekordów SEWiK przekazany przez użytkownika.

Revision ID: 0010
Revises: 0009
"""

import csv
import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE safety.incidents ADD COLUMN metadata jsonb NOT NULL DEFAULT '{}'")
    connection = op.get_bind()
    source_id = connection.execute(
        sa.text(
            "INSERT INTO system.sources (code, name, provider, url) "
            "VALUES ('sewik_user_snapshot', 'SEWiK — częściowy zrzut użytkownika', "
            "'sewik.pl / dane policyjne SEWiK', 'https://sewik.pl/') "
            "ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name RETURNING source_id"
        )
    ).scalar_one()
    path = Path(__file__).parents[1] / "data" / "sewik_warsaw_user_snapshot.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            metadata = {
                "local_time": row["time"],
                "address": row["address"],
                "street_keys": row["street_keys"].split("|"),
                "place": row["place"],
                "injured": int(row["injured"]) if row["injured"] else None,
                "killed": None,
                "batch": "user-screenshot-2026-11-16",
                "coverage": "partial",
                "capture_method": "manual_transcription",
                "selection": "Związek z pociągami wskazany przez użytkownika; filtr nieutrwalony",
            }
            connection.execute(
                sa.text(
                    "INSERT INTO safety.incidents "
                    "(source_id, source_object_id, occurred_on, incident_type, metadata) "
                    "VALUES (:source_id, :object_id, CAST(:day AS date), :kind, "
                    "CAST(:metadata AS jsonb)) ON CONFLICT (source_id, source_object_id) DO NOTHING"
                ),
                {
                    "source_id": source_id,
                    "object_id": row["id"],
                    "day": row["date"],
                    "kind": "Inne" if row["id"] == "125699355" else "Zderzenie pojazdów boczne",
                    "metadata": json.dumps(metadata, ensure_ascii=False),
                },
            )


def downgrade() -> None:
    op.execute("""
        DELETE FROM safety.incidents WHERE source_id IN (
            SELECT source_id FROM system.sources WHERE code = 'sewik_user_snapshot'
        ) AND metadata->>'batch' = 'user-screenshot-2026-11-16'
    """)
    op.execute(
        "DELETE FROM system.sources WHERE code = 'sewik_user_snapshot' "
        "AND NOT EXISTS (SELECT 1 FROM safety.incidents i "
        "WHERE i.source_id = system.sources.source_id)"
    )
    op.execute("ALTER TABLE safety.incidents DROP COLUMN metadata")
