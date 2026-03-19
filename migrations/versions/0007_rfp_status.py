"""Add status column to rfps table

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-19

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # Add status column to rfps (idempotent)
    exists = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='rfps' AND column_name='status'"
    )).first()
    if not exists:
        op.add_column("rfps", sa.Column("status", sa.String(50), nullable=False, server_default="draft"))


def downgrade() -> None:
    op.drop_column("rfps", "status")
