"""Add counterparty fact provenance.

Revision ID: 20261022_0014
Revises: 20261022_0013
"""

from typing import Optional

from alembic import op
import sqlalchemy as sa


revision: str = "20261022_0014"
down_revision: Optional[str] = "20261022_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "counterparty_facts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("fact_key", sa.String(length=64), nullable=False),
        sa.Column("counterparty_id", sa.String(length=36), nullable=False),
        sa.Column("fact_type", sa.String(length=60), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.String(length=500), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("source_document_id", sa.String(length=36), nullable=True),
        sa.Column("verification_status", sa.String(length=40), nullable=False),
        sa.Column("verification_rationale", sa.Text(), nullable=True),
        sa.Column("verified_by_id", sa.String(length=36), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["supporting_documents.id"]),
        sa.ForeignKeyConstraint(["verified_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_counterparty_facts_fact_key", "counterparty_facts", ["fact_key"], unique=True
    )
    op.create_index(
        "ix_counterparty_facts_counterparty_id", "counterparty_facts", ["counterparty_id"]
    )
    op.create_index("ix_counterparty_facts_fact_type", "counterparty_facts", ["fact_type"])
    op.create_index(
        "ix_counterparty_facts_normalized_value",
        "counterparty_facts",
        ["normalized_value"],
    )
    op.create_index(
        "ix_counterparty_facts_source_document_id",
        "counterparty_facts",
        ["source_document_id"],
    )
    op.create_index(
        "ix_counterparty_facts_verification_status",
        "counterparty_facts",
        ["verification_status"],
    )
    op.create_index("ix_counterparty_facts_expires_at", "counterparty_facts", ["expires_at"])
    op.create_index("ix_counterparty_facts_status", "counterparty_facts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_counterparty_facts_status", table_name="counterparty_facts")
    op.drop_index("ix_counterparty_facts_expires_at", table_name="counterparty_facts")
    op.drop_index(
        "ix_counterparty_facts_verification_status", table_name="counterparty_facts"
    )
    op.drop_index("ix_counterparty_facts_source_document_id", table_name="counterparty_facts")
    op.drop_index("ix_counterparty_facts_normalized_value", table_name="counterparty_facts")
    op.drop_index("ix_counterparty_facts_fact_type", table_name="counterparty_facts")
    op.drop_index("ix_counterparty_facts_counterparty_id", table_name="counterparty_facts")
    op.drop_index("ix_counterparty_facts_fact_key", table_name="counterparty_facts")
    op.drop_table("counterparty_facts")
