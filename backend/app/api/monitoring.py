import json
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.audit import record_audit_event
from backend.app.db import get_db
from backend.app.decisioning import assessment_detail_query, orchestrate_assessment
from backend.app.deps import require_roles
from backend.app.drift import calculate_drift_metrics
from backend.app.models import (
    Alert,
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
    TradeTransaction,
    User,
)
from backend.app.monitoring import create_outcome_alert
from backend.app.schemas import (
    AlertAction,
    AlertRead,
    AlertReassessmentRequest,
    AssessmentDetail,
    DriftSnapshotRead,
    DriftSnapshotRequest,
    MonitoringRunRead,
    MonitoringRunRequest,
    OutcomeCreate,
    OutcomeRead,
)
from backend.app.screening_service import run_counterparty_screening


router = APIRouter(tags=["monitoring"])
alert_user = require_roles(
    {"admin", "risk_reviewer", "compliance_reviewer", "model_developer"}
)
monitoring_user = require_roles({"admin", "compliance_reviewer"})
outcome_user = require_roles(
    {"admin", "business_user", "risk_reviewer", "compliance_reviewer"}
)
drift_user = require_roles({"admin", "risk_reviewer", "model_developer"})
ALERT_STATUSES = {"open", "acknowledged", "resolved", "dismissed"}
REVIEWER_ROLES = {"admin", "risk_reviewer", "compliance_reviewer", "model_developer"}


def _ensure_alert_permission(alert: Alert, user: User) -> None:
    if user.role != "admin" and user.role != alert.required_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This alert requires the {} role".format(alert.required_role),
        )


@router.get("/alerts", response_model=List[AlertRead])
def list_alerts(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    counterparty_id: Optional[str] = Query(default=None),
    assigned_to_me: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(alert_user),
) -> List[Alert]:
    if status_filter is not None and status_filter not in ALERT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Unsupported alert status",
        )
    query = select(Alert)
    if status_filter:
        query = query.where(Alert.status == status_filter)
    if counterparty_id:
        query = query.where(Alert.counterparty_id == counterparty_id)
    if assigned_to_me:
        query = query.where(Alert.assigned_to_id == user.id)
    return list(db.scalars(query.order_by(Alert.created_at.desc())))


@router.post("/alerts/{alert_id}/actions", response_model=AlertRead)
def act_on_alert(
    alert_id: str,
    payload: AlertAction,
    db: Session = Depends(get_db),
    user: User = Depends(alert_user),
) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    _ensure_alert_permission(alert, user)
    if alert.status in {"resolved", "dismissed"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Alert is already closed")

    previous_status = alert.status
    if payload.action == "assign":
        if payload.assignee_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="assignee_id is required for assignment",
            )
        assignee = db.get(User, payload.assignee_id)
        allowed_assignee_roles = {"admin", alert.required_role}
        if (
            assignee is None
            or not assignee.is_active
            or assignee.role not in REVIEWER_ROLES
            or assignee.role not in allowed_assignee_roles
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Assignee must be an active reviewer or administrator",
            )
        alert.assigned_to_id = assignee.id
    elif payload.action == "acknowledge":
        alert.status = "acknowledged"
        alert.acknowledged_by_id = user.id
        alert.acknowledged_at = datetime.utcnow()
        if alert.assigned_to_id is None:
            alert.assigned_to_id = user.id
    else:
        alert.status = "resolved" if payload.action == "resolve" else "dismissed"
        alert.resolved_by_id = user.id
        alert.resolved_at = datetime.utcnow()
        alert.resolution_rationale = payload.rationale.strip()

    record_audit_event(
        db,
        actor_id=user.id,
        action={
            "acknowledge": "alert.acknowledged",
            "assign": "alert.assigned",
            "resolve": "alert.resolved",
            "dismiss": "alert.dismissed",
        }[payload.action],
        object_type="alert",
        object_id=alert.id,
        details={
            "from": previous_status,
            "to": alert.status,
            "assignee_id": alert.assigned_to_id,
            "rationale": payload.rationale.strip(),
        },
    )
    db.commit()
    db.refresh(alert)
    return alert


@router.post("/alerts/{alert_id}/reassess", response_model=AssessmentDetail)
def reassess_from_alert(
    alert_id: str,
    payload: AlertReassessmentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(alert_user),
) -> Assessment:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    _ensure_alert_permission(alert, user)
    if alert.status in {"resolved", "dismissed"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Alert is already closed")

    transaction_id = payload.transaction_id or alert.transaction_id
    if transaction_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="transaction_id is required because this alert is not linked to a transaction",
        )
    transaction = db.scalar(
        select(TradeTransaction)
        .options(selectinload(TradeTransaction.parties))
        .where(TradeTransaction.id == transaction_id)
    )
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    linked_counterparty_ids = {
        party.counterparty_id for party in transaction.parties if party.counterparty_id
    }
    if alert.counterparty_id and alert.counterparty_id not in linked_counterparty_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Transaction is not linked to the alert counterparty",
        )
    roles = {party.role for party in transaction.parties}
    missing = []
    if not roles.intersection({"buyer", "seller", "counterparty"}):
        missing.append("buyer, seller, or counterparty")
    if not transaction.end_use:
        missing.append("end_use")
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": "Critical information is missing", "fields": missing},
        )

    assessment = orchestrate_assessment(db, transaction, user)
    alert.transaction_id = transaction.id
    alert.reassessment_id = assessment.id
    alert.status = "resolved"
    alert.resolved_by_id = user.id
    alert.resolved_at = datetime.utcnow()
    alert.resolution_rationale = payload.rationale.strip()
    record_audit_event(
        db,
        actor_id=user.id,
        action="assessment.submitted_from_alert",
        object_type="assessment",
        object_id=assessment.id,
        details={
            "alert_id": alert.id,
            "transaction_id": transaction.id,
            "version": assessment.version,
            "recommendation": assessment.recommendation,
        },
    )
    record_audit_event(
        db,
        actor_id=user.id,
        action="alert.reassessment_created",
        object_type="alert",
        object_id=alert.id,
        details={
            "transaction_id": transaction.id,
            "assessment_id": assessment.id,
            "rationale": alert.resolution_rationale,
        },
    )
    db.commit()
    return db.scalar(assessment_detail_query().where(Assessment.id == assessment.id))


