from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.audit import record_audit_event
from backend.app.db import get_db
from backend.app.decisioning import assessment_detail_query, orchestrate_assessment
from backend.app.deps import require_roles
from backend.app.models import Alert, Assessment, TradeTransaction, User
from backend.app.schemas import (
    AlertAction,
    AlertRead,
    AlertReassessmentRequest,
    AssessmentDetail,
)


router = APIRouter(tags=["monitoring"])
alert_user = require_roles({"admin", "risk_reviewer", "compliance_reviewer"})
ALERT_STATUSES = {"open", "acknowledged", "resolved", "dismissed"}
REVIEWER_ROLES = {"admin", "risk_reviewer", "compliance_reviewer"}


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
