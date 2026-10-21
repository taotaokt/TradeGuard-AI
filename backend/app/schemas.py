from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(ORMModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool


class AuditEventRead(ORMModel):
    id: str
    actor_id: Optional[str]
    action: str
    object_type: str
    object_id: Optional[str]
    details_json: str
    created_at: datetime


class DashboardSummary(BaseModel):
    counterparties: int
    transactions: int
    pending_reviews: int
    compliance_holds: int
    open_alerts: int


class AliasCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    alias_type: str = Field(default="trading_name", max_length=40)
    script: Optional[str] = Field(default=None, max_length=40)


class AliasRead(ORMModel):
    id: str
    name: str
    alias_type: str
    script: Optional[str]


class RelatedPartyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    relationship_type: str = Field(min_length=1, max_length=50)
    country: Optional[str] = Field(default=None, min_length=2, max_length=2)
    identifier: Optional[str] = Field(default=None, max_length=150)

    @field_validator("country")
    @classmethod
    def normalize_country(cls, value: Optional[str]) -> Optional[str]:
        return value.upper() if value else value


class RelatedPartyRead(ORMModel):
    id: str
    name: str
    relationship_type: str
    country: Optional[str]
    identifier: Optional[str]


class CounterpartyCreate(BaseModel):
    legal_name: str = Field(min_length=2, max_length=300)
    jurisdiction: str = Field(min_length=2, max_length=2)
    registration_number: str = Field(min_length=2, max_length=120)
    website: Optional[str] = Field(default=None, max_length=500)
    primary_address: Optional[str] = None
    notes: Optional[str] = None
    aliases: List[AliasCreate] = Field(default_factory=list)
    related_parties: List[RelatedPartyCreate] = Field(default_factory=list)

    @field_validator("jurisdiction")
    @classmethod
    def normalize_jurisdiction(cls, value: str) -> str:
        return value.upper()


class CounterpartyUpdate(BaseModel):
    legal_name: Optional[str] = Field(default=None, min_length=2, max_length=300)
    website: Optional[str] = Field(default=None, max_length=500)
    primary_address: Optional[str] = None
    notes: Optional[str] = None
    expected_version: int = Field(ge=1)


class CounterpartyRead(ORMModel):
    id: str
    legal_name: str
    jurisdiction: str
    registration_number: str
    status: str
    website: Optional[str]
    primary_address: Optional[str]
    notes: Optional[str]
    version: int
    aliases: List[AliasRead]
    related_parties: List[RelatedPartyRead]
    created_at: datetime
    updated_at: datetime


class TransactionPartyCreate(BaseModel):
    role: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=300)
    counterparty_id: Optional[str] = None
    country: Optional[str] = Field(default=None, min_length=2, max_length=2)
    registration_number: Optional[str] = Field(default=None, max_length=120)

    @field_validator("country")
    @classmethod
    def normalize_country(cls, value: Optional[str]) -> Optional[str]:
        return value.upper() if value else value


class TransactionPartyRead(ORMModel):
    id: str
    role: str
    name: str
    counterparty_id: Optional[str]
    country: Optional[str]
    registration_number: Optional[str]


class TransactionCreate(BaseModel):
    reference: str = Field(min_length=2, max_length=100)
    product_description: str = Field(min_length=2)
    hs_code: Optional[str] = Field(default=None, max_length=30)
    quantity: Optional[Decimal] = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    quantity_unit: Optional[str] = Field(default=None, max_length=30)
    origin_country: str = Field(min_length=2, max_length=2)
    destination_country: str = Field(min_length=2, max_length=2)
    transshipment_country: Optional[str] = Field(default=None, min_length=2, max_length=2)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    payment_method: str = Field(min_length=2, max_length=50)
    payment_terms_days: int = Field(default=0, ge=0, le=730)
    deposit_percentage: Decimal = Field(
        default=Decimal("0.00"), ge=0, le=100, max_digits=5, decimal_places=2
    )
    incoterm: Optional[str] = Field(default=None, max_length=10)
    bank_beneficiary_name: Optional[str] = Field(default=None, max_length=300)
    bank_beneficiary_country: Optional[str] = Field(default=None, min_length=2, max_length=2)
    requested_credit_exposure: Optional[Decimal] = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    end_use: Optional[str] = None
    parties: List[TransactionPartyCreate] = Field(min_length=1)

    @field_validator(
        "origin_country",
        "destination_country",
        "transshipment_country",
        "bank_beneficiary_country",
    )
    @classmethod
    def normalize_country(cls, value: Optional[str]) -> Optional[str]:
        return value.upper() if value else value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class TransactionRead(ORMModel):
    id: str
    reference: str
    status: str
    version: int
    product_description: str
    hs_code: Optional[str]
    quantity: Optional[Decimal]
    quantity_unit: Optional[str]
    origin_country: str
    destination_country: str
    transshipment_country: Optional[str]
    amount: Decimal
    currency: str
    payment_method: str
    payment_terms_days: int
    deposit_percentage: Decimal
    incoterm: Optional[str]
    bank_beneficiary_name: Optional[str]
    bank_beneficiary_country: Optional[str]
    requested_credit_exposure: Optional[Decimal]
    end_use: Optional[str]
    parties: List[TransactionPartyRead]
    created_at: datetime
    updated_at: datetime


