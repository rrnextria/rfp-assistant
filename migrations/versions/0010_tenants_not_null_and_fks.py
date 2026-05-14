"""Lock down tenant_id with NOT NULL, FK, and indexes (Phase 0 of bid-assessment-pivot)

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-13

Second half of the Phase 0 foundation migration set. Migration 0009 created
the ``tenants`` table, added nullable ``tenant_id`` columns to 12 directly-
scoped tables, and backfilled every row (including the pre-existing
``tenant_products.tenant_id`` column) to the seeded Akkodis tenant.

This migration:

  1. Re-verifies that the 0009 backfill left no NULL ``tenant_id`` values
     anywhere — explicitly raises if any are found, so a partial 0009 can't
     be silently locked down with bad data.
  2. Promotes every ``tenant_id`` column added in 0009 to NOT NULL.
     ``tenant_products.tenant_id`` was already NOT NULL since 0005.
  3. Adds FK constraints from every ``tenant_id`` column (including the
     pre-existing ``tenant_products.tenant_id``) to ``tenants.id``.
  4. Creates ``(tenant_id)`` indexes on hot list-heavy tables: ``documents``,
     ``rfps``, ``audit_logs``. ``chunks`` is intentionally excluded — it has
     no ``tenant_id`` column and inherits scoping via ``document_id``.

``downgrade()`` reverses only 0010's own changes: drops the FKs and the
``(tenant_id)`` indexes it added, and reverts the NOT NULL constraints back
to NULLable. The ``tenants`` table itself and the ``tenant_id`` columns are
dropped by 0009's downgrade.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables that gained a ``tenant_id`` column in migration 0009.
NEW_COLUMN_TABLES: tuple[str, ...] = (
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

# All tables whose ``tenant_id`` should FK to ``tenants.id`` after this
# migration. Includes the pre-existing ``tenant_products`` column.
ALL_FK_TABLES: tuple[str, ...] = NEW_COLUMN_TABLES + ("tenant_products",)

# Hot list-heavy tables that benefit from a ``(tenant_id)`` btree index.
INDEXED_TABLES: tuple[str, ...] = ("documents", "rfps", "audit_logs")


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Re-verify no NULL ``tenant_id`` rows survive in any of the 13
    #    affected tables. If 0009's backfill missed a row, fail loudly here
    #    rather than producing a half-locked schema with bad data.
    for table in ALL_FK_TABLES:
        null_count = bind.execute(
            sa.text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL")
        ).scalar_one()
        if null_count:
            raise RuntimeError(
                f"Migration 0010 aborted: {table} has {null_count} row(s) with NULL tenant_id. "
                "Re-run migration 0009 backfill before locking columns down."
            )

    # 2. Promote new tenant_id columns to NOT NULL. tenant_products is
    #    already NOT NULL from migration 0005 — skip it.
    for table in NEW_COLUMN_TABLES:
        op.alter_column(table, "tenant_id", nullable=False)

    # 3. Add FK constraints to tenants.id for every directly-scoped table.
    for table in ALL_FK_TABLES:
        op.create_foreign_key(
            f"fk_{table}_tenant_id_tenants",
            source_table=table,
            referent_table="tenants",
            local_cols=["tenant_id"],
            remote_cols=["id"],
        )

    # 4. Create btree indexes on (tenant_id) for hot list-heavy tables.
    for table in INDEXED_TABLES:
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])


def downgrade() -> None:
    # Reverse only this migration's changes. tenants table + tenant_id
    # columns are dropped by 0009's downgrade.
    for table in INDEXED_TABLES:
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)

    for table in ALL_FK_TABLES:
        op.drop_constraint(f"fk_{table}_tenant_id_tenants", table, type_="foreignkey")

    for table in NEW_COLUMN_TABLES:
        op.alter_column(table, "tenant_id", nullable=True)
