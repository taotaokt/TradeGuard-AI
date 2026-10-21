"""Add scheduled jobs, execution history, and notification outbox.

Revision ID: 20261021_0009
Revises: 20261021_0008
"""

from typing import Optional

from alembic import op
import sqlalchemy as sa


revision: str = "20261021_0009"
down_revision: Optional[str] = "20261021_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_key", sa.String(length=60), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("parameters_json", sa.Text(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(), nullable=False),
        sa.Column("last_started_at", sa.DateTime(), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(), nullable=True),
        sa.Column("last_status", sa.String(length=40), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduled_jobs_job_key", "scheduled_jobs", ["job_key"], unique=True)
    op.create_index("ix_scheduled_jobs_next_run_at", "scheduled_jobs", ["next_run_at"])
    op.create_index("ix_scheduled_jobs_last_status", "scheduled_jobs", ["last_status"])

    op.create_table(
        "scheduled_job_executions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scheduled_job_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("triggered_by_id", sa.String(length=36), nullable=False),
        sa.Column("result_reference_json", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["scheduled_job_id"], ["scheduled_jobs.id"]),
        sa.ForeignKeyConstraint(["triggered_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scheduled_job_executions_scheduled_job_id",
        "scheduled_job_executions",
        ["scheduled_job_id"],
    )
    op.create_index(
        "ix_scheduled_job_executions_status", "scheduled_job_executions", ["status"]
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("alert_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("recipient_role", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("claimed_by", sa.String(length=120), nullable=True),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_notification_deliveries_alert_id", "notification_deliveries", ["alert_id"]
    )
    op.create_index(
        "ix_notification_deliveries_recipient_role",
        "notification_deliveries",
        ["recipient_role"],
    )
    op.create_index(
        "ix_notification_deliveries_status", "notification_deliveries", ["status"]
    )
    op.create_index(
        "ix_notification_deliveries_available_at",
        "notification_deliveries",
        ["available_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_deliveries_available_at", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_status", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_recipient_role", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_alert_id", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    op.drop_index("ix_scheduled_job_executions_status", table_name="scheduled_job_executions")
    op.drop_index(
        "ix_scheduled_job_executions_scheduled_job_id",
        table_name="scheduled_job_executions",
    )
    op.drop_table("scheduled_job_executions")
    op.drop_index("ix_scheduled_jobs_last_status", table_name="scheduled_jobs")
    op.drop_index("ix_scheduled_jobs_next_run_at", table_name="scheduled_jobs")
    op.drop_index("ix_scheduled_jobs_job_key", table_name="scheduled_jobs")
    op.drop_table("scheduled_jobs")
