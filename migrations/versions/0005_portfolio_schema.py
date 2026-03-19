"""Portfolio and learning schema tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-18

"""
from __future__ import annotations
from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # products
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("vendor", sa.String(255), nullable=True),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # tenant_products
    op.create_table(
        "tenant_products",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "product_id"),
    )

    # product_embeddings — VECTOR(384)
    op.create_table(
        "product_embeddings",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    )
    op.execute("ALTER TABLE product_embeddings ADD COLUMN embedding vector(384)")

    # rfp_requirements
    op.create_table(
        "rfp_requirements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("rfp_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rfps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("scoring_criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("is_questionnaire", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # questionnaire_items
    op.create_table(
        "questionnaire_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("rfp_requirement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rfp_requirements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_type", sa.String(50), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("flagged", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # win_loss_records
    op.create_table(
        "win_loss_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("rfp_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rfps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("outcome", sa.String(50), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("lessons_learned", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # Extend rfps with raw_text
    op.add_column("rfps", sa.Column("raw_text", sa.Text(), nullable=True))

    # Extend rfp_answers with confidence and detail_level
    op.add_column("rfp_answers", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("rfp_answers", sa.Column("detail_level", sa.String(20), nullable=True, server_default="balanced"))
    op.add_column("rfp_answers", sa.Column("partial_compliance", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("rfp_answers", "partial_compliance")
    op.drop_column("rfp_answers", "detail_level")
    op.drop_column("rfp_answers", "confidence")
    op.drop_column("rfps", "raw_text")
    op.drop_table("win_loss_records")
    op.drop_table("questionnaire_items")
    op.drop_table("rfp_requirements")
    op.drop_table("product_embeddings")
    op.drop_table("tenant_products")
    op.drop_table("products")
