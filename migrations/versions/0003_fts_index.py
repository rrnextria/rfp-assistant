"""Add FTS tsvector column to chunks

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-18

"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE chunks ADD COLUMN text_search tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', text)) STORED"
    )
    op.execute("CREATE INDEX ix_chunks_text_search_gin ON chunks USING GIN (text_search)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_text_search_gin")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS text_search")
