import json
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.audit import record_audit_event
from backend.app.db import get_db
from backend.app.decisioning import assessment_detail_query, orchestrate_assessment
from backend.app.deps import require_roles
from backend.app.models import (
    Alert,
    Assessment,
    DriftSnapshot,
    MonitoringRun,
    NotificationDelivery,
    Outcome,
    ScheduledJob,
    ScheduledJobExecution,
    TradeTransaction,
    User,
)
from backend.app.monitoring import create_outcome_alert
from backend.app.monitoring_service import execute_drift_snapshot, execute_portfolio_rescreen
from backend.app.schemas import (
    AlertAction,
    AlertRead,
    AlertReassessmentRequest,
    AssessmentDetail,
    DriftSnapshotRead,
    DriftSnapshotRequest,
    MonitoringRunRead,
    MonitoringRunRequest,
    NotificationClaimRequest,
    NotificationDeliveryRead,
    NotificationResultRequest,
    OperationsSummary,
    OutcomeCreate,
    OutcomeRead,
    ScheduledJobExecutionRead,
    ScheduledJobRead,
    ScheduledJobUpsert,
    ScheduledRunRequest,
)


router = APIRouter(tags=["monitoring"])
alert_user = require_roles(
    {"admin", "risk_reviewer", "compliance_reviewer", "model_developer"}
)
monitoring_user = require_roles({"admin", "compliance_reviewer"})
outcome_user = require_roles(
    {"admin", "business_user", "risk_reviewer", "compliance_reviewer"}
)
drift_user = require_roles({"admin", "risk_reviewer", "model_developer"})
admin_user = require_roles({"admin"})
ALERT_STATUSES = {"open", "acknowledged", "resolved", "dismissed"}
REVIEWER_ROLES = {"admin", "risk_reviewer", "compliance_reviewer", "model_developer"}
SCHEDULED_JOB_KEYS = {"portfolio_rescreen", "model_drift"}


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
    monitoring_run = execute_portfolio_rescreen(
        db,
        user=user,
        force=payload.force,
        fuzzy_threshold=payload.fuzzy_threshold,
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
    snapshot = execute_drift_snapshot(
        db,
        user=user,
        window_days=payload.window_days,
        minimum_sample_size=payload.minimum_sample_size,
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


@router.put("/monitoring/schedules/{job_key}", response_model=ScheduledJobRead)
def upsert_monitoring_schedule(
    job_key: str,
    payload: ScheduledJobUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> ScheduledJob:
    if job_key not in SCHEDULED_JOB_KEYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Unsupported scheduled job",
        )
    parameters = (
        {"force": payload.force, "fuzzy_threshold": payload.fuzzy_threshold}
        if job_key == "portfolio_rescreen"
        else {
            "window_days": payload.window_days,
            "minimum_sample_size": payload.minimum_sample_size,
        }
    )
    requested_next_run = payload.next_run_at
    if requested_next_run is not None and requested_next_run.tzinfo is not None:
        requested_next_run = requested_next_run.astimezone(timezone.utc).replace(tzinfo=None)
    scheduled_job = db.scalar(select(ScheduledJob).where(ScheduledJob.job_key == job_key))
    if scheduled_job is None:
        scheduled_job = ScheduledJob(
            job_key=job_key,
            enabled=payload.enabled,
            interval_minutes=payload.interval_minutes,
            parameters_json=json.dumps(parameters, sort_keys=True),
            next_run_at=requested_next_run or datetime.utcnow(),
            updated_by_id=user.id,
        )
        db.add(scheduled_job)
        action = "monitoring.schedule_created"
    else:
        scheduled_job.enabled = payload.enabled
        scheduled_job.interval_minutes = payload.interval_minutes
        scheduled_job.parameters_json = json.dumps(parameters, sort_keys=True)
        if requested_next_run is not None:
            scheduled_job.next_run_at = requested_next_run
        scheduled_job.updated_by_id = user.id
        scheduled_job.version += 1
        action = "monitoring.schedule_updated"
    db.flush()
    record_audit_event(
        db,
        actor_id=user.id,
        action=action,
        object_type="scheduled_job",
        object_id=scheduled_job.id,
        details={
            "job_key": job_key,
            "enabled": payload.enabled,
            "interval_minutes": payload.interval_minutes,
            "parameters": parameters,
        },
    )
    db.commit()
    db.refresh(scheduled_job)
    return scheduled_job


@router.get("/monitoring/schedules", response_model=List[ScheduledJobRead])
def list_monitoring_schedules(
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> List[ScheduledJob]:
    return list(db.scalars(select(ScheduledJob).order_by(ScheduledJob.job_key)))


@router.post(
    "/monitoring/schedules/run-due",
    response_model=List[ScheduledJobExecutionRead],
)
def run_due_monitoring_schedules(
    payload: ScheduledRunRequest,
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> List[ScheduledJobExecution]:
    now = datetime.utcnow()
    scheduled_jobs = list(
        db.scalars(
            select(ScheduledJob)
            .where(ScheduledJob.enabled.is_(True), ScheduledJob.next_run_at <= now)
            .order_by(ScheduledJob.next_run_at)
            .limit(payload.limit)
            .with_for_update(skip_locked=True)
        )
    )
    claimed_jobs = []
    for scheduled_job in scheduled_jobs:
        execution = ScheduledJobExecution(
            scheduled_job_id=scheduled_job.id,
            status="running",
            triggered_by_id=user.id,
        )
        scheduled_job.last_started_at = now
        scheduled_job.last_status = "running"
        scheduled_job.next_run_at = now + timedelta(minutes=scheduled_job.interval_minutes)
        db.add(execution)
        db.flush()
        claimed_jobs.append((scheduled_job.id, execution.id))
    db.commit()

    for scheduled_job_id, execution_id in claimed_jobs:
        scheduled_job = db.get(ScheduledJob, scheduled_job_id)
        execution = db.get(ScheduledJobExecution, execution_id)
        try:
            parameters = json.loads(scheduled_job.parameters_json)
            if scheduled_job.job_key == "portfolio_rescreen":
                result = execute_portfolio_rescreen(
                    db,
                    user=user,
                    force=bool(parameters.get("force", False)),
                    fuzzy_threshold=int(parameters.get("fuzzy_threshold", 85)),
                )
                result_reference = {"monitoring_run_id": result.id}
            elif scheduled_job.job_key == "model_drift":
                result = execute_drift_snapshot(
                    db,
                    user=user,
                    window_days=int(parameters.get("window_days", 90)),
                    minimum_sample_size=int(parameters.get("minimum_sample_size", 20)),
                )
                result_reference = {"drift_snapshot_id": result.id}
            else:
                raise ValueError("Unsupported scheduled job {}".format(scheduled_job.job_key))
            completed_at = datetime.utcnow()
            execution.status = "completed"
            execution.result_reference_json = json.dumps(result_reference, sort_keys=True)
            execution.completed_at = completed_at
            scheduled_job.last_status = "completed"
            scheduled_job.last_completed_at = completed_at
            record_audit_event(
                db,
                actor_id=user.id,
                action="monitoring.scheduled_job_completed",
                object_type="scheduled_job_execution",
                object_id=execution.id,
                details={"job_key": scheduled_job.job_key, **result_reference},
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            execution = db.get(ScheduledJobExecution, execution_id)
            scheduled_job = db.get(ScheduledJob, scheduled_job_id)
            completed_at = datetime.utcnow()
            message = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
            execution.status = "failed"
            execution.error_message = message[:4000]
            execution.completed_at = completed_at
            scheduled_job.last_status = "failed"
            scheduled_job.last_completed_at = completed_at
            record_audit_event(
                db,
                actor_id=user.id,
                action="monitoring.scheduled_job_failed",
                object_type="scheduled_job_execution",
                object_id=execution.id,
                details={"job_key": scheduled_job.job_key, "error": message[:1000]},
            )
            db.commit()
    return [db.get(ScheduledJobExecution, execution_id) for _, execution_id in claimed_jobs]


@router.get(
    "/monitoring/schedule-executions",
    response_model=List[ScheduledJobExecutionRead],
)
def list_schedule_executions(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> List[ScheduledJobExecution]:
    return list(
        db.scalars(
            select(ScheduledJobExecution)
            .order_by(ScheduledJobExecution.started_at.desc())
            .limit(limit)
        )
    )


@router.get("/notifications", response_model=List[NotificationDeliveryRead])
def list_notifications(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(alert_user),
) -> List[NotificationDelivery]:
    if status_filter is not None and status_filter not in {
        "pending",
        "processing",
        "delivered",
        "failed",
    }:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Unsupported notification status",
        )
    query = select(NotificationDelivery)
    if user.role != "admin":
        query = query.where(NotificationDelivery.recipient_role == user.role)
    if status_filter:
        query = query.where(NotificationDelivery.status == status_filter)
    return list(
        db.scalars(query.order_by(NotificationDelivery.created_at.desc()).limit(limit))
    )


@router.post("/notifications/claim", response_model=List[NotificationDeliveryRead])
def claim_notifications(
    payload: NotificationClaimRequest,
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> List[NotificationDelivery]:
    now = datetime.utcnow()
    stale_claim = now - timedelta(minutes=15)
    claimable = list(
        db.scalars(
            select(NotificationDelivery)
            .where(
                or_(
                    and_(
                        NotificationDelivery.status.in_(["pending", "failed"]),
                        NotificationDelivery.available_at <= now,
                    ),
                    and_(
                        NotificationDelivery.status == "processing",
                        NotificationDelivery.claimed_at <= stale_claim,
                    ),
                )
            )
            .order_by(NotificationDelivery.available_at, NotificationDelivery.created_at)
            .limit(payload.limit)
            .with_for_update(skip_locked=True)
        )
    )
    for delivery in claimable:
        delivery.status = "processing"
        delivery.claimed_by = payload.worker_id
        delivery.claimed_at = now
        delivery.attempt_count += 1
    if claimable:
        record_audit_event(
            db,
            actor_id=user.id,
            action="notification.batch_claimed",
            object_type="notification_delivery",
            object_id=None,
            details={
                "worker_id": payload.worker_id,
                "delivery_ids": [item.id for item in claimable],
            },
        )
        db.commit()
    return claimable


@router.post("/notifications/{delivery_id}/result", response_model=NotificationDeliveryRead)
def record_notification_result(
    delivery_id: str,
    payload: NotificationResultRequest,
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> NotificationDelivery:
    delivery = db.get(NotificationDelivery, delivery_id)
    if delivery is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    if delivery.status != "processing" or delivery.claimed_by != payload.worker_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Notification is not claimed by this worker",
        )
    now = datetime.utcnow()
    delivery.status = payload.status
    if payload.status == "delivered":
        delivery.delivered_at = now
        delivery.last_error = None
    else:
        delivery.last_error = payload.error
        backoff_minutes = min(2 ** delivery.attempt_count, 60)
        delivery.available_at = now + timedelta(minutes=backoff_minutes)
    record_audit_event(
        db,
        actor_id=user.id,
        action="notification.{}".format(payload.status),
        object_type="notification_delivery",
        object_id=delivery.id,
        details={
            "worker_id": payload.worker_id,
            "attempt_count": delivery.attempt_count,
            "error": payload.error,
        },
    )
    db.commit()
    db.refresh(delivery)
    return delivery


@router.get("/monitoring/operations-summary", response_model=OperationsSummary)
def get_operations_summary(
    db: Session = Depends(get_db),
    user: User = Depends(alert_user),
) -> OperationsSummary:
    now = datetime.utcnow()
    open_alerts = db.scalar(
        select(func.count(Alert.id)).where(Alert.status.in_(["open", "acknowledged"]))
    ) or 0
    notification_counts = {
        notification_status: db.scalar(
            select(func.count(NotificationDelivery.id)).where(
                NotificationDelivery.status == notification_status
            )
        )
        or 0
        for notification_status in ("pending", "processing", "failed")
    }
    enabled_schedules = db.scalar(
        select(func.count(ScheduledJob.id)).where(ScheduledJob.enabled.is_(True))
    ) or 0
    overdue_schedules = db.scalar(
        select(func.count(ScheduledJob.id)).where(
            ScheduledJob.enabled.is_(True), ScheduledJob.next_run_at < now
        )
    ) or 0
    failed_executions = db.scalar(
        select(func.count(ScheduledJobExecution.id)).where(
            ScheduledJobExecution.status == "failed",
            ScheduledJobExecution.started_at >= now - timedelta(hours=24),
        )
    ) or 0
    latest_rescreen = db.scalar(
        select(MonitoringRun).order_by(MonitoringRun.started_at.desc()).limit(1)
    )
    latest_drift = db.scalar(
        select(DriftSnapshot).order_by(DriftSnapshot.created_at.desc()).limit(1)
    )
    needs_attention = bool(
        overdue_schedules or failed_executions or notification_counts["failed"]
    )
    return OperationsSummary(
        health="attention" if needs_attention else "healthy",
        open_alerts=open_alerts,
        pending_notifications=notification_counts["pending"],
        processing_notifications=notification_counts["processing"],
        failed_notifications=notification_counts["failed"],
        enabled_schedules=enabled_schedules,
        overdue_schedules=overdue_schedules,
        failed_executions_24h=failed_executions,
        latest_rescreen_status=latest_rescreen.status if latest_rescreen else None,
        latest_drift_status=latest_drift.status if latest_drift else None,
    )
