"""Add trade receivables and payment ledger.

Revision ID: 20261026_0016
Revises: 20261022_0015
"""

from typing import Optional

from alembic import op
import sqlalchemy as sa


revision: str = "20261026_0016"
down_revision: Optional[str] = "20261022_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trade_receivables",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("transaction_id", sa.String(length=36), nullable=False),
        sa.Column("counterparty_id", sa.String(length=36), nullable=False),
        sa.Column("invoice_reference", sa.String(length=120), nullable=False),
        sa.Column("invoice_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("outstanding_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["trade_transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trade_receivables_transaction_id",
        "trade_receivables",
        ["transaction_id"],
        unique=True,
    )
    op.create_index(
        "ix_trade_receivables_counterparty_id",
        "trade_receivables",
        ["counterparty_id"],
    )
    op.create_index(
        "ix_trade_receivables_invoice_reference",
        "trade_receivables",
        ["invoice_reference"],
        unique=True,
    )
    op.create_index("ix_trade_receivables_currency", "trade_receivables", ["currency"])
    op.create_index("ix_trade_receivables_due_at", "trade_receivables", ["due_at"])
    op.create_index("ix_trade_receivables_status", "trade_receivables", ["status"])

    op.create_table(
        "receivable_payments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("receivable_id", sa.String(length=36), nullable=False),
        sa.Column("payment_reference", sa.String(length=120), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["receivable_id"], ["trade_receivables.id"]),
        sa.ForeignKeyConstraint(["recorded_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_receivable_payments_receivable_id",
        "receivable_payments",
        ["receivable_id"],
    )
    op.create_index(
        "ix_receivable_payments_payment_reference",
        "receivable_payments",
        ["payment_reference"],
        unique=True,
    )
    op.create_index(
        "ix_receivable_payments_received_at",
        "receivable_payments",
        ["received_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_receivable_payments_received_at", table_name="receivable_payments")
    op.drop_index(
        "ix_receivable_payments_payment_reference",
        table_name="receivable_payments",
    )
    op.drop_index(
        "ix_receivable_payments_receivable_id",
        table_name="receivable_payments",
    )
    op.drop_table("receivable_payments")
    op.drop_index("ix_trade_receivables_status", table_name="trade_receivables")
    op.drop_index("ix_trade_receivables_due_at", table_name="trade_receivables")
    op.drop_index("ix_trade_receivables_currency", table_name="trade_receivables")
    op.drop_index(
        "ix_trade_receivables_invoice_reference",
        table_name="trade_receivables",
    )
    op.drop_index(
        "ix_trade_receivables_counterparty_id",
        table_name="trade_receivables",
    )
    op.drop_index(
        "ix_trade_receivables_transaction_id",
        table_name="trade_receivables",
    )
    op.drop_table("trade_receivables")
