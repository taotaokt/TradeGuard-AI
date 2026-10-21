"""Add versioned model metadata and assessment predictions.

Revision ID: 20261021_0006
Revises: 20261020_0005
"""

from typing import Optional

from alembic import op
import sqlalchemy as sa


revision: str = "20261021_0006"
down_revision: Optional[str] = "20261020_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("model_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("target_definition", sa.Text(), nullable=False),
        sa.Column("feature_schema_json", sa.Text(), nullable=False),
        sa.Column("metrics_json", sa.Text(), nullable=False),
        sa.Column("artifact_path", sa.String(length=500), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("training_data_sha256", sa.String(length=64), nullable=False),
        sa.Column("runtime_json", sa.Text(), nullable=False),
        sa.Column("trained_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_versions_version", "model_versions", ["version"], unique=True)
    op.create_table(
        "predictions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), nullable=False),
        sa.Column("model_version_id", sa.String(length=36), nullable=False),
        sa.Column("probability", sa.Numeric(8, 6), nullable=False),
        sa.Column("calibrated", sa.Boolean(), nullable=False),
        sa.Column("risk_band", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.String(length=30), nullable=False),
        sa.Column("uncertainty_reason", sa.Text(), nullable=True),
        sa.Column("reason_codes_json", sa.Text(), nullable=False),
        sa.Column("features_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"]),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_predictions_assessment_id", "predictions", ["assessment_id"], unique=True)
    op.create_index("ix_predictions_model_version_id", "predictions", ["model_version_id"])


def downgrade() -> None:
    op.drop_index("ix_predictions_model_version_id", table_name="predictions")
    op.drop_index("ix_predictions_assessment_id", table_name="predictions")
    op.drop_table("predictions")
    op.drop_index("ix_model_versions_version", table_name="model_versions")
    op.drop_table("model_versions")
