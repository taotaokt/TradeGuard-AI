"""Add governed counterparty credit policies.

Revision ID: 20261022_0015
Revises: 20261022_0014
"""

from typing import Optional

from alembic import op
import sqlalchemy as sa


revision: str = "20261022_0015"
down_revision: Optional[str] = "20261022_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "counterparty_credit_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("counterparty_id", sa.String(length=36), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("risk_tier", sa.String(length=40), nullable=False),
        sa.Column("credit_limit", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("max_payment_terms_days", sa.Integer(), nullable=False),
        sa.Column(
            "minimum_deposit_percentage",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
        ),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("approved_by_id", sa.String(length=36), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "counterparty_id",
            "currency",
            "policy_version",
            name="uq_counterparty_credit_policy_version",
        ),
    )
    op.create_index(
        "ix_counterparty_credit_policies_counterparty_id",
        "counterparty_credit_policies",
        ["counterparty_id"],
    )
    op.create_index(
        "ix_counterparty_credit_policies_currency",
        "counterparty_credit_policies",
        ["currency"],
    )
    op.create_index(
        "ix_counterparty_credit_policies_status",
        "counterparty_credit_policies",
        ["status"],
    )
    op.create_index(
        "ix_counterparty_credit_policies_expires_at",
        "counterparty_credit_policies",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_counterparty_credit_policies_expires_at",
        table_name="counterparty_credit_policies",
    )
    op.drop_index(
        "ix_counterparty_credit_policies_status",
        table_name="counterparty_credit_policies",
    )
    op.drop_index(
        "ix_counterparty_credit_policies_currency",
        table_name="counterparty_credit_policies",
    )
    op.drop_index(
        "ix_counterparty_credit_policies_counterparty_id",
        table_name="counterparty_credit_policies",
    )
    op.drop_table("counterparty_credit_policies")
