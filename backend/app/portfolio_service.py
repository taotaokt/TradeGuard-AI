import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.audit import record_audit_event
from backend.app.models import (
    Assessment,
    Outcome,
    PortfolioStressTest,
    Prediction,
    TradeTransaction,
    User,
)
from backend.app.schemas import PortfolioStressTestCreate, PortfolioSummary


MONEY = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _latest_predictions(
    db: Session, transaction_ids: Iterable[str]
) -> Dict[str, Prediction]:
    identifiers = list(transaction_ids)
    if not identifiers:
        return {}
    rows = db.execute(
        select(Assessment.transaction_id, Assessment.version, Prediction)
        .join(Prediction, Prediction.assessment_id == Assessment.id)
        .where(Assessment.transaction_id.in_(identifiers))
        .order_by(Assessment.transaction_id, Assessment.version.desc())
    ).all()
    latest = {}
    for transaction_id, _, prediction in rows:
        latest.setdefault(transaction_id, prediction)
    return latest


def _portfolio_rows(db: Session) -> Tuple[List[TradeTransaction], List[dict]]:
    transactions = list(
        db.scalars(select(TradeTransaction).order_by(TradeTransaction.created_at))
    )
    latest_predictions = _latest_predictions(db, (item.id for item in transactions))
    open_rows = []
    for transaction in transactions:
        if transaction.status == "completed":
            continue
        prediction = latest_predictions.get(transaction.id)
        exposure = transaction.requested_credit_exposure
        if exposure is None:
            exposure = transaction.amount
        open_rows.append(
            {
                "transaction_id": transaction.id,
                "reference": transaction.reference,
                "status": transaction.status,
                "destination_country": transaction.destination_country,
                "currency": transaction.currency,
                "exposure": _money(Decimal(exposure)),
                "probability": (
                    Decimal(prediction.probability) if prediction is not None else None
                ),
                "risk_band": prediction.risk_band if prediction is not None else "unscored",
            }
        )
    return transactions, open_rows


def _aggregate(rows: Iterable[dict], key_name: str) -> List[dict]:
    buckets = defaultdict(lambda: {"transaction_count": 0, "exposure": Decimal("0")})
    for row in rows:
        bucket_key = (row[key_name], row["currency"])
        buckets[bucket_key]["transaction_count"] += 1
        buckets[bucket_key]["exposure"] += row["exposure"]
    return [
        {
            "key": key,
            "currency": currency,
            "transaction_count": values["transaction_count"],
            "exposure": _money(values["exposure"]),
        }
        for (key, currency), values in sorted(buckets.items())
    ]


def build_portfolio_summary(db: Session) -> PortfolioSummary:
    transactions, open_rows = _portfolio_rows(db)
    outcomes = list(db.scalars(select(Outcome)))
    adverse_count = sum(
        item.outcome_type in {"dispute", "material_loss"} or item.days_past_due >= 30
        for item in outcomes
    )
    losses = defaultdict(lambda: {"transaction_count": 0, "exposure": Decimal("0")})
    for outcome in outcomes:
        if outcome.loss_amount is None or outcome.currency is None:
            continue
        bucket = losses[outcome.currency]
        bucket["transaction_count"] += 1
        bucket["exposure"] += Decimal(outcome.loss_amount)
    loss_buckets = [
        {
            "key": "recorded_loss",
            "currency": currency,
            "transaction_count": values["transaction_count"],
            "exposure": _money(values["exposure"]),
        }
        for currency, values in sorted(losses.items())
    ]
    scored_count = sum(row["probability"] is not None for row in open_rows)
    return PortfolioSummary(
        generated_at=datetime.utcnow(),
        transaction_count=len(transactions),
        open_transaction_count=len(open_rows),
        assessed_transaction_count=scored_count,
        unscored_transaction_count=len(open_rows) - scored_count,
        exposure_by_currency=_aggregate(
            ({**row, "currency_key": row["currency"]} for row in open_rows),
            "currency_key",
        ),
        exposure_by_risk_band=_aggregate(open_rows, "risk_band"),
        exposure_by_destination=_aggregate(open_rows, "destination_country"),
        outcomes={
            "outcome_count": len(outcomes),
            "adverse_outcome_count": adverse_count,
            "adverse_outcome_rate": adverse_count / len(outcomes) if outcomes else None,
            "losses_by_currency": loss_buckets,
        },
    )


