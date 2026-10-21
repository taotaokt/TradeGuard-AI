FEATURE_NAMES = [
    "amount_usd_log",
    "payment_terms_days",
    "deposit_percentage",
    "requested_credit_exposure_ratio",
    "has_letter_of_credit",
    "has_transshipment",
    "counterparty_active",
    "transaction_document_count",
    "counterparty_evidence_count",
]

TARGET_NAME = "severe_delinquency_90d"
TARGET_DEFINITION = (
    "Synthetic indicator that a trade invoice becomes at least 90 days past due or produces a "
    "material payment loss within 180 days after its contractual due date."
)

RISK_BAND_THRESHOLDS = {
    "low": 0.10,
    "medium": 0.25,
    "high": 0.45,
}
