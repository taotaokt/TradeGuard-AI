import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base


def new_id() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    role: Mapped[str] = mapped_column(String(40), default="business_user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Counterparty(TimestampMixin, Base):
    __tablename__ = "counterparties"
    __table_args__ = (
        UniqueConstraint("jurisdiction", "registration_number", name="uq_counterparty_registration"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    legal_name: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(2), index=True, nullable=False)
    registration_number: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    website: Mapped[Optional[str]] = mapped_column(String(500))
    primary_address: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    aliases: Mapped[List["CounterpartyAlias"]] = relationship(
        cascade="all, delete-orphan", back_populates="counterparty"
    )
    related_parties: Mapped[List["RelatedParty"]] = relationship(
        cascade="all, delete-orphan", back_populates="counterparty"
    )


class CounterpartyAlias(Base):
    __tablename__ = "counterparty_aliases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    counterparty_id: Mapped[str] = mapped_column(ForeignKey("counterparties.id"), index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    alias_type: Mapped[str] = mapped_column(String(40), default="trading_name", nullable=False)
    script: Mapped[Optional[str]] = mapped_column(String(40))

    counterparty: Mapped[Counterparty] = relationship(back_populates="aliases")


class RelatedParty(TimestampMixin, Base):
    __tablename__ = "related_parties"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    counterparty_id: Mapped[str] = mapped_column(ForeignKey("counterparties.id"), index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False)
    country: Mapped[Optional[str]] = mapped_column(String(2))
    identifier: Mapped[Optional[str]] = mapped_column(String(150))

    counterparty: Mapped[Counterparty] = relationship(back_populates="related_parties")


class TradeTransaction(TimestampMixin, Base):
    __tablename__ = "trade_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    reference: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    product_description: Mapped[str] = mapped_column(Text, nullable=False)
    hs_code: Mapped[Optional[str]] = mapped_column(String(30))
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    quantity_unit: Mapped[Optional[str]] = mapped_column(String(30))
    origin_country: Mapped[str] = mapped_column(String(2), nullable=False)
    destination_country: Mapped[str] = mapped_column(String(2), nullable=False)
    transshipment_country: Mapped[Optional[str]] = mapped_column(String(2))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deposit_percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=lambda: Decimal("0.00"), nullable=False
    )
    incoterm: Mapped[Optional[str]] = mapped_column(String(10))
    bank_beneficiary_name: Mapped[Optional[str]] = mapped_column(String(300))
    bank_beneficiary_country: Mapped[Optional[str]] = mapped_column(String(2))
    requested_credit_exposure: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    end_use: Mapped[Optional[str]] = mapped_column(Text)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    parties: Mapped[List["TransactionParty"]] = relationship(
        cascade="all, delete-orphan", back_populates="transaction"
    )
    assessments: Mapped[List["Assessment"]] = relationship(
        cascade="all, delete-orphan", back_populates="transaction"
    )


class TransactionParty(Base):
    __tablename__ = "transaction_parties"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("trade_transactions.id"), index=True)
    counterparty_id: Mapped[Optional[str]] = mapped_column(ForeignKey("counterparties.id"), index=True)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    country: Mapped[Optional[str]] = mapped_column(String(2))
    registration_number: Mapped[Optional[str]] = mapped_column(String(120))

    transaction: Mapped[TradeTransaction] = relationship(back_populates="parties")


class Assessment(TimestampMixin, Base):
    __tablename__ = "assessments"
    __table_args__ = (
        UniqueConstraint("transaction_id", "version", name="uq_assessment_transaction_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("trade_transactions.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="created", nullable=False)
    current_step: Mapped[str] = mapped_column(String(80), default="validation", nullable=False)
    recommendation: Mapped[Optional[str]] = mapped_column(String(50))
    rule_version: Mapped[str] = mapped_column(String(50), default="v1", nullable=False)
    model_version: Mapped[Optional[str]] = mapped_column(String(100))
    submitted_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    rule_checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64))
    input_snapshot_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    screening_snapshot_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    transaction: Mapped[TradeTransaction] = relationship(back_populates="assessments")
    steps: Mapped[List["AssessmentStep"]] = relationship(
        cascade="all, delete-orphan", back_populates="assessment", order_by="AssessmentStep.sequence"
    )
    rule_results: Mapped[List["RuleResult"]] = relationship(
        cascade="all, delete-orphan", back_populates="assessment"
    )
    decision: Mapped[Optional["Decision"]] = relationship(
        cascade="all, delete-orphan", back_populates="assessment", uselist=False
    )
    review_case: Mapped[Optional["ReviewCase"]] = relationship(
        cascade="all, delete-orphan", back_populates="assessment", uselist=False
    )
    prediction: Mapped[Optional["Prediction"]] = relationship(
        cascade="all, delete-orphan", back_populates="assessment", uselist=False
    )