class TransactionUpdate(BaseModel):
    product_description: Optional[str] = Field(default=None, min_length=2)
    hs_code: Optional[str] = Field(default=None, max_length=30)
    quantity: Optional[Decimal] = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    quantity_unit: Optional[str] = Field(default=None, max_length=30)
    origin_country: Optional[str] = Field(default=None, min_length=2, max_length=2)
    destination_country: Optional[str] = Field(default=None, min_length=2, max_length=2)
    transshipment_country: Optional[str] = Field(default=None, min_length=2, max_length=2)
    amount: Optional[Decimal] = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    payment_method: Optional[str] = Field(default=None, min_length=2, max_length=50)
    payment_terms_days: Optional[int] = Field(default=None, ge=0, le=730)
    deposit_percentage: Optional[Decimal] = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    incoterm: Optional[str] = Field(default=None, max_length=10)
    bank_beneficiary_name: Optional[str] = Field(default=None, max_length=300)
    bank_beneficiary_country: Optional[str] = Field(default=None, min_length=2, max_length=2)
    requested_credit_exposure: Optional[Decimal] = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    end_use: Optional[str] = None
    expected_version: int = Field(ge=1)

    @field_validator(
        "origin_country",
        "destination_country",
        "transshipment_country",
        "bank_beneficiary_country",
    )
    @classmethod
    def normalize_optional_country(cls, value: Optional[str]) -> Optional[str]:
        return value.upper() if value else value

    @field_validator("currency")
    @classmethod
    def normalize_optional_currency(cls, value: Optional[str]) -> Optional[str]:
        return value.upper() if value else value


class AssessmentRead(ORMModel):
    id: str
    transaction_id: str
    version: int
    status: str
    current_step: str
    recommendation: Optional[str]
    rule_version: str
    model_version: Optional[str]
    created_at: datetime


class AssessmentStepRead(ORMModel):
    id: str
    name: str
    sequence: int
    status: str
    input_reference_json: str
    output_json: str
    error_message: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]


class RuleResultRead(ORMModel):
    id: str
    rule_version: str
    reason_code: str
    severity: str
    action: str
    explanation: str
    inputs_json: str
    created_at: datetime


class DecisionRead(ORMModel):
    id: str
    automatic_recommendation: str
    final_recommendation: str
    status: str
    hard_stop: bool
    summary: str
    reason_codes_json: str
    risk_dimensions_json: str
    conditions_json: str
    rationale: Optional[str]
    reviewed_by_id: Optional[str]
    reviewed_at: Optional[datetime]
    is_override: bool
    created_at: datetime
    updated_at: datetime


class ReviewCaseRead(ORMModel):
    id: str
    assessment_id: str
    status: str
    required_role: str
    rationale: Optional[str]
    reviewer_id: Optional[str]
    resolved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class PredictionRead(ORMModel):
    id: str
    model_version_id: str
    probability: Decimal
    calibrated: bool
    risk_band: str
    confidence: str
    uncertainty_reason: Optional[str]
    reason_codes_json: str
    features_json: str
    created_at: datetime


