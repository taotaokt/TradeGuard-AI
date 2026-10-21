"""Create the initial TradeGuard schema.

Revision ID: 20261020_0001
Revises: None
Create Date: 2026-10-20
"""

from typing import Optional

from alembic import op
import sqlalchemy as sa


revision: str = "20261020_0001"
down_revision: Optional[str] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=500), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "counterparties",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("legal_name", sa.String(length=300), nullable=False),
        sa.Column("jurisdiction", sa.String(length=2), nullable=False),
        sa.Column("registration_number", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("primary_address", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "jurisdiction", "registration_number", name="uq_counterparty_registration"
        ),
    )
    op.create_index("ix_counterparties_legal_name", "counterparties", ["legal_name"])
    op.create_index("ix_counterparties_jurisdiction", "counterparties", ["jurisdiction"])
    op.create_index(
        "ix_counterparties_registration_number", "counterparties", ["registration_number"]
    )

    op.create_table(
        "trade_transactions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("product_description", sa.Text(), nullable=False),
        sa.Column("hs_code", sa.String(length=30), nullable=True),
        sa.Column("origin_country", sa.String(length=2), nullable=False),
        sa.Column("destination_country", sa.String(length=2), nullable=False),
        sa.Column("transshipment_country", sa.String(length=2), nullable=True),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("payment_method", sa.String(length=50), nullable=False),
        sa.Column("payment_terms_days", sa.Integer(), nullable=False),
        sa.Column("deposit_percentage", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("incoterm", sa.String(length=10), nullable=True),
        sa.Column("end_use", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trade_transactions_reference", "trade_transactions", ["reference"], unique=True
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("object_type", sa.String(length=80), nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_object_id", "audit_events", ["object_id"])

    op.create_table(
        "counterparty_aliases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("counterparty_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("alias_type", sa.String(length=40), nullable=False),
        sa.Column("script", sa.String(length=40), nullable=True),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_counterparty_aliases_counterparty_id", "counterparty_aliases", ["counterparty_id"]
    )

    op.create_table(
        "related_parties",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("counterparty_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("relationship_type", sa.String(length=50), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("identifier", sa.String(length=150), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_related_parties_counterparty_id", "related_parties", ["counterparty_id"])

    op.create_table(
        "transaction_parties",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("transaction_id", sa.String(length=36), nullable=False),
        sa.Column("counterparty_id", sa.String(length=36), nullable=True),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("registration_number", sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(["counterparty_id"], ["counterparties.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["trade_transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transaction_parties_counterparty_id", "transaction_parties", ["counterparty_id"]
    )
    op.create_index(
        "ix_transaction_parties_transaction_id", "transaction_parties", ["transaction_id"]
    )

    op.create_table(
        "assessments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("transaction_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("current_step", sa.String(length=80), nullable=False),
        sa.Column("recommendation", sa.String(length=50), nullable=True),
        sa.Column("rule_version", sa.String(length=50), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("submitted_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["submitted_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["trade_transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transaction_id", "version", name="uq_assessment_transaction_version"),
    )
    op.create_index("ix_assessments_transaction_id", "assessments", ["transaction_id"])


def downgrade() -> None:
    op.drop_index("ix_assessments_transaction_id", table_name="assessments")
    op.drop_table("assessments")
    op.drop_index("ix_transaction_parties_transaction_id", table_name="transaction_parties")
    op.drop_index("ix_transaction_parties_counterparty_id", table_name="transaction_parties")
    op.drop_table("transaction_parties")
    op.drop_index("ix_related_parties_counterparty_id", table_name="related_parties")
    op.drop_table("related_parties")
    op.drop_index("ix_counterparty_aliases_counterparty_id", table_name="counterparty_aliases")
    op.drop_table("counterparty_aliases")
    op.drop_index("ix_audit_events_object_id", table_name="audit_events")
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_trade_transactions_reference", table_name="trade_transactions")
    op.drop_table("trade_transactions")
    op.drop_index("ix_counterparties_registration_number", table_name="counterparties")
    op.drop_index("ix_counterparties_jurisdiction", table_name="counterparties")
    op.drop_index("ix_counterparties_legal_name", table_name="counterparties")
    op.drop_table("counterparties")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