class RuleVersion(TimestampMixin, Base):
    __tablename__ = "rule_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class ModelVersion(TimestampMixin, Base):
    __tablename__ = "model_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    target_definition: Mapped[str] = mapped_column(Text, nullable=False)
    feature_schema_json: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(500), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    training_data_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    runtime_json: Mapped[str] = mapped_column(Text, nullable=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id"), unique=True, index=True, nullable=False
    )
    model_version_id: Mapped[str] = mapped_column(
        ForeignKey("model_versions.id"), index=True, nullable=False
    )
    probability: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    calibrated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    risk_band: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence: Mapped[str] = mapped_column(String(30), nullable=False)
    uncertainty_reason: Mapped[Optional[str]] = mapped_column(Text)
    reason_codes_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    features_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    assessment: Mapped[Assessment] = relationship(back_populates="prediction")
    model_version: Mapped[ModelVersion] = relationship()


class AssessmentStep(Base):
    __tablename__ = "assessment_steps"
    __table_args__ = (
        UniqueConstraint("assessment_id", "name", name="uq_assessment_step_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    input_reference_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    output_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    assessment: Mapped[Assessment] = relationship(back_populates="steps")


class RuleResult(Base):
    __tablename__ = "rule_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id"), index=True, nullable=False
    )
    rule_version: Mapped[str] = mapped_column(String(50), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    inputs_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    assessment: Mapped[Assessment] = relationship(back_populates="rule_results")


class Decision(TimestampMixin, Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id"), unique=True, index=True, nullable=False
    )
    automatic_recommendation: Mapped[str] = mapped_column(String(50), nullable=False)
    final_recommendation: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    hard_stop: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    reason_codes_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    risk_dimensions_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    conditions_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_by_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    assessment: Mapped[Assessment] = relationship(back_populates="decision")


class ReviewCase(TimestampMixin, Base):
    __tablename__ = "review_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id"), unique=True, index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default="pending_review", nullable=False)
    required_role: Mapped[str] = mapped_column(String(50), nullable=False)
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    reviewer_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    assessment: Mapped[Assessment] = relationship(back_populates="review_case")


class Alert(TimestampMixin, Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    alert_type: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    required_role: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="open", index=True, nullable=False)
    counterparty_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("counterparties.id"), index=True
    )
    transaction_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("trade_transactions.id"), index=True
    )
    screening_run_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("screening_runs.id"), index=True
    )
    reassessment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("assessments.id"), index=True
    )
    source_reference_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    assigned_to_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), index=True)
    created_by_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    acknowledged_by_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    resolved_by_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    resolution_rationale: Mapped[Optional[str]] = mapped_column(Text)