@router.post(
    "/monitoring/runs/rescreen",
    response_model=MonitoringRunRead,
    status_code=status.HTTP_201_CREATED,
)
def run_portfolio_rescreening(
    payload: MonitoringRunRequest,
    db: Session = Depends(get_db),
    user: User = Depends(monitoring_user),
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
        force=payload.force,
        fuzzy_threshold=payload.fuzzy_threshold,
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
            not payload.force
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
            fuzzy_threshold=payload.fuzzy_threshold,
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
        details={**counters, "force": payload.force, "list_version_ids": active_version_ids},
    )
    db.commit()
    db.refresh(monitoring_run)
    return monitoring_run


@router.get("/monitoring/runs", response_model=List[MonitoringRunRead])
def list_monitoring_runs(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(monitoring_user),
) -> List[MonitoringRun]:
    return list(
        db.scalars(select(MonitoringRun).order_by(MonitoringRun.started_at.desc()).limit(limit))
    )


@router.post(
    "/transactions/{transaction_id}/outcome",
    response_model=OutcomeRead,
    status_code=status.HTTP_201_CREATED,
)
def record_transaction_outcome(
    transaction_id: str,
    payload: OutcomeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(outcome_user),
) -> Outcome:
    transaction = db.scalar(
        select(TradeTransaction)
        .options(selectinload(TradeTransaction.parties))
        .where(TradeTransaction.id == transaction_id)
    )
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    if db.scalar(select(Outcome.id).where(Outcome.transaction_id == transaction_id)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An outcome is already recorded for this transaction",
        )
    if payload.assessment_id:
        assessment = db.get(Assessment, payload.assessment_id)
        if assessment is None or assessment.transaction_id != transaction.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="assessment_id must belong to this transaction",
            )

    outcome = Outcome(
        **payload.model_dump(),
        transaction_id=transaction.id,
        reported_by_id=user.id,
    )
    db.add(outcome)
    db.flush()
    adverse = (
        outcome.outcome_type in {"dispute", "material_loss"}
        or outcome.days_past_due >= 30
    )
    if adverse:
        create_outcome_alert(db, outcome=outcome, transaction=transaction, actor=user)
        transaction.status = "adverse_outcome"
    elif outcome.outcome_type in {"paid_on_time", "cancelled"}:
        transaction.status = "completed"
    record_audit_event(
        db,
        actor_id=user.id,
        action="transaction.outcome_recorded",
        object_type="outcome",
        object_id=outcome.id,
        details={
            "transaction_id": transaction.id,
            "outcome_type": outcome.outcome_type,
            "days_past_due": outcome.days_past_due,
            "adverse_alert_created": adverse,
        },
    )
    db.commit()
    db.refresh(outcome)
    return outcome


@router.get("/transactions/{transaction_id}/outcome", response_model=OutcomeRead)
def get_transaction_outcome(
    transaction_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(outcome_user),
) -> Outcome:
    outcome = db.scalar(select(Outcome).where(Outcome.transaction_id == transaction_id))
    if outcome is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outcome not found")
    return outcome


@router.post(
    "/monitoring/drift-snapshots",
    response_model=DriftSnapshotRead,
    status_code=status.HTTP_201_CREATED,
)
def create_drift_snapshot(
    payload: DriftSnapshotRequest,
    db: Session = Depends(get_db),
    user: User = Depends(drift_user),
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
    window_start = window_end - timedelta(days=payload.window_days)
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
        minimum_sample_size=payload.minimum_sample_size,
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
        alert = Alert(
            alert_type="model_drift",
            severity="critical" if drift_status == "critical" else "medium",
            required_role="model_developer",
            title="Model monitoring threshold exceeded",
            description=(
                "The {} prediction window produced a {} drift status."
            ).format(model_version.version, drift_status),
            created_by_id=user.id,
            source_reference_json=json.dumps(
                {"drift_snapshot_id": snapshot.id, "model_version": model_version.version},
                sort_keys=True,
            ),
        )
        db.add(alert)
        db.flush()
        record_audit_event(
            db,
            actor_id=user.id,
            action="alert.created",
            object_type="alert",
            object_id=alert.id,
            details={"alert_type": "model_drift", "drift_snapshot_id": snapshot.id},
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
    db.commit()
    db.refresh(snapshot)
    return snapshot


@router.get("/monitoring/drift-snapshots", response_model=List[DriftSnapshotRead])
def list_drift_snapshots(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(drift_user),
) -> List[DriftSnapshot]:
    return list(
        db.scalars(select(DriftSnapshot).order_by(DriftSnapshot.created_at.desc()).limit(limit))
    )
