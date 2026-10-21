"""Add rule results, assessment steps, decisions, and review cases.

Revision ID: 20261020_0005
Revises: 20261020_0004
Create Date: 2026-10-20
"""

from typing import Optional

from alembic import op
import sqlalchemy as sa


revision: str = "20261020_0005"
down_revision: Optional[str] = "20261020_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assessments", sa.Column("rule_checksum_sha256", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "assessments",
        sa.Column("input_snapshot_json", sa.Text(), server_default="{}", nullable=False),
    )
    op.add_column(
        "assessments",
        sa.Column("screening_snapshot_json", sa.Text(), server_default="{}", nullable=False),
    )
    op.add_column("assessments", sa.Column("completed_at", sa.DateTime(), nullable=True))

    op.create_table(
        "rule_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checksum_sha256"),
    )
    op.create_index("ix_rule_versions_version", "rule_versions", ["version"], unique=True)

    op.create_table(
        "assessment_steps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("input_reference_json", sa.Text(), nullable=False),
        sa.Column("output_json", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_id", "name", name="uq_assessment_step_name"),
    )
    op.create_index("ix_assessment_steps_assessment_id", "assessment_steps", ["assessment_id"])

    op.create_table(
        "rule_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), nullable=False),
        sa.Column("rule_version", sa.String(length=50), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=30), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("inputs_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rule_results_assessment_id", "rule_results", ["assessment_id"])
    op.create_index("ix_rule_results_reason_code", "rule_results", ["reason_code"])

    op.create_table(
        "decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), nullable=False),
        sa.Column("automatic_recommendation", sa.String(length=50), nullable=False),
        sa.Column("final_recommendation", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("hard_stop", sa.Boolean(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("reason_codes_json", sa.Text(), nullable=False),
        sa.Column("risk_dimensions_json", sa.Text(), nullable=False),
        sa.Column("conditions_json", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("reviewed_by_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("is_override", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decisions_assessment_id", "decisions", ["assessment_id"], unique=True)

    op.create_table(
        "review_cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("required_role", sa.String(length=50), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("reviewer_id", sa.String(length=36), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"]),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_cases_assessment_id", "review_cases", ["assessment_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_review_cases_assessment_id", table_name="review_cases")
    op.drop_table("review_cases")
    op.drop_index("ix_decisions_assessment_id", table_name="decisions")
    op.drop_table("decisions")
    op.drop_index("ix_rule_results_reason_code", table_name="rule_results")
    op.drop_index("ix_rule_results_assessment_id", table_name="rule_results")
    op.drop_table("rule_results")
    op.drop_index("ix_assessment_steps_assessment_id", table_name="assessment_steps")
    op.drop_table("assessment_steps")
    op.drop_index("ix_rule_versions_version", table_name="rule_versions")
    op.drop_table("rule_versions")
    op.drop_column("assessments", "completed_at")
    op.drop_column("assessments", "screening_snapshot_json")
    op.drop_column("assessments", "input_snapshot_json")
    op.drop_column("assessments", "rule_checksum_sha256")
