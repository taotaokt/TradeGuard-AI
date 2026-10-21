"""Add monitoring alerts and reassessment links.

Revision ID: 20261021_0007
Revises: 20261021_0006
"""

from typing import Optional

from alembic import op
import sqlalchemy as sa


revision: str = "20261021_0007"
down_revision: Optional[str] = "20261021_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("alert_type", sa.String(length=60), nullable=False),
        sa.Column("severity", sa.String(length=30), nullable=False),
        sa.Column("required_role", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("counterparty_id", sa.String(length=36), nullable=True),
        sa.Column("transaction_id", sa.String(length=36), nullable=True),
        sa.Column("screening_run_id", sa.String(length=36), nullable=True),
        sa.Column("reassessment_id", sa.String(length=36), nullable=True),
        sa.Column("source_reference_json", sa.Text(), nullable=False),
        sa.Column("assigned_to_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=True),
        sa.Column("acknowledged_by_id", sa.String(length=36), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by_id", sa.String(length=36), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolution_rationale", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["trade_transactions.id"]),
        sa.ForeignKeyConstraint(["screening_run_id"], ["screening_runs.id"]),
        sa.ForeignKeyConstraint(["reassessment_id"], ["assessments.id"]),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["acknowledged_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["resolved_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_alert_type", "alerts", ["alert_type"])
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index("ix_alerts_status", "alerts", ["status"])
    op.create_index("ix_alerts_counterparty_id", "alerts", ["counterparty_id"])
    op.create_index("ix_alerts_transaction_id", "alerts", ["transaction_id"])
    op.create_index("ix_alerts_screening_run_id", "alerts", ["screening_run_id"])
    op.create_index("ix_alerts_reassessment_id", "alerts", ["reassessment_id"])
    op.create_index("ix_alerts_assigned_to_id", "alerts", ["assigned_to_id"])


def downgrade() -> None:
    op.drop_index("ix_alerts_assigned_to_id", table_name="alerts")
    op.drop_index("ix_alerts_reassessment_id", table_name="alerts")
    op.drop_index("ix_alerts_screening_run_id", table_name="alerts")
    op.drop_index("ix_alerts_transaction_id", table_name="alerts")
    op.drop_index("ix_alerts_counterparty_id", table_name="alerts")
    op.drop_index("ix_alerts_status", table_name="alerts")
    op.drop_index("ix_alerts_severity", table_name="alerts")
    op.drop_index("ix_alerts_alert_type", table_name="alerts")
    op.drop_table("alerts")
