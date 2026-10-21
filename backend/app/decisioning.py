import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.models import (
    Assessment,
    AssessmentStep,
    Counterparty,
    Decision,
    Prediction,
    ReviewCase,
    RuleResult,
    RuleVersion,
    ScreeningList,
    TradeTransaction,
    User,
)
from backend.app.ml_service import predict_transaction, register_model_version
from backend.app.screening import normalize_name


RULE_PATH = Path(__file__).resolve().parents[2] / "config" / "rules" / "v1.json"
REQUIRED_RULE_FIELDS = {
    "reason_code",
    "inputs",
    "condition",
    "severity",
    "action",
    "description",
    "explanatory_text",
}


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def assessment_detail_query():
    return select(Assessment).options(
        selectinload(Assessment.steps),
        selectinload(Assessment.rule_results),
        selectinload(Assessment.decision),
        selectinload(Assessment.review_case),
        selectinload(Assessment.prediction),
    )


def load_rule_config() -> Tuple[dict, str, str]:
    raw = RULE_PATH.read_bytes()
    config = json.loads(raw.decode("utf-8"))
    if not config.get("version") or config.get("status") != "active":
        raise RuntimeError("The rule configuration must have an active version")
    for rule in config.get("rules", []):
        missing = REQUIRED_RULE_FIELDS.difference(rule)
        if missing:
            raise RuntimeError(
                "Rule {} is missing fields: {}".format(
                    rule.get("reason_code", "unknown"), ", ".join(sorted(missing))
                )
            )
    canonical = _json(config)
    checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return config, checksum, canonical


def register_rule_version(db: Session, config: dict, checksum: str, canonical: str) -> RuleVersion:
    existing = db.scalar(select(RuleVersion).where(RuleVersion.version == config["version"]))
    if existing is not None:
        if existing.checksum_sha256 != checksum:
            raise RuntimeError(
                "Rule version {} changed without a new version identifier".format(config["version"])
            )
        return existing
    rule_version = RuleVersion(
        version=config["version"],
        status=config["status"],
        description=config.get("description", ""),
        checksum_sha256=checksum,
        config_json=canonical,
        activated_at=datetime.utcnow(),
    )
    db.add(rule_version)
    db.flush()
    return rule_version


def transaction_snapshot(transaction: TradeTransaction) -> dict:
    return {
        "transaction_id": transaction.id,
        "reference": transaction.reference,
        "transaction_version": transaction.version,
        "product_description": transaction.product_description,
        "hs_code": transaction.hs_code,
        "quantity": transaction.quantity,
        "quantity_unit": transaction.quantity_unit,
        "origin_country": transaction.origin_country,
        "destination_country": transaction.destination_country,
        "transshipment_country": transaction.transshipment_country,
        "amount": transaction.amount,
        "currency": transaction.currency,
        "payment_method": transaction.payment_method,
        "payment_terms_days": transaction.payment_terms_days,
        "deposit_percentage": transaction.deposit_percentage,
        "incoterm": transaction.incoterm,
        "bank_beneficiary_name": transaction.bank_beneficiary_name,
        "bank_beneficiary_country": transaction.bank_beneficiary_country,
        "requested_credit_exposure": transaction.requested_credit_exposure,
        "end_use": transaction.end_use,
        "parties": [
            {
                "id": party.id,
                "role": party.role,
                "name": party.name,
                "country": party.country,
                "registration_number": party.registration_number,
                "counterparty_id": party.counterparty_id,
            }
            for party in transaction.parties
        ],
    }


def evaluate_rules(config: dict, transaction: TradeTransaction) -> List[dict]:
    party_names = {normalize_name(party.name) for party in transaction.parties}
    party_roles = {party.role for party in transaction.parties}
    results = []
    for rule in config["rules"]:
        condition = rule["condition"]
        triggered = False
        observed: Dict[str, object] = {}

        if condition == "beneficiary_name_not_in_transaction_parties":
            beneficiary = transaction.bank_beneficiary_name
            triggered = bool(beneficiary) and normalize_name(beneficiary) not in party_names
            observed = {
                "bank_beneficiary_name": beneficiary,
                "transaction_party_names": sorted(party.name for party in transaction.parties),
            }
        elif condition == "end_user_party_missing":
            triggered = "end_user" not in party_roles
            observed = {"party_roles": sorted(party_roles)}
        elif condition == "end_use_missing_or_vague":
            value = (transaction.end_use or "").strip()
            triggered = len(value) < 10 or value.casefold() in {"unknown", "n/a", "tbd", "general"}
            observed = {"end_use": value}
        elif condition == "payment_terms_above_threshold":
            threshold = int(rule.get("parameters", {}).get("payment_terms_days", 30))
            triggered = transaction.payment_terms_days > threshold
            observed = {
                "payment_terms_days": transaction.payment_terms_days,
                "threshold": threshold,
            }
        elif condition == "credit_exposure_above_threshold":
            threshold = Decimal(
                str(rule.get("parameters", {}).get("maximum_credit_exposure", 100000))
            )
            exposure = transaction.requested_credit_exposure or Decimal("0")
            triggered = exposure > threshold
            observed = {"requested_credit_exposure": exposure, "threshold": threshold}
        else:
            raise RuntimeError("Unknown rule condition: {}".format(condition))

        if triggered:
            results.append(
                {
                    "reason_code": rule["reason_code"],
                    "severity": rule["severity"],
                    "action": rule["action"],
                    "explanation": rule["explanatory_text"],
                    "inputs": observed,
                }
            )
    return results


