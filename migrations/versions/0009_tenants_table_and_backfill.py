"""Tenants table and tenant_id backfill (Phase 0 of bid-assessment-pivot)

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-13

This migration is the foundation for multi-tenancy across the product.
It:

  1. Creates the ``tenants`` table with brand + config JSONB columns.
  2. Inserts a stable Akkodis tenant row (UUID derived via uuid5 on the slug).
  3. Adds nullable ``tenant_id UUID`` columns to the 12 directly-scoped
     existing tables (users, teams, documents, rfps, rfp_questions,
     rfp_answers, rfp_requirements, questionnaire_items, audit_logs,
     win_loss_records, products, companies).
  4. Backfills every row in those tables to the Akkodis tenant.
  5. Backfills the pre-existing free-floating ``tenant_products.tenant_id``
     column (created in migration 0005) so it points at the new tenant row.
     The FK to tenants is added in migration 0010.

Migration 0010 then locks the columns down with NOT NULL + FK constraints.
The split is intentional so a partial failure on a real deployment can be
recovered without re-running the backfill.

Indirectly-scoped tables (user_teams, chunks, product_embeddings) do NOT
get a ``tenant_id`` column — they are scoped via a parent FK (users/teams,
documents, products respectively).

``analytics_events`` does not exist in the current schema and is
intentionally excluded.
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Stable, deterministic Akkodis tenant UUID derived from the slug.
# This keeps cross-environment seeds idempotent: re-running anywhere
# produces the same UUID for the Akkodis row.
AKKODIS_TENANT_ID: uuid.UUID = uuid.uuid5(uuid.NAMESPACE_DNS, "akkodis.tenant.rfp-assistant")

# Tables that get a new directly-scoped ``tenant_id`` column.
DIRECT_TABLES: tuple[str, ...] = (
    "users",
    "teams",
    "documents",
    "rfps",
    "rfp_questions",
    "rfp_answers",
    "rfp_requirements",
    "questionnaire_items",
    "audit_logs",
    "win_loss_records",
    "products",
    "companies",
)


def upgrade() -> None:
    # 1. Create the tenants table.
    op.create_table(
        "tenants",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column(
            "brand",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # 2. Seed the Akkodis tenant row with concrete brand values.
    op.execute(
        sa.text(
            """
            INSERT INTO tenants (id, slug, display_name, brand, config)
            VALUES (
                CAST(:id AS uuid),
                :slug,
                :display_name,
                CAST(:brand AS jsonb),
                CAST(:config AS jsonb)
            )
            ON CONFLICT (slug) DO NOTHING
            """
        ).bindparams(
            id=str(AKKODIS_TENANT_ID),
            slug="akkodis",
            display_name="Akkodis",
            brand=(
                '{"primary_color": "#E2231A", '
                '"accent_color": "#FF6900", '
                '"report_header": "Akkodis Bid Assessment Report", '
                '"report_footer": "Confidential — Akkodis internal use"}'
            ),
            config="{}",
        )
    )

    # 3. Add nullable tenant_id columns to every directly-scoped existing table.
    for table in DIRECT_TABLES:
        op.add_column(
            table,
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        )

    # 4. Backfill every row in those tables to the Akkodis tenant.
    bind = op.get_bind()
    for table in DIRECT_TABLES:
        bind.execute(
            sa.text(
                f"UPDATE {table} SET tenant_id = CAST(:tid AS uuid) WHERE tenant_id IS NULL"
            ).bindparams(tid=str(AKKODIS_TENANT_ID))
        )

    # 5. Re-key the pre-existing free-floating tenant_products.tenant_id
    #    column to the Akkodis tenant. This column was created in migration
    #    0005 as NOT NULL with no FK to any real ``tenants`` row (there was
    #    no ``tenants`` table at the time), so existing values are arbitrary
    #    free-floating UUIDs. Since this migration is what introduces the
    #    single ``tenants.akkodis`` row, every existing association must be
    #    re-keyed to it before the FK in migration 0010 can be added.
    #    Update is unconditional (NOT ``WHERE tenant_id IS NULL``) because
    #    the column has been NOT NULL since 0005 — a NULL filter would be
    #    a no-op and leave invalid free-floating UUIDs that 0010 cannot FK.
    bind.execute(
        sa.text("UPDATE tenant_products SET tenant_id = CAST(:tid AS uuid)").bindparams(
            tid=str(AKKODIS_TENANT_ID)
        )
    )


def downgrade() -> None:
    # Reverse 0009 in the opposite order. 0010's downgrade must run first
    # to drop the FKs and revert NOT NULL — see migration 0010 for details.
    for table in reversed(DIRECT_TABLES):
        op.drop_column(table, "tenant_id")
    op.drop_table("tenants")
