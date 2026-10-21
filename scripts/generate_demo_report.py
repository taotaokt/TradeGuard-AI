import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from backend.app.models import Assessment, AssessmentStep, Decision, Prediction
from backend.app.reporting import build_assessment_pdf


def main() -> None:
    assessment = Assessment(
        id="demo-assessment-public-safe",
        transaction_id="demo-transaction-public-safe",
        version=1,
        status="pending_review",
        current_step="decision",
        recommendation="REFER",
        rule_version="v1",
        rule_checksum_sha256="2c0f9ea8a6fb21e0a1c83be6d57a68a521d4c9fe62d764aa2e75178b569fd305",
        model_version="synthetic-2026-10-21-v1",
        submitted_by_id="demo-user",
        input_snapshot_json=json.dumps(
            {
                "reference": "DEMO-EXPORT-001",
                "product_description": "Commercial refrigeration components",
                "origin_country": "CN",
                "destination_country": "US",
                "amount": "85000.00",
                "currency": "USD",
                "payment_method": "letter_of_credit",
                "payment_terms_days": 60,
                "deposit_percentage": "20.00",
                "end_use": "Installation in public-safe demonstration cold-storage facilities",
            }
        ),
        screening_snapshot_json="{}",
        completed_at=datetime(2026, 10, 21, 16, 45),
    )
    assessment.steps = [
        AssessmentStep(name=name, sequence=index, status="completed", completed_at=datetime(2026, 10, 21, 16, 45), input_reference_json="{}", output_json="{}")
        for index, name in enumerate(["validation", "screening", "rules", "model", "decision"], 1)
    ]
    assessment.decision = Decision(
        automatic_recommendation="REFER",
        final_recommendation="REFER",
        status="pending_review",
        hard_stop=False,
        summary="Extended payment terms require accountable human risk review.",
        reason_codes_json=json.dumps(["NEW_COUNTERPARTY_LONG_TERMS", "LIMITED_TRANSACTION_DOCUMENTS"]),
        risk_dimensions_json=json.dumps(
            {
                "identity_kyb": "reviewed",
                "compliance": "clear",
                "transaction": "medium",
                "commercial_credit": "medium",
                "country_logistics": "not_evaluated",
                "portfolio_concentration": "not_evaluated",
            }
        ),
        conditions_json="[]",
    )
    assessment.prediction = Prediction(
        model_version_id="demo-model",
        probability=Decimal("0.137500"),
        calibrated=True,
        risk_band="medium",
        confidence="high",
        reason_codes_json=json.dumps(["LIMITED_TRANSACTION_DOCUMENTS"]),
        features_json="{}",
    )
    output = Path("output/pdf/demo-assessment-report.pdf")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(build_assessment_pdf(assessment))
    print(output)


if __name__ == "__main__":
    main()
