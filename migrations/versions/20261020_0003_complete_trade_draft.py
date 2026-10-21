"""Add complete trade-draft fields and optimistic versioning.

Revision ID: 20261020_0003
Revises: 20261020_0002
Create Date: 2026-10-20
"""

from typing import Optional

from alembic import op
import sqlalchemy as sa


revision: str = "20261020_0003"
down_revision: Optional[str] = "20261020_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trade_transactions",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "trade_transactions", sa.Column("quantity", sa.Numeric(precision=18, scale=4), nullable=True)
    )
    op.add_column("trade_transactions", sa.Column("quantity_unit", sa.String(length=30), nullable=True))
    op.add_column(
        "trade_transactions",
        sa.Column("bank_beneficiary_name", sa.String(length=300), nullable=True),
    )
    op.add_column(
        "trade_transactions",
        sa.Column("bank_beneficiary_country", sa.String(length=2), nullable=True),
    )
    op.add_column(
        "trade_transactions",
        sa.Column("requested_credit_exposure", sa.Numeric(precision=18, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trade_transactions", "requested_credit_exposure")
    op.drop_column("trade_transactions", "bank_beneficiary_country")
    op.drop_column("trade_transactions", "bank_beneficiary_name")
    op.drop_column("trade_transactions", "quantity_unit")
    op.drop_column("trade_transactions", "quantity")
    op.drop_column("trade_transactions", "version")
