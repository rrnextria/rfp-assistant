"""bid_assessments + compliance_items + eligibility_checks + risks + capability_matches.

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bid_assessments",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("rfp_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("rfps.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("fit_score", sa.Numeric, nullable=True),
        sa.Column("win_probability", sa.Numeric, nullable=True),
        sa.Column("verdict", sa.String, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("model_version", sa.String, nullable=False, server_default="unknown"),
        sa.Column("generated_by", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("generated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("rfp_id", "version", name="uq_bid_assessments_rfp_version"),
        sa.CheckConstraint("status IN ('running','complete','partial','failed')",
                           name="ck_bid_assessments_status"),
        sa.CheckConstraint("verdict IS NULL OR verdict IN ('bid','no_bid','review')",
                           name="ck_bid_assessments_verdict"),
    )
    op.create_index("ix_bid_assessments_rfp", "bid_assessments", ["rfp_id"])
    op.create_index("ix_bid_assessments_tenant", "bid_assessments", ["tenant_id"])

    op.create_table(
        "compliance_items",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("bid_assessments.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("requirement_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("rfp_requirements.id"), nullable=True),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("label", sa.String, nullable=False),
        sa.Column("mandatory", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("evidence", sa.dialects.postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("citations", sa.dialects.postgresql.JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.CheckConstraint(
            "category IN ('security','privacy','operational','commercial','legal','other')",
            name="ck_compliance_category"),
        sa.CheckConstraint("status IN ('pass','fail','partial','unknown')",
                           name="ck_compliance_status"),
    )
    op.create_index("ix_compliance_items_assessment", "compliance_items", ["assessment_id"])

    op.create_table(
        "eligibility_checks",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("bid_assessments.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("label", sa.String, nullable=False),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("expected", sa.String, nullable=True),
        sa.Column("actual", sa.String, nullable=True),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("citations", sa.dialects.postgresql.JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.CheckConstraint(
            "kind IN ('geography','contract_vehicle','certification','financial','exclusion','other')",
            name="ck_eligibility_kind"),
        sa.CheckConstraint("status IN ('pass','fail','partial','unknown')",
                           name="ck_eligibility_status"),
    )
    op.create_index("ix_eligibility_checks_assessment", "eligibility_checks", ["assessment_id"])

    op.create_table(
        "risks",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("bid_assessments.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("severity", sa.String, nullable=False),
        sa.Column("likelihood", sa.String, nullable=False),
        sa.Column("mitigation", sa.Text, nullable=True),
        sa.Column("citations", sa.dialects.postgresql.JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("authored_by", sa.String, nullable=False, server_default="ai"),
        sa.CheckConstraint(
            "category IN ('commercial','delivery','legal','technical','reputational')",
            name="ck_risks_category"),
        sa.CheckConstraint("severity IN ('low','medium','high')", name="ck_risks_severity"),
        sa.CheckConstraint("likelihood IN ('low','medium','high')", name="ck_risks_likelihood"),
        sa.CheckConstraint("authored_by IN ('ai','human')", name="ck_risks_authored_by"),
    )
    op.create_index("ix_risks_assessment", "risks", ["assessment_id"])

    op.create_table(
        "capability_matches",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("assessment_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("bid_assessments.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("requirement_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("rfp_requirements.id"), nullable=False),
        sa.Column("offering_type", sa.String, nullable=False),
        sa.Column("offering_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("match_score", sa.Numeric, nullable=False),
        sa.Column("gap_notes", sa.Text, nullable=True),
        sa.CheckConstraint("offering_type IN ('service_line','product')",
                           name="ck_capability_matches_offering_type"),
    )
    op.create_index("ix_capability_matches_assessment", "capability_matches", ["assessment_id"])


def downgrade() -> None:
    op.drop_index("ix_capability_matches_assessment", table_name="capability_matches")
    op.drop_table("capability_matches")
    op.drop_index("ix_risks_assessment", table_name="risks")
    op.drop_table("risks")
    op.drop_index("ix_eligibility_checks_assessment", table_name="eligibility_checks")
    op.drop_table("eligibility_checks")
    op.drop_index("ix_compliance_items_assessment", table_name="compliance_items")
    op.drop_table("compliance_items")
    op.drop_index("ix_bid_assessments_tenant", table_name="bid_assessments")
    op.drop_index("ix_bid_assessments_rfp", table_name="bid_assessments")
    op.drop_table("bid_assessments")