def _add_step(
    assessment: Assessment,
    *,
    name: str,
    sequence: int,
    step_status: str,
    inputs: dict,
    output: dict,
    error: str = None,
) -> None:
    assessment.steps.append(
        AssessmentStep(
            name=name,
            sequence=sequence,
            status=step_status,
            input_reference_json=_json(inputs),
            output_json=_json(output),
            error_message=error,
            completed_at=datetime.utcnow(),
        )
    )


def _screening_state(db: Session, transaction: TradeTransaction) -> dict:
    counterparty_ids = sorted(
        {party.counterparty_id for party in transaction.parties if party.counterparty_id}
    )
    counterparties = [db.get(Counterparty, identifier) for identifier in counterparty_ids]
    active_versions = [
        item.active_version_id
        for item in db.scalars(select(ScreeningList).where(ScreeningList.active_version_id.is_not(None)))
    ]
    statuses = {
        item.id: item.status for item in counterparties if item is not None
    }
    return {
        "counterparty_ids": counterparty_ids,
        "counterparty_statuses": statuses,
        "active_list_versions": active_versions,
        "has_confirmed_hold": any(value == "compliance_hold" for value in statuses.values()),
        "has_possible_match": any(value == "screening_review" for value in statuses.values()),
        "has_unscreened_party": (
            not counterparty_ids
            or len(statuses) != len(counterparty_ids)
            or any(value == "draft" for value in statuses.values())
        ),
        "has_active_lists": bool(active_versions),
    }


def _recommend(screening: dict, rules: List[dict], prediction: dict = None) -> Tuple[str, bool, str]:
    critical_rules = [item for item in rules if item["severity"] == "critical"]
    if screening["has_confirmed_hold"]:
        return (
            "COMPLIANCE_HOLD",
            True,
            "A linked counterparty has a confirmed compliance concern. This state cannot be overridden by a risk score.",
        )
    if critical_rules:
        return (
            "REQUEST_INFORMATION",
            True,
            "A critical deterministic rule requires correction and reassessment.",
        )
    if any(item["action"] == "request_information" for item in rules):
        return "REQUEST_INFORMATION", False, "Required transaction information is missing or inconsistent."
    if (
        screening["has_possible_match"]
        or screening["has_unscreened_party"]
        or not screening["has_active_lists"]
    ):
        return "REFER", False, "Screening is incomplete or contains candidates requiring human review."
    if any(item["action"] == "manual_review" for item in rules):
        return "REFER", False, "One or more policy rules require human risk review."
    if prediction is None:
        return "REFER", False, "The commercial-risk model was unavailable, so human review is required."
    if prediction["confidence"] == "low":
        return "REFER", False, "The model input is outside its documented training range."
    if prediction["risk_band"] != "low":
        return "REFER", False, "The calibrated commercial-risk estimate requires human review."
    return "APPROVE", False, "No deterministic policy or confirmed compliance issue was found."


