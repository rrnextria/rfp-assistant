"""Add score_boosts JSONB column to win_loss_records

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-18

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    if not _column_exists("win_loss_records", "score_boosts"):
        op.add_column(
            "win_loss_records",
            sa.Column(
                "score_boosts",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default="{}",
            ),
        )


def downgrade() -> None:
    if _column_exists("win_loss_records", "score_boosts"):
        op.drop_column("win_loss_records", "score_boosts")
