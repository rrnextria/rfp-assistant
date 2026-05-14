"""documents.category column + CHECK + index.

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CATEGORIES = ("general", "product_doc", "past_proposal", "contract", "boilerplate_snippet")


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("category", sa.String, nullable=False, server_default="general"),
    )
    op.create_check_constraint(
        "ck_documents_category",
        "documents",
        f"category IN {CATEGORIES}",
    )
    op.create_index(
        "ix_documents_tenant_category",
        "documents",
        ["tenant_id", "category"],
    )


def downgrade() -> None:
    op.drop_index("ix_documents_tenant_category", table_name="documents")
    op.drop_constraint("ck_documents_category", "documents", type_="check")
    op.drop_column("documents", "category")
