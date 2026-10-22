from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.audit import record_audit_event
from backend.app.db import get_db
from backend.app.deps import require_roles
from backend.app.models import (
    Assessment,
    DecisionCondition,
    SupportingDocument,
    User,
)
from backend.app.schemas import DecisionConditionAction, DecisionConditionRead


router = APIRouter(prefix="/conditions", tags=["conditions"])
condition_user = require_roles(
    {"admin", "business_user", "risk_reviewer", "compliance_reviewer"}
)


def _can_manage(condition: DecisionCondition, user: User) -> bool:
    return (
        user.role == "admin"
        or user.role == condition.owner_role
        or condition.assigned_to_id == user.id
    )


@router.get("", response_model=List[DecisionConditionRead])
def list_conditions(
    condition_status: Optional[str] = Query(default=None, alias="status"),
    assessment_id: Optional[str] = None,
    assigned_to_me: bool = False,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(condition_user),
) -> List[DecisionCondition]:
    query = select(DecisionCondition)
    if user.role != "admin":
        query = query.where(
            or_(
                DecisionCondition.owner_role == user.role,
                DecisionCondition.assigned_to_id == user.id,
            )
        )
    if condition_status:
        query = query.where(DecisionCondition.status == condition_status)
    if assessment_id:
        query = query.where(DecisionCondition.assessment_id == assessment_id)
    if assigned_to_me:
        query = query.where(DecisionCondition.assigned_to_id == user.id)
    return list(
        db.scalars(
            query.order_by(DecisionCondition.due_at, DecisionCondition.created_at).limit(limit)
        )
    )


@router.post("/{condition_id}/actions", response_model=DecisionConditionRead)
def act_on_condition(
    condition_id: str,
    payload: DecisionConditionAction,
    db: Session = Depends(get_db),
    user: User = Depends(condition_user),
) -> DecisionCondition:
    condition = db.get(DecisionCondition, condition_id)
    if condition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Condition not found")
    if not _can_manage(condition, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This condition belongs to the {} role".format(condition.owner_role),
        )
    if condition.version != payload.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Condition was updated by another user; reload before saving",
        )

    previous_status = condition.status
    if payload.action == "assign":
        if condition.status != "open":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only open conditions can be assigned",
            )
        if not payload.assignee_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="assignee_id is required for assign",
            )
        assignee = db.get(User, payload.assignee_id)
        if assignee is None or not assignee.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Assignee must be an active user",
            )
        if assignee.role not in {"admin", condition.owner_role}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Assignee does not have the condition owner role",
            )
        condition.assigned_to_id = assignee.id
    elif payload.action == "fulfill":
        if condition.status != "open":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only open conditions can be fulfilled",
            )
        if not payload.evidence_document_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="evidence_document_id is required to fulfill a condition",
            )
        evidence = db.get(SupportingDocument, payload.evidence_document_id)
        assessment = db.get(Assessment, condition.assessment_id)
        if (
            evidence is None
            or evidence.status != "active"
            or evidence.transaction_id != assessment.transaction_id
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Evidence must be an active document for the assessed transaction",
            )
        condition.status = "fulfilled"
        condition.evidence_document_id = evidence.id
        condition.completion_rationale = payload.rationale.strip()
        condition.completed_by_id = user.id
        condition.completed_at = datetime.utcnow()
    elif payload.action == "waive":
        if condition.status != "open":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only open conditions can be waived",
            )
        if user.role not in {"admin", condition.owner_role}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the owner role can waive a condition",
            )
        condition.status = "waived"
        condition.completion_rationale = payload.rationale.strip()
        condition.completed_by_id = user.id
        condition.completed_at = datetime.utcnow()
    else:
        if condition.status not in {"fulfilled", "waived"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only closed conditions can be reopened",
            )
        condition.status = "open"
        condition.evidence_document_id = None
        condition.completion_rationale = None
        condition.completed_by_id = None
        condition.completed_at = None

    condition.version += 1
    record_audit_event(
        db,
        actor_id=user.id,
        action="decision_condition.{}".format(payload.action),
        object_type="decision_condition",
        object_id=condition.id,
        details={
            "assessment_id": condition.assessment_id,
            "from_status": previous_status,
            "to_status": condition.status,
            "rationale": payload.rationale.strip(),
            "assignee_id": payload.assignee_id,
            "evidence_document_id": payload.evidence_document_id,
            "version": condition.version,
        },
    )
    db.commit()
    db.refresh(condition)
    return condition