def execute_portfolio_stress_test(
    db: Session,
    *,
    payload: PortfolioStressTestCreate,
    user: User,
) -> PortfolioStressTest:
    _, rows = _portfolio_rows(db)
    selected_countries = set(payload.selected_countries)
    growth_factor = Decimal("1") + payload.exposure_growth_percentage / Decimal("100")
    results_by_currency = defaultdict(
        lambda: {
            "transaction_count": 0,
            "baseline_exposure": Decimal("0"),
            "stressed_exposure": Decimal("0"),
            "baseline_expected_loss": Decimal("0"),
            "stressed_expected_loss": Decimal("0"),
        }
    )
    selected_country_transaction_count = 0
    snapshot_rows = []
    for row in rows:
        probability = (
            row["probability"]
            if row["probability"] is not None
            else payload.unscored_probability
        )
        country_is_selected = row["destination_country"] in selected_countries
        country_addon = (
            payload.country_probability_addon
            if country_is_selected
            else Decimal("0")
        )
        if country_is_selected:
            selected_country_transaction_count += 1
        stressed_probability = min(
            Decimal("1"),
            probability * payload.probability_multiplier + country_addon,
        )
        stressed_exposure = row["exposure"] * growth_factor
        baseline_expected_loss = row["exposure"] * probability * payload.loss_given_default
        stressed_expected_loss = (
            stressed_exposure * stressed_probability * payload.loss_given_default
        )
        bucket = results_by_currency[row["currency"]]
        bucket["transaction_count"] += 1
        bucket["baseline_exposure"] += row["exposure"]
        bucket["stressed_exposure"] += stressed_exposure
        bucket["baseline_expected_loss"] += baseline_expected_loss
        bucket["stressed_expected_loss"] += stressed_expected_loss
        snapshot_rows.append(
            {
                **row,
                "exposure": str(row["exposure"]),
                "probability": str(row["probability"]) if row["probability"] is not None else None,
                "effective_baseline_probability": str(probability),
            }
        )

    currency_results = []
    for currency, values in sorted(results_by_currency.items()):
        baseline_loss = _money(values["baseline_expected_loss"])
        stressed_loss = _money(values["stressed_expected_loss"])
        currency_results.append(
            {
                "currency": currency,
                "transaction_count": values["transaction_count"],
                "baseline_exposure": str(_money(values["baseline_exposure"])),
                "stressed_exposure": str(_money(values["stressed_exposure"])),
                "baseline_expected_loss": str(baseline_loss),
                "stressed_expected_loss": str(stressed_loss),
                "expected_loss_delta": str(_money(stressed_loss - baseline_loss)),
            }
        )
    result = {
        "affected_transactions": len(rows),
        "selected_country_transaction_count": selected_country_transaction_count,
        "by_currency": currency_results,
        "methodology": (
            "EAD x probability of adverse outcome x loss given default; currencies are not summed."
        ),
        "decision_effect": "none",
    }
    item = PortfolioStressTest(
        name=payload.name.strip(),
        status="completed",
        rationale=payload.rationale.strip(),
        parameters_json=json.dumps(payload.model_dump(mode="json"), sort_keys=True),
        portfolio_snapshot_json=json.dumps(
            {"generated_at": datetime.utcnow().isoformat(), "transactions": snapshot_rows},
            sort_keys=True,
        ),
        result_json=json.dumps(result, sort_keys=True),
        created_by_id=user.id,
    )
    db.add(item)
    db.flush()
    record_audit_event(
        db,
        actor_id=user.id,
        action="portfolio.stress_test_completed",
        object_type="portfolio_stress_test",
        object_id=item.id,
        details={
            "name": item.name,
            "affected_transactions": len(rows),
            "selected_countries": payload.selected_countries,
        },
    )
    return item
