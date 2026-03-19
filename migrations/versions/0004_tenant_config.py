"""Add tenant_config column to users

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-18

"""
from __future__ import annotations
from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # tenant_config already added in 0002; this migration is a no-op placeholder
    # to maintain the migration chain described in the plan
    pass


def downgrade() -> None:
    pass
