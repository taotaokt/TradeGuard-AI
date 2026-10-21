from typing import Dict, Iterable, Tuple


DRIFT_THRESHOLDS = {
    "mean_probability_shift_warning": 0.05,
    "mean_probability_shift_critical": 0.10,
    "low_confidence_rate_warning": 0.10,
    "low_confidence_rate_critical": 0.25,
    "calibration_gap_warning": 0.10,
    "calibration_gap_critical": 0.20,
}


def _is_adverse_outcome(outcome) -> bool:
    return (
        outcome.outcome_type in {"dispute", "material_loss"}
        or outcome.days_past_due >= 90
    )


def calculate_drift_metrics(
    predictions: Iterable[dict],
    outcomes_by_transaction: Dict[str, object],
    *,
    reference_positive_rate: float,
    minimum_sample_size: int,
) -> Tuple[str, dict, dict]:
    rows = list(predictions)
    probabilities = [float(item["probability"]) for item in rows]
    sample_size = len(rows)
    mean_probability = sum(probabilities) / sample_size if sample_size else 0.0
    low_confidence_rate = (
        sum(item["confidence"] == "low" for item in rows) / sample_size
        if sample_size
        else 0.0
    )
    risk_bands = {band: 0 for band in ("low", "medium", "high", "critical")}
    for item in rows:
        risk_bands[item["risk_band"]] = risk_bands.get(item["risk_band"], 0) + 1
    risk_band_rates = {
        band: count / sample_size if sample_size else 0.0
        for band, count in risk_bands.items()
    }

    labeled = [
        (item, outcomes_by_transaction[item["transaction_id"]])
        for item in rows
        if item["transaction_id"] in outcomes_by_transaction
    ]
    actuals = [float(_is_adverse_outcome(outcome)) for _, outcome in labeled]
    labeled_probabilities = [float(item["probability"]) for item, _ in labeled]
    observed_adverse_rate = sum(actuals) / len(actuals) if actuals else None
    brier_score = (
        sum((probability - actual) ** 2 for probability, actual in zip(labeled_probabilities, actuals))
        / len(actuals)
        if actuals
        else None
    )
    calibration_gap = (
        abs(sum(labeled_probabilities) / len(labeled_probabilities) - observed_adverse_rate)
        if actuals
        else None
    )
    mean_probability_shift = abs(mean_probability - reference_positive_rate)

    metrics = {
        "sample_size": sample_size,
        "labeled_count": len(labeled),
        "reference_positive_rate": round(reference_positive_rate, 6),
        "mean_probability": round(mean_probability, 6),
        "mean_probability_shift": round(mean_probability_shift, 6),
        "low_confidence_rate": round(low_confidence_rate, 6),
        "risk_band_rates": {key: round(value, 6) for key, value in risk_band_rates.items()},
        "observed_adverse_rate": (
            round(observed_adverse_rate, 6) if observed_adverse_rate is not None else None
        ),
        "brier_score": round(brier_score, 6) if brier_score is not None else None,
        "calibration_gap": round(calibration_gap, 6) if calibration_gap is not None else None,
    }

    if sample_size < minimum_sample_size:
        status = "insufficient_data"
    else:
        critical = (
            mean_probability_shift >= DRIFT_THRESHOLDS["mean_probability_shift_critical"]
            or low_confidence_rate >= DRIFT_THRESHOLDS["low_confidence_rate_critical"]
            or (
                calibration_gap is not None
                and len(labeled) >= minimum_sample_size
                and calibration_gap >= DRIFT_THRESHOLDS["calibration_gap_critical"]
            )
        )
        warning = (
            mean_probability_shift >= DRIFT_THRESHOLDS["mean_probability_shift_warning"]
            or low_confidence_rate >= DRIFT_THRESHOLDS["low_confidence_rate_warning"]
            or (
                calibration_gap is not None
                and len(labeled) >= minimum_sample_size
                and calibration_gap >= DRIFT_THRESHOLDS["calibration_gap_warning"]
            )
        )
        status = "critical" if critical else "warning" if warning else "stable"
    return status, metrics, DRIFT_THRESHOLDS
