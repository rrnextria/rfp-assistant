"""past_proposals and contracts typed entity tables.

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "past_proposals",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("document_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("client_name", sa.String, nullable=True),
        sa.Column("industry_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("industries.id"), nullable=True),
        sa.Column("submitted_at", sa.Date, nullable=False),
        sa.Column("outcome", sa.String, nullable=False, server_default="pending"),
        sa.Column("outcome_reason", sa.Text, nullable=True),
        sa.Column("value_amount", sa.Numeric, nullable=True),
        sa.Column("value_currency", sa.CHAR(3), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("outcome IN ('won','lost','withdrawn','pending')",
                           name="ck_past_proposals_outcome"),
    )
    op.create_index("ix_past_proposals_tenant_outcome",
                    "past_proposals", ["tenant_id", "outcome"])

    op.create_table(
        "contracts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("document_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("client_name", sa.String, nullable=False),
        sa.Column("effective_date", sa.Date, nullable=False),
        sa.Column("expires_at", sa.Date, nullable=True),
        sa.Column("value_amount", sa.Numeric, nullable=True),
        sa.Column("value_currency", sa.CHAR(3), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_contracts_tenant_expires",
                    "contracts", ["tenant_id", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_contracts_tenant_expires", table_name="contracts")
    op.drop_table("contracts")
    op.drop_index("ix_past_proposals_tenant_outcome", table_name="past_proposals")
    op.drop_table("past_proposals")