class AssessmentDetail(AssessmentRead):
    rule_checksum_sha256: Optional[str]
    input_snapshot_json: str
    screening_snapshot_json: str
    completed_at: Optional[datetime]
    steps: List[AssessmentStepRead]
    rule_results: List[RuleResultRead]
    decision: Optional[DecisionRead]
    review_case: Optional[ReviewCaseRead]
    prediction: Optional[PredictionRead]


class ReviewDecision(BaseModel):
    decision: Literal[
        "APPROVE",
        "APPROVE_WITH_CONDITIONS",
        "REQUEST_INFORMATION",
        "REJECT",
        "COMPLIANCE_HOLD",
    ]
    rationale: str = Field(min_length=10, max_length=4000)
    conditions: List[str] = Field(default_factory=list, max_length=20)


class AlertRead(ORMModel):
    id: str
    alert_type: str
    severity: str
    required_role: str
    title: str
    description: str
    status: str
    counterparty_id: Optional[str]
    transaction_id: Optional[str]
    screening_run_id: Optional[str]
    reassessment_id: Optional[str]
    source_reference_json: str
    assigned_to_id: Optional[str]
    created_by_id: Optional[str]
    acknowledged_by_id: Optional[str]
    acknowledged_at: Optional[datetime]
    resolved_by_id: Optional[str]
    resolved_at: Optional[datetime]
    resolution_rationale: Optional[str]
    created_at: datetime
    updated_at: datetime


class AlertAction(BaseModel):
    action: Literal["acknowledge", "assign", "resolve", "dismiss"]
    rationale: str = Field(min_length=5, max_length=4000)
    assignee_id: Optional[str] = None


class AlertReassessmentRequest(BaseModel):
    transaction_id: Optional[str] = None
    rationale: str = Field(min_length=5, max_length=4000)


class MonitoringRunRequest(BaseModel):
    force: bool = False
    fuzzy_threshold: int = Field(default=85, ge=50, le=100)


class MonitoringRunRead(ORMModel):
    id: str
    run_type: str
    status: str
    force: bool
    fuzzy_threshold: int
    list_versions_json: str
    counters_json: str
    error_message: Optional[str]
    initiated_by_id: str
    started_at: datetime
    completed_at: Optional[datetime]


class OutcomeCreate(BaseModel):
    assessment_id: Optional[str] = None
    outcome_type: Literal["paid_on_time", "delayed", "dispute", "material_loss", "cancelled"]
    due_at: Optional[datetime] = None
    settled_at: Optional[datetime] = None
    days_past_due: int = Field(default=0, ge=0, le=3650)
    loss_amount: Optional[Decimal] = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    notes: Optional[str] = Field(default=None, max_length=4000)

    @field_validator("currency")
    @classmethod
    def normalize_outcome_currency(cls, value: Optional[str]) -> Optional[str]:
        return value.upper() if value else value

    @model_validator(mode="after")
    def validate_outcome(self):
        if self.outcome_type == "paid_on_time" and self.days_past_due:
            raise ValueError("paid_on_time outcomes cannot have past-due days")
        if self.outcome_type == "delayed" and self.days_past_due < 1:
            raise ValueError("delayed outcomes require at least one past-due day")
        if self.outcome_type == "material_loss" and not self.loss_amount:
            raise ValueError("material_loss outcomes require a positive loss_amount")
        if self.loss_amount is not None and self.currency is None:
            raise ValueError("currency is required when loss_amount is supplied")
        return self


class OutcomeRead(ORMModel):
    id: str
    transaction_id: str
    assessment_id: Optional[str]
    outcome_type: str
    due_at: Optional[datetime]
    settled_at: Optional[datetime]
    days_past_due: int
    loss_amount: Optional[Decimal]
    currency: Optional[str]
    notes: Optional[str]
    version: int
    reported_by_id: str
    created_at: datetime
    updated_at: datetime


class DriftSnapshotRequest(BaseModel):
    window_days: int = Field(default=90, ge=1, le=730)
    minimum_sample_size: int = Field(default=20, ge=5, le=10000)


class DriftSnapshotRead(ORMModel):
    id: str
    model_version_id: str
    window_start: datetime
    window_end: datetime
    sample_size: int
    labeled_count: int
    status: str
    metrics_json: str
    thresholds_json: str
    created_by_id: str
    created_at: datetime


