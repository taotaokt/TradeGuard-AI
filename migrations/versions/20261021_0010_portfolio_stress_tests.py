"""Add reproducible portfolio stress tests.

Revision ID: 20261021_0010
Revises: 20261021_0009
"""

from typing import Optional

from alembic import op
import sqlalchemy as sa


revision: str = "20261021_0010"
down_revision: Optional[str] = "20261021_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_stress_tests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("parameters_json", sa.Text(), nullable=False),
        sa.Column("portfolio_snapshot_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_portfolio_stress_tests_status", "portfolio_stress_tests", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_portfolio_stress_tests_status", table_name="portfolio_stress_tests")
    op.drop_table("portfolio_stress_tests")
