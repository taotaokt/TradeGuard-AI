"""Add portfolio monitoring runs, trade outcomes, and drift snapshots.

Revision ID: 20261021_0008
Revises: 20261021_0007
"""

from typing import Optional

from alembic import op
import sqlalchemy as sa


revision: str = "20261021_0008"
down_revision: Optional[str] = "20261021_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monitoring_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_type", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("force", sa.Boolean(), nullable=False),
        sa.Column("fuzzy_threshold", sa.Integer(), nullable=False),
        sa.Column("list_versions_json", sa.Text(), nullable=False),
        sa.Column("counters_json", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("initiated_by_id", sa.String(length=36), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["initiated_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_monitoring_runs_run_type", "monitoring_runs", ["run_type"])
    op.create_index("ix_monitoring_runs_status", "monitoring_runs", ["status"])

    op.create_table(
        "outcomes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("transaction_id", sa.String(length=36), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), nullable=True),
        sa.Column("outcome_type", sa.String(length=50), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("settled_at", sa.DateTime(), nullable=True),
        sa.Column("days_past_due", sa.Integer(), nullable=False),
        sa.Column("loss_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reported_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["transaction_id"], ["trade_transactions.id"]),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"]),
        sa.ForeignKeyConstraint(["reported_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outcomes_transaction_id", "outcomes", ["transaction_id"], unique=True)
    op.create_index("ix_outcomes_assessment_id", "outcomes", ["assessment_id"])
    op.create_index("ix_outcomes_outcome_type", "outcomes", ["outcome_type"])

    op.create_table(
        "drift_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("model_version_id", sa.String(length=36), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("window_end", sa.DateTime(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("labeled_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("metrics_json", sa.Text(), nullable=False),
        sa.Column("thresholds_json", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_drift_snapshots_model_version_id", "drift_snapshots", ["model_version_id"])
    op.create_index("ix_drift_snapshots_status", "drift_snapshots", ["status"])


def downgrade() -> None:
    op.drop_index("ix_drift_snapshots_status", table_name="drift_snapshots")
    op.drop_index("ix_drift_snapshots_model_version_id", table_name="drift_snapshots")
    op.drop_table("drift_snapshots")
    op.drop_index("ix_outcomes_outcome_type", table_name="outcomes")
    op.drop_index("ix_outcomes_assessment_id", table_name="outcomes")
    op.drop_index("ix_outcomes_transaction_id", table_name="outcomes")
    op.drop_table("outcomes")
    op.drop_index("ix_monitoring_runs_status", table_name="monitoring_runs")
    op.drop_index("ix_monitoring_runs_run_type", table_name="monitoring_runs")
    op.drop_table("monitoring_runs")
