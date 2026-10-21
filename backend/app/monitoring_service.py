import json
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.audit import record_audit_event
from backend.app.drift import calculate_drift_metrics
from backend.app.models import (
    Assessment,
    Counterparty,
    DriftSnapshot,
    ModelVersion,
    MonitoringRun,
    Outcome,
    Prediction,
    ScreeningList,
    ScreeningListVersion,
    ScreeningRun,
    User,
)
from backend.app.monitoring import create_drift_alert
from backend.app.screening_service import run_counterparty_screening


def execute_portfolio_rescreen(
    db: Session,
    *,
    user: User,
    force: bool,
    fuzzy_threshold: int,
) -> MonitoringRun:
    active_lists = list(
        db.scalars(select(ScreeningList).where(ScreeningList.active_version_id.is_not(None)))
    )
    if not active_lists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active screening-list version is configured",
        )
    active_version_ids = [item.active_version_id for item in active_lists]
    active_versions = list(
        db.scalars(
            select(ScreeningListVersion).where(ScreeningListVersion.id.in_(active_version_ids))
        )
    )
    latest_list_change = max(item.created_at for item in active_versions)
    monitoring_run = MonitoringRun(
        run_type="portfolio_rescreen",
        status="running",
        force=force,
        fuzzy_threshold=fuzzy_threshold,
        list_versions_json=json.dumps(sorted(active_version_ids)),
        initiated_by_id=user.id,
    )
    db.add(monitoring_run)
    db.flush()

    counterparties = list(
        db.scalars(
            select(Counterparty)
            .options(
                selectinload(Counterparty.aliases),
                selectinload(Counterparty.related_parties),
            )
            .where(Counterparty.status != "archived")
            .order_by(Counterparty.created_at)
        ).unique()
    )
    processed = 0
    skipped_current = 0
    candidate_count = 0
    for counterparty in counterparties:
        latest_run = db.scalar(
            select(ScreeningRun)
            .where(ScreeningRun.counterparty_id == counterparty.id)
            .order_by(ScreeningRun.created_at.desc())
            .limit(1)
        )
        if (
            not force
            and latest_run is not None
            and latest_run.created_at >= latest_list_change
        ):
            skipped_current += 1
            continue
        screening_run = run_counterparty_screening(
            db,
            counterparty=counterparty,
            active_lists=active_lists,
            user=user,
            fuzzy_threshold=fuzzy_threshold,
        )
        processed += 1
        candidate_count += len(screening_run.candidates)

    counters = {
        "eligible_counterparties": len(counterparties),
        "processed": processed,
        "skipped_current": skipped_current,
        "candidate_count": candidate_count,
    }
    monitoring_run.status = "completed"
    monitoring_run.counters_json = json.dumps(counters, sort_keys=True)
    monitoring_run.completed_at = datetime.utcnow()
    record_audit_event(
        db,
        actor_id=user.id,
        action="monitoring.portfolio_rescreened",
        object_type="monitoring_run",
        object_id=monitoring_run.id,
        details={**counters, "force": force, "list_version_ids": active_version_ids},
    )
    return monitoring_run


def execute_drift_snapshot(
    db: Session,
    *,
    user: User,
    window_days: int,
    minimum_sample_size: int,
) -> DriftSnapshot:
    model_version = db.scalar(
        select(ModelVersion)
        .where(ModelVersion.status == "champion")
        .order_by(ModelVersion.trained_at.desc())
        .limit(1)
    )
    if model_version is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No registered champion model is available",
        )
    window_end = datetime.utcnow()
    window_start = window_end - timedelta(days=window_days)
    rows = db.execute(
        select(Prediction, Assessment.transaction_id)
        .join(Assessment, Assessment.id == Prediction.assessment_id)
        .where(
            Prediction.model_version_id == model_version.id,
            Prediction.created_at >= window_start,
            Prediction.created_at <= window_end,
        )
    ).all()
    prediction_rows = [
        {
            "transaction_id": transaction_id,
            "probability": prediction.probability,
            "confidence": prediction.confidence,
            "risk_band": prediction.risk_band,
        }
        for prediction, transaction_id in rows
    ]
    transaction_ids = {item["transaction_id"] for item in prediction_rows}
    outcomes = (
        list(db.scalars(select(Outcome).where(Outcome.transaction_id.in_(transaction_ids))))
        if transaction_ids
        else []
    )
    metrics_document = json.loads(model_version.metrics_json)
    reference_metrics = metrics_document.get(model_version.name) or next(
        iter(metrics_document.values())
    )
    drift_status, metrics, thresholds = calculate_drift_metrics(
        prediction_rows,
        {item.transaction_id: item for item in outcomes},
        reference_positive_rate=float(reference_metrics["positive_rate"]),
        minimum_sample_size=minimum_sample_size,
    )
    snapshot = DriftSnapshot(
        model_version_id=model_version.id,
        window_start=window_start,
        window_end=window_end,
        sample_size=metrics["sample_size"],
        labeled_count=metrics["labeled_count"],
        status=drift_status,
        metrics_json=json.dumps(metrics, sort_keys=True),
        thresholds_json=json.dumps(thresholds, sort_keys=True),
        created_by_id=user.id,
    )
    db.add(snapshot)
    db.flush()
    if drift_status in {"warning", "critical"}:
        create_drift_alert(
            db,
            snapshot=snapshot,
            model_version=model_version,
            actor=user,
        )
    record_audit_event(
        db,
        actor_id=user.id,
        action="model.drift_snapshot_created",
        object_type="drift_snapshot",
        object_id=snapshot.id,
        details={
            "model_version": model_version.version,
            "status": drift_status,
            "sample_size": snapshot.sample_size,
            "labeled_count": snapshot.labeled_count,
        },
    )
    return snapshot
