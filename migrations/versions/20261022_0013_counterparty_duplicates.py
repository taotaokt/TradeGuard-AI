"""Add counterparty duplicate review.

Revision ID: 20261022_0013
Revises: 20261022_0012
"""

from typing import Optional

from alembic import op
import sqlalchemy as sa


revision: str = "20261022_0013"
down_revision: Optional[str] = "20261022_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("counterparties") as batch_op:
        batch_op.add_column(
            sa.Column(
                "duplicate_status",
                sa.String(length=40),
                server_default="clear",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("canonical_counterparty_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_counterparties_canonical_counterparty_id",
            "counterparties",
            ["canonical_counterparty_id"],
            ["id"],
        )
        batch_op.create_index("ix_counterparties_duplicate_status", ["duplicate_status"])
        batch_op.create_index(
            "ix_counterparties_canonical_counterparty_id", ["canonical_counterparty_id"]
        )
    op.create_table(
        "counterparty_duplicate_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pair_key", sa.String(length=80), nullable=False),
        sa.Column("existing_counterparty_id", sa.String(length=36), nullable=False),
        sa.Column("possible_duplicate_id", sa.String(length=36), nullable=False),
        sa.Column("name_similarity", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("matched_name", sa.String(length=300), nullable=False),
        sa.Column("signals_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("reviewed_by_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["existing_counterparty_id"], ["counterparties.id"]),
        sa.ForeignKeyConstraint(["possible_duplicate_id"], ["counterparties.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_counterparty_duplicate_candidates_pair_key",
        "counterparty_duplicate_candidates",
        ["pair_key"],
        unique=True,
    )
    op.create_index(
        "ix_counterparty_duplicate_candidates_existing_counterparty_id",
        "counterparty_duplicate_candidates",
        ["existing_counterparty_id"],
    )
    op.create_index(
        "ix_counterparty_duplicate_candidates_possible_duplicate_id",
        "counterparty_duplicate_candidates",
        ["possible_duplicate_id"],
    )
    op.create_index(
        "ix_counterparty_duplicate_candidates_status",
        "counterparty_duplicate_candidates",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_counterparty_duplicate_candidates_status",
        table_name="counterparty_duplicate_candidates",
    )
    op.drop_index(
        "ix_counterparty_duplicate_candidates_possible_duplicate_id",
        table_name="counterparty_duplicate_candidates",
    )
    op.drop_index(
        "ix_counterparty_duplicate_candidates_existing_counterparty_id",
        table_name="counterparty_duplicate_candidates",
    )
    op.drop_index(
        "ix_counterparty_duplicate_candidates_pair_key",
        table_name="counterparty_duplicate_candidates",
    )
    op.drop_table("counterparty_duplicate_candidates")
    with op.batch_alter_table("counterparties") as batch_op:
        batch_op.drop_index("ix_counterparties_canonical_counterparty_id")
        batch_op.drop_index("ix_counterparties_duplicate_status")
        batch_op.drop_constraint(
            "fk_counterparties_canonical_counterparty_id", type_="foreignkey"
        )
        batch_op.drop_column("canonical_counterparty_id")
        batch_op.drop_column("duplicate_status")
