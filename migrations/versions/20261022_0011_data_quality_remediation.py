"""Add data-quality scans and remediation issues.

Revision ID: 20261022_0011
Revises: 20261021_0010
"""

from typing import Optional

from alembic import op
import sqlalchemy as sa


revision: str = "20261022_0011"
down_revision: Optional[str] = "20261021_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_quality_scans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("ruleset_version", sa.String(length=50), nullable=False),
        sa.Column("parameters_json", sa.Text(), nullable=False),
        sa.Column("counters_json", sa.Text(), nullable=False),
        sa.Column("initiated_by_id", sa.String(length=36), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["initiated_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_quality_scans_status", "data_quality_scans", ["status"])

    op.create_table(
        "data_quality_issues",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("issue_key", sa.String(length=220), nullable=False),
        sa.Column("detected_by_scan_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=30), nullable=False),
        sa.Column("required_role", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("assigned_to_id", sa.String(length=36), nullable=True),
        sa.Column("resolution_rationale", sa.Text(), nullable=True),
        sa.Column("resolved_by_id", sa.String(length=36), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["detected_by_scan_id"], ["data_quality_scans.id"]),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["resolved_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_data_quality_issues_issue_key", "data_quality_issues", ["issue_key"], unique=True
    )
    op.create_index(
        "ix_data_quality_issues_detected_by_scan_id",
        "data_quality_issues",
        ["detected_by_scan_id"],
    )
    op.create_index("ix_data_quality_issues_entity_type", "data_quality_issues", ["entity_type"])
    op.create_index("ix_data_quality_issues_entity_id", "data_quality_issues", ["entity_id"])
    op.create_index("ix_data_quality_issues_code", "data_quality_issues", ["code"])
    op.create_index("ix_data_quality_issues_severity", "data_quality_issues", ["severity"])
    op.create_index("ix_data_quality_issues_status", "data_quality_issues", ["status"])
    op.create_index(
        "ix_data_quality_issues_assigned_to_id", "data_quality_issues", ["assigned_to_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_data_quality_issues_assigned_to_id", table_name="data_quality_issues")
    op.drop_index("ix_data_quality_issues_status", table_name="data_quality_issues")
    op.drop_index("ix_data_quality_issues_severity", table_name="data_quality_issues")
    op.drop_index("ix_data_quality_issues_code", table_name="data_quality_issues")
    op.drop_index("ix_data_quality_issues_entity_id", table_name="data_quality_issues")
    op.drop_index("ix_data_quality_issues_entity_type", table_name="data_quality_issues")
    op.drop_index(
        "ix_data_quality_issues_detected_by_scan_id", table_name="data_quality_issues"
    )
    op.drop_index("ix_data_quality_issues_issue_key", table_name="data_quality_issues")
    op.drop_table("data_quality_issues")
    op.drop_index("ix_data_quality_scans_status", table_name="data_quality_scans")
    op.drop_table("data_quality_scans")
