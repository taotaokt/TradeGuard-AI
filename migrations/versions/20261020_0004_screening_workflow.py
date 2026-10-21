"""Add versioned screening lists, runs, candidates, and resolutions.

Revision ID: 20261020_0004
Revises: 20261020_0003
Create Date: 2026-10-20
"""

from typing import Optional

from alembic import op
import sqlalchemy as sa


revision: str = "20261020_0004"
down_revision: Optional[str] = "20261020_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "screening_lists",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("authority", sa.String(length=200), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("active_version_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_screening_lists_code", "screening_lists", ["code"], unique=True)

    op.create_table(
        "screening_list_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("screening_list_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("effective_at", sa.DateTime(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("source_file_key", sa.String(length=150), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("imported_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["imported_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["screening_list_id"], ["screening_lists.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("screening_list_id", "version", name="uq_screening_list_version"),
        sa.UniqueConstraint("source_file_key"),
    )
    op.create_index(
        "ix_screening_list_versions_screening_list_id",
        "screening_list_versions",
        ["screening_list_id"],
    )

    op.create_table(
        "screening_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("list_version_id", sa.String(length=36), nullable=False),
        sa.Column("source_entry_id", sa.String(length=150), nullable=False),
        sa.Column("primary_name", sa.String(length=500), nullable=False),
        sa.Column("normalized_name", sa.String(length=500), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("program", sa.String(length=200), nullable=True),
        sa.Column("aliases_json", sa.Text(), nullable=False),
        sa.Column("identifiers_json", sa.Text(), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["list_version_id"], ["screening_list_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("list_version_id", "source_entry_id", name="uq_screening_source_entry"),
    )
    op.create_index(
        "ix_screening_entries_list_version_id", "screening_entries", ["list_version_id"]
    )
    op.create_index("ix_screening_entries_normalized_name", "screening_entries", ["normalized_name"])

    op.create_table(
        "screening_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("counterparty_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("fuzzy_threshold", sa.Integer(), nullable=False),
        sa.Column("screened_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"]),
        sa.ForeignKeyConstraint(["screened_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_screening_runs_counterparty_id", "screening_runs", ["counterparty_id"])

    op.create_table(
        "screening_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("screening_run_id", sa.String(length=36), nullable=False),
        sa.Column("counterparty_id", sa.String(length=36), nullable=False),
        sa.Column("related_party_id", sa.String(length=36), nullable=True),
        sa.Column("list_version_id", sa.String(length=36), nullable=False),
        sa.Column("screening_entry_id", sa.String(length=36), nullable=False),
        sa.Column("source_list_code", sa.String(length=60), nullable=False),
        sa.Column("screened_name", sa.String(length=500), nullable=False),
        sa.Column("normalized_screened_name", sa.String(length=500), nullable=False),
        sa.Column("screened_country", sa.String(length=2), nullable=True),
        sa.Column("screened_identifier", sa.String(length=150), nullable=True),
        sa.Column("matched_name", sa.String(length=500), nullable=False),
        sa.Column("match_type", sa.String(length=30), nullable=False),
        sa.Column("score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("program", sa.String(length=200), nullable=True),
        sa.Column("matched_country", sa.String(length=2), nullable=True),
        sa.Column("matched_address", sa.Text(), nullable=True),
        sa.Column("matched_identifiers_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("reviewed_by_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"]),
        sa.ForeignKeyConstraint(["list_version_id"], ["screening_list_versions.id"]),
        sa.ForeignKeyConstraint(["related_party_id"], ["related_parties.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["screening_entry_id"], ["screening_entries.id"]),
        sa.ForeignKeyConstraint(["screening_run_id"], ["screening_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_screening_candidates_screening_run_id", "screening_candidates", ["screening_run_id"]
    )
    op.create_index(
        "ix_screening_candidates_counterparty_id", "screening_candidates", ["counterparty_id"]
    )
    op.create_index(
        "ix_screening_candidates_related_party_id", "screening_candidates", ["related_party_id"]
    )
    op.create_index(
        "ix_screening_candidates_list_version_id", "screening_candidates", ["list_version_id"]
    )
    op.create_index("ix_screening_candidates_status", "screening_candidates", ["status"])


def downgrade() -> None:
    op.drop_index("ix_screening_candidates_status", table_name="screening_candidates")
    op.drop_index("ix_screening_candidates_list_version_id", table_name="screening_candidates")
    op.drop_index("ix_screening_candidates_related_party_id", table_name="screening_candidates")
    op.drop_index("ix_screening_candidates_counterparty_id", table_name="screening_candidates")
    op.drop_index("ix_screening_candidates_screening_run_id", table_name="screening_candidates")
    op.drop_table("screening_candidates")
    op.drop_index("ix_screening_runs_counterparty_id", table_name="screening_runs")
    op.drop_table("screening_runs")
    op.drop_index("ix_screening_entries_normalized_name", table_name="screening_entries")
    op.drop_index("ix_screening_entries_list_version_id", table_name="screening_entries")
    op.drop_table("screening_entries")
    op.drop_index(
        "ix_screening_list_versions_screening_list_id", table_name="screening_list_versions"
    )
    op.drop_table("screening_list_versions")
    op.drop_index("ix_screening_lists_code", table_name="screening_lists")
    op.drop_table("screening_lists")