class ScheduledJobUpsert(BaseModel):
    enabled: bool = True
    interval_minutes: int = Field(ge=15, le=525600)
    next_run_at: Optional[datetime] = None
    force: bool = False
    fuzzy_threshold: int = Field(default=85, ge=50, le=100)
    window_days: int = Field(default=90, ge=1, le=730)
    minimum_sample_size: int = Field(default=20, ge=5, le=10000)


class ScheduledJobRead(ORMModel):
    id: str
    job_key: str
    enabled: bool
    interval_minutes: int
    parameters_json: str
    next_run_at: datetime
    last_started_at: Optional[datetime]
    last_completed_at: Optional[datetime]
    last_status: Optional[str]
    version: int
    updated_by_id: str
    created_at: datetime
    updated_at: datetime


class ScheduledRunRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=50)


class ScheduledJobExecutionRead(ORMModel):
    id: str
    scheduled_job_id: str
    status: str
    triggered_by_id: str
    result_reference_json: str
    error_message: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]


class NotificationClaimRequest(BaseModel):
    worker_id: str = Field(min_length=2, max_length=120)
    limit: int = Field(default=20, ge=1, le=100)


class NotificationResultRequest(BaseModel):
    worker_id: str = Field(min_length=2, max_length=120)
    status: Literal["delivered", "failed"]
    error: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_delivery_result(self):
        if self.status == "failed" and not self.error:
            raise ValueError("error is required for failed delivery")
        return self


class NotificationDeliveryRead(ORMModel):
    id: str
    alert_id: str
    idempotency_key: str
    channel: str
    recipient_role: str
    status: str
    payload_json: str
    attempt_count: int
    available_at: datetime
    claimed_by: Optional[str]
    claimed_at: Optional[datetime]
    delivered_at: Optional[datetime]
    last_error: Optional[str]
    created_at: datetime


class OperationsSummary(BaseModel):
    health: Literal["healthy", "attention"]
    open_alerts: int
    pending_notifications: int
    processing_notifications: int
    failed_notifications: int
    enabled_schedules: int
    overdue_schedules: int
    failed_executions_24h: int
    latest_rescreen_status: Optional[str]
    latest_drift_status: Optional[str]


class RuleVersionRead(ORMModel):
    id: str
    version: str
    status: str
    description: str
    checksum_sha256: str
    activated_at: Optional[datetime]
    created_at: datetime


class SupportingDocumentRead(ORMModel):
    id: str
    counterparty_id: Optional[str]
    transaction_id: Optional[str]
    original_filename: str
    document_type: str
    content_type: str
    size_bytes: int
    description: Optional[str]
    verification_status: str
    status: str
    uploaded_by_id: str
    created_at: datetime


class ScreeningListCreate(BaseModel):
    code: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=200)
    authority: str = Field(min_length=2, max_length=200)
    source_url: str = Field(min_length=8, max_length=1000)


class ScreeningListRead(ORMModel):
    id: str
    code: str
    name: str
    authority: str
    source_url: str
    active_version_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class ScreeningListVersionRead(ORMModel):
    id: str
    screening_list_id: str
    version: str
    status: str
    effective_at: datetime
    checksum_sha256: str
    source_filename: str
    entry_count: int
    imported_by_id: str
    created_at: datetime


class ScreeningRequest(BaseModel):
    fuzzy_threshold: int = Field(default=85, ge=50, le=100)


class ScreeningCandidateRead(ORMModel):
    id: str
    screening_run_id: str
    counterparty_id: str
    related_party_id: Optional[str]
    list_version_id: str
    source_list_code: str
    screened_name: str
    screened_country: Optional[str]
    screened_identifier: Optional[str]
    matched_name: str
    match_type: str
    score: Decimal
    program: Optional[str]
    matched_country: Optional[str]
    matched_address: Optional[str]
    matched_identifiers_json: str
    status: str
    rationale: Optional[str]
    reviewed_by_id: Optional[str]
    reviewed_at: Optional[datetime]
    created_at: datetime


class ScreeningRunRead(ORMModel):
    id: str
    counterparty_id: str
    status: str
    fuzzy_threshold: int
    screened_by_id: str
    created_at: datetime
    completed_at: datetime
    candidates: List[ScreeningCandidateRead]


class ScreeningResolution(BaseModel):
    classification: Literal["cleared", "possible", "confirmed", "insufficient_information"]
    rationale: str = Field(min_length=5, max_length=4000)
