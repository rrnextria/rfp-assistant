"""Capability profile: service_lines, industries, geographies, certifications + M2Ms.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. service_lines
    op.create_table(
        "service_lines",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("parent_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("service_lines.id"), nullable=True),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_service_lines_tenant_name"),
    )
    op.create_index("ix_service_lines_tenant", "service_lines", ["tenant_id"])

    # 2. industries
    op.create_table(
        "industries",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_industries_tenant_name"),
    )
    op.create_index("ix_industries_tenant", "industries", ["tenant_id"])

    # 3. geographies
    op.create_table(
        "geographies",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("type", sa.String, nullable=False),  # country | region | city
        sa.Column("parent_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("geographies.id"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("type IN ('country','region','city')",
                           name="ck_geographies_type"),
    )
    op.create_index("ix_geographies_tenant", "geographies", ["tenant_id"])

    # 4. certifications
    op.create_table(
        "certifications",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("issuing_body", sa.String, nullable=True),
        sa.Column("scope", sa.Text, nullable=True),
        sa.Column("expires_at", sa.Date, nullable=True),
        sa.Column("evidence_doc_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_certifications_tenant", "certifications", ["tenant_id"])

    # 5. service_line_industries (M2M)
    op.create_table(
        "service_line_industries",
        sa.Column("service_line_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("service_lines.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("industry_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("industries.id", ondelete="CASCADE"),
                  primary_key=True),
    )

    # 6. service_line_geographies (M2M)
    op.create_table(
        "service_line_geographies",
        sa.Column("service_line_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("service_lines.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("geography_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("geographies.id", ondelete="CASCADE"),
                  primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("service_line_geographies")
    op.drop_table("service_line_industries")
    op.drop_index("ix_certifications_tenant", table_name="certifications")
    op.drop_table("certifications")
    op.drop_index("ix_geographies_tenant", table_name="geographies")
    op.drop_table("geographies")
    op.drop_index("ix_industries_tenant", table_name="industries")
    op.drop_table("industries")
    op.drop_index("ix_service_lines_tenant", table_name="service_lines")
    op.drop_table("service_lines")