class MonitoringRun(Base):
    __tablename__ = "monitoring_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_type: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    force: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fuzzy_threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    list_versions_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    counters_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    initiated_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class Outcome(TimestampMixin, Base):
    __tablename__ = "outcomes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("trade_transactions.id"), unique=True, index=True, nullable=False
    )
    assessment_id: Mapped[Optional[str]] = mapped_column(ForeignKey("assessments.id"), index=True)
    outcome_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    days_past_due: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    loss_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    currency: Mapped[Optional[str]] = mapped_column(String(3))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    reported_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class DriftSnapshot(Base):
    __tablename__ = "drift_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    model_version_id: Mapped[str] = mapped_column(
        ForeignKey("model_versions.id"), index=True, nullable=False
    )
    window_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    labeled_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    thresholds_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ScheduledJob(TimestampMixin, Base):
    __tablename__ = "scheduled_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_key: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    parameters_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    next_run_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    last_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_status: Mapped[Optional[str]] = mapped_column(String(40), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class ScheduledJobExecution(Base):
    __tablename__ = "scheduled_job_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scheduled_job_id: Mapped[str] = mapped_column(
        ForeignKey("scheduled_jobs.id"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    triggered_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    result_reference_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.id"), index=True, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    recipient_role: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    claimed_by: Mapped[Optional[str]] = mapped_column(String(120))
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class PortfolioStressTest(Base):
    __tablename__ = "portfolio_stress_tests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    parameters_json: Mapped[str] = mapped_column(Text, nullable=False)
    portfolio_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class SupportingDocument(TimestampMixin, Base):
    __tablename__ = "supporting_documents"
    __table_args__ = (
        CheckConstraint(
            "(counterparty_id IS NOT NULL AND transaction_id IS NULL) OR "
            "(counterparty_id IS NULL AND transaction_id IS NOT NULL)",
            name="ck_document_single_parent",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    counterparty_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("counterparties.id"), index=True
    )
    transaction_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("trade_transactions.id"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    document_type: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    verification_status: Mapped[str] = mapped_column(
        String(40), default="unverified", nullable=False
    )
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    uploaded_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class ScreeningList(TimestampMixin, Base):
    __tablename__ = "screening_lists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    authority: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    active_version_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)


class ScreeningListVersion(TimestampMixin, Base):
    __tablename__ = "screening_list_versions"
    __table_args__ = (
        UniqueConstraint("screening_list_id", "version", name="uq_screening_list_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    screening_list_id: Mapped[str] = mapped_column(
        ForeignKey("screening_lists.id"), index=True, nullable=False
    )
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="validated", nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_file_key: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class ScreeningEntry(Base):
    __tablename__ = "screening_entries"
    __table_args__ = (
        UniqueConstraint("list_version_id", "source_entry_id", name="uq_screening_source_entry"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    list_version_id: Mapped[str] = mapped_column(
        ForeignKey("screening_list_versions.id"), index=True, nullable=False
    )
    source_entry_id: Mapped[str] = mapped_column(String(150), nullable=False)
    primary_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), default="entity", nullable=False)
    country: Mapped[Optional[str]] = mapped_column(String(2))
    address: Mapped[Optional[str]] = mapped_column(Text)
    program: Mapped[Optional[str]] = mapped_column(String(200))
    aliases_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    identifiers_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    remarks: Mapped[Optional[str]] = mapped_column(Text)


class ScreeningRun(Base):
    __tablename__ = "screening_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    counterparty_id: Mapped[str] = mapped_column(
        ForeignKey("counterparties.id"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(40), default="completed", nullable=False)
    fuzzy_threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    screened_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    candidates: Mapped[List["ScreeningCandidate"]] = relationship(
        cascade="all, delete-orphan", back_populates="run"
    )


class ScreeningCandidate(Base):
    __tablename__ = "screening_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    screening_run_id: Mapped[str] = mapped_column(
        ForeignKey("screening_runs.id"), index=True, nullable=False
    )
    counterparty_id: Mapped[str] = mapped_column(
        ForeignKey("counterparties.id"), index=True, nullable=False
    )
    related_party_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("related_parties.id"), index=True
    )
    list_version_id: Mapped[str] = mapped_column(
        ForeignKey("screening_list_versions.id"), index=True, nullable=False
    )
    screening_entry_id: Mapped[str] = mapped_column(
        ForeignKey("screening_entries.id"), nullable=False
    )
    source_list_code: Mapped[str] = mapped_column(String(60), nullable=False)
    screened_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_screened_name: Mapped[str] = mapped_column(String(500), nullable=False)
    screened_country: Mapped[Optional[str]] = mapped_column(String(2))
    screened_identifier: Mapped[Optional[str]] = mapped_column(String(150))
    matched_name: Mapped[str] = mapped_column(String(500), nullable=False)
    match_type: Mapped[str] = mapped_column(String(30), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    program: Mapped[Optional[str]] = mapped_column(String(200))
    matched_country: Mapped[Optional[str]] = mapped_column(String(2))
    matched_address: Mapped[Optional[str]] = mapped_column(Text)
    matched_identifiers_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True, nullable=False)
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_by_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    run: Mapped[ScreeningRun] = relationship(back_populates="candidates")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    object_type: Mapped[str] = mapped_column(String(80), nullable=False)
    object_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
