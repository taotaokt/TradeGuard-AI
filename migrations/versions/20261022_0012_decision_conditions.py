"""Add tracked decision conditions.

Revision ID: 20261022_0012
Revises: 20261022_0011
"""

from typing import Optional

from alembic import op
import sqlalchemy as sa


revision: str = "20261022_0012"
down_revision: Optional[str] = "20261022_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decision_conditions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("decision_id", sa.String(length=36), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_role", sa.String(length=50), nullable=False),
        sa.Column("assigned_to_id", sa.String(length=36), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("evidence_document_id", sa.String(length=36), nullable=True),
        sa.Column("completion_rationale", sa.Text(), nullable=True),
        sa.Column("completed_by_id", sa.String(length=36), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.id"]),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"]),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["evidence_document_id"], ["supporting_documents.id"]),
        sa.ForeignKeyConstraint(["completed_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_id", "sequence", name="uq_decision_condition_sequence"),
    )
    op.create_index("ix_decision_conditions_decision_id", "decision_conditions", ["decision_id"])
    op.create_index(
        "ix_decision_conditions_assessment_id", "decision_conditions", ["assessment_id"]
    )
    op.create_index("ix_decision_conditions_owner_role", "decision_conditions", ["owner_role"])
    op.create_index(
        "ix_decision_conditions_assigned_to_id", "decision_conditions", ["assigned_to_id"]
    )
    op.create_index("ix_decision_conditions_due_at", "decision_conditions", ["due_at"])
    op.create_index("ix_decision_conditions_status", "decision_conditions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_decision_conditions_status", table_name="decision_conditions")
    op.drop_index("ix_decision_conditions_due_at", table_name="decision_conditions")
    op.drop_index("ix_decision_conditions_assigned_to_id", table_name="decision_conditions")
    op.drop_index("ix_decision_conditions_owner_role", table_name="decision_conditions")
    op.drop_index("ix_decision_conditions_assessment_id", table_name="decision_conditions")
    op.drop_index("ix_decision_conditions_decision_id", table_name="decision_conditions")
    op.drop_table("decision_conditions")