def orchestrate_assessment(
    db: Session, transaction: TradeTransaction, user: User
) -> Assessment:
    config, checksum, canonical = load_rule_config()
    register_rule_version(db, config, checksum, canonical)
    latest_version = db.scalar(
        select(func.max(Assessment.version)).where(Assessment.transaction_id == transaction.id)
    ) or 0
    snapshot = transaction_snapshot(transaction)
    assessment = Assessment(
        transaction_id=transaction.id,
        version=latest_version + 1,
        submitted_by_id=user.id,
        status="running",
        current_step="validation",
        rule_version=config["version"],
        rule_checksum_sha256=checksum,
        input_snapshot_json=_json(snapshot),
    )
    db.add(assessment)
    db.flush()

    _add_step(
        assessment,
        name="validation",
        sequence=1,
        step_status="completed",
        inputs={"transaction_id": transaction.id, "transaction_version": transaction.version},
        output={"valid": True, "critical_missing_fields": []},
    )

    assessment.current_step = "screening"
    screening = _screening_state(db, transaction)
    assessment.screening_snapshot_json = _json(screening)
    screening_incomplete = screening["has_unscreened_party"] or not screening["has_active_lists"]
    _add_step(
        assessment,
        name="screening",
        sequence=2,
        step_status="incomplete" if screening_incomplete else "completed",
        inputs={"counterparty_ids": screening["counterparty_ids"]},
        output=screening,
        error="No current complete screening result" if screening_incomplete else None,
    )

    assessment.current_step = "rules"
    evaluations = evaluate_rules(config, transaction)
    for result in evaluations:
        assessment.rule_results.append(
            RuleResult(
                rule_version=config["version"],
                reason_code=result["reason_code"],
                severity=result["severity"],
                action=result["action"],
                explanation=result["explanation"],
                inputs_json=_json(result["inputs"]),
            )
        )
    _add_step(
        assessment,
        name="rules",
        sequence=3,
        step_status="completed",
        inputs={"rule_version": config["version"], "checksum_sha256": checksum},
        output={"triggered_reason_codes": [item["reason_code"] for item in evaluations]},
    )

    assessment.current_step = "model"
    prediction = None
    model_error = None
    try:
        prediction = predict_transaction(db, transaction)
        model_version = register_model_version(db, prediction["manifest"])
        assessment.model_version = model_version.version
        assessment.prediction = Prediction(
            model_version_id=model_version.id,
            probability=Decimal(str(round(prediction["probability"], 6))),
            calibrated=True,
            risk_band=prediction["risk_band"],
            confidence=prediction["confidence"],
            uncertainty_reason=prediction["uncertainty_reason"],
            reason_codes_json=_json(prediction["reason_codes"]),
            features_json=_json(prediction["features"]),
        )
    except (OSError, ValueError, RuntimeError) as exc:
        model_error = str(exc)
    _add_step(
        assessment,
        name="model",
        sequence=4,
        step_status="completed" if prediction else "incomplete",
        inputs={"feature_schema": list(prediction["features"]) if prediction else []},
        output={
            "model_version": assessment.model_version,
            "probability": prediction["probability"] if prediction else None,
            "risk_band": prediction["risk_band"] if prediction else None,
            "confidence": prediction["confidence"] if prediction else None,
            "reason_codes": prediction["reason_codes"] if prediction else [],
        },
        error=model_error,
    )

    assessment.current_step = "decision"
    recommendation, hard_stop, summary = _recommend(screening, evaluations, prediction)
    severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    transaction_severity = max(
        (item["severity"] for item in evaluations),
        key=lambda value: severity_order.get(value, 0),
        default="low",
    )
    compliance_dimension = (
        "confirmed_concern"
        if screening["has_confirmed_hold"]
        else "possible_match"
        if screening["has_possible_match"]
        else "insufficient_information"
        if screening_incomplete
        else "clear"
    )
    decision_status = "final" if recommendation == "APPROVE" else "pending_review"
    assessment.decision = Decision(
        automatic_recommendation=recommendation,
        final_recommendation=recommendation,
        status=decision_status,
        hard_stop=hard_stop,
        summary=summary,
        reason_codes_json=_json(
            [item["reason_code"] for item in evaluations]
            + (prediction["reason_codes"] if prediction else ["MODEL_UNAVAILABLE"])
        ),
        risk_dimensions_json=_json(
            {
                "identity_kyb": "insufficient" if screening["has_unscreened_party"] else "reviewed",
                "compliance": compliance_dimension,
                "transaction": transaction_severity,
                "commercial_credit": prediction["risk_band"] if prediction else "unavailable",
                "country_logistics": "not_evaluated",
                "portfolio_concentration": "not_evaluated",
            }
        ),
    )

    if recommendation != "APPROVE":
        required_role = (
            "compliance_reviewer"
            if recommendation == "COMPLIANCE_HOLD" or screening["has_possible_match"]
            else "risk_reviewer"
        )
        assessment.review_case = ReviewCase(required_role=required_role)

    status_by_recommendation = {
        "APPROVE": "completed",
        "REFER": "pending_review",
        "REQUEST_INFORMATION": "information_required",
        "COMPLIANCE_HOLD": "compliance_hold",
    }
    assessment.status = status_by_recommendation[recommendation]
    assessment.recommendation = recommendation
    assessment.completed_at = datetime.utcnow()
    _add_step(
        assessment,
        name="decision",
        sequence=5,
        step_status="completed",
        inputs={"precedence": "compliance > critical rules > missing info > review > approve"},
        output={"recommendation": recommendation, "hard_stop": hard_stop, "summary": summary},
    )
    transaction.status = "assessed" if recommendation == "APPROVE" else "under_review"
    db.flush()
    return assessment
