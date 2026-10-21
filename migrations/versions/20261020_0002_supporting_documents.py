"""Add supporting documents for counterparties and transactions.

Revision ID: 20261020_0002
Revises: 20261020_0001
Create Date: 2026-10-20
"""

from typing import Optional

from alembic import op
import sqlalchemy as sa


revision: str = "20261020_0002"
down_revision: Optional[str] = "20261020_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supporting_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("counterparty_id", sa.String(length=36), nullable=True),
        sa.Column("transaction_id", sa.String(length=36), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=100), nullable=False),
        sa.Column("document_type", sa.String(length=60), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("verification_status", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("uploaded_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "(counterparty_id IS NOT NULL AND transaction_id IS NULL) OR "
            "(counterparty_id IS NULL AND transaction_id IS NOT NULL)",
            name="ck_document_single_parent",
        ),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["trade_transactions.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        "ix_supporting_documents_counterparty_id",
        "supporting_documents",
        ["counterparty_id"],
    )
    op.create_index(
        "ix_supporting_documents_transaction_id",
        "supporting_documents",
        ["transaction_id"],
    )
    op.create_index(
        "ix_supporting_documents_document_type",
        "supporting_documents",
        ["document_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_supporting_documents_document_type", table_name="supporting_documents")
    op.drop_index("ix_supporting_documents_transaction_id", table_name="supporting_documents")
    op.drop_index("ix_supporting_documents_counterparty_id", table_name="supporting_documents")
    op.drop_table("supporting_documents")
