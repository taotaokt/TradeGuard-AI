import json
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.audit import record_audit_event
from backend.app.db import get_db
from backend.app.decisioning import assessment_detail_query
from backend.app.deps import get_current_user, require_roles
from backend.app.models import Assessment, DecisionCondition, ReviewCase, RuleVersion, User
from backend.app.schemas import (
    AssessmentDetail,
    ReviewCaseRead,
    ReviewDecision,
    RuleVersionRead,
)
from backend.app.reporting import build_assessment_pdf


router = APIRouter(tags=["assessments"])
reviewer_user = require_roles({"admin", "risk_reviewer", "compliance_reviewer"})
admin_user = require_roles({"admin"})


@router.get("/assessments/{assessment_id}", response_model=AssessmentDetail)
def get_assessment(
    assessment_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Assessment:
    assessment = db.scalar(assessment_detail_query().where(Assessment.id == assessment_id))
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    return assessment


@router.get("/assessments/{assessment_id}/report")
def get_assessment_report(
    assessment_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    assessment = db.scalar(assessment_detail_query().where(Assessment.id == assessment_id))
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    content = build_assessment_pdf(assessment)
    record_audit_event(
        db,
        actor_id=user.id,
        action="assessment.report_downloaded",
        object_type="assessment",
        object_id=assessment.id,
        details={"format": "pdf"},
    )
    db.commit()
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="tradeguard-assessment-{}.pdf"'.format(
                assessment.id
            )
        },
    )


@router.get("/reviews", response_model=List[ReviewCaseRead])
def list_review_queue(
    db: Session = Depends(get_db),
    user: User = Depends(reviewer_user),
) -> List[ReviewCase]:
    query = select(ReviewCase).where(ReviewCase.status == "pending_review")
    if user.role != "admin":
        query = query.where(ReviewCase.required_role == user.role)
    return list(db.scalars(query.order_by(ReviewCase.created_at)))


@router.post("/assessments/{assessment_id}/reviews", response_model=AssessmentDetail)
def decide_review(
    assessment_id: str,
    payload: ReviewDecision,
    db: Session = Depends(get_db),
    user: User = Depends(reviewer_user),
) -> Assessment:
    assessment = db.scalar(assessment_detail_query().where(Assessment.id == assessment_id))
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    review = assessment.review_case
    decision = assessment.decision
    if review is None or decision is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Assessment has no review case")
    if review.status != "pending_review":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Review case is already resolved")
    if user.role != "admin" and user.role != review.required_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This case requires the {} role".format(review.required_role),
        )
    if decision.hard_stop and payload.decision != decision.automatic_recommendation:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A hard-stop decision cannot be overridden; resolve the source issue and reassess",
        )
    if payload.decision == "APPROVE_WITH_CONDITIONS" and not payload.conditions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="At least one condition is required",
        )

    previous = decision.final_recommendation
    decision.final_recommendation = payload.decision
    decision.status = "final"
    decision.rationale = payload.rationale.strip()
    decision.conditions_json = json.dumps(payload.conditions, ensure_ascii=False)
    decision.reviewed_by_id = user.id
    decision.reviewed_at = datetime.utcnow()
    decision.is_override = payload.decision != decision.automatic_recommendation

    if payload.decision == "APPROVE_WITH_CONDITIONS":
        owner_role = payload.condition_owner_role or review.required_role
        due_at = datetime.utcnow() + timedelta(days=payload.condition_due_days)
        for sequence, description in enumerate(payload.conditions, start=1):
            decision.conditions.append(
                DecisionCondition(
                    assessment_id=assessment.id,
                    sequence=sequence,
                    description=description.strip(),
                    owner_role=owner_role,
                    due_at=due_at,
                    created_by_id=user.id,
                )
            )

    review.rationale = payload.rationale.strip()
    review.reviewer_id = user.id
    review.resolved_at = datetime.utcnow()
    review_status = {
        "APPROVE": "approved",
        "APPROVE_WITH_CONDITIONS": "approved_with_conditions",
        "REQUEST_INFORMATION": "information_requested",
        "REJECT": "rejected",
        "COMPLIANCE_HOLD": "stopped_for_compliance",
    }
    review.status = review_status[payload.decision]
    assessment.recommendation = payload.decision
    assessment.status = {
        "APPROVE": "completed",
        "APPROVE_WITH_CONDITIONS": "completed",
        "REQUEST_INFORMATION": "information_required",
        "REJECT": "rejected",
        "COMPLIANCE_HOLD": "compliance_hold",
    }[payload.decision]
    assessment.transaction.status = (
        "assessed" if payload.decision in {"APPROVE", "APPROVE_WITH_CONDITIONS"} else "under_review"
    )
    record_audit_event(
        db,
        actor_id=user.id,
        action="assessment.reviewed",
        object_type="assessment",
        object_id=assessment.id,
        details={
            "from": previous,
            "to": payload.decision,
            "is_override": decision.is_override,
            "rationale": decision.rationale,
            "conditions": payload.conditions,
            "condition_due_days": payload.condition_due_days,
            "condition_owner_role": payload.condition_owner_role or review.required_role,
        },
    )
    db.commit()
    return db.scalar(assessment_detail_query().where(Assessment.id == assessment.id))


@router.get("/admin/rules", response_model=List[RuleVersionRead])
def list_rule_versions(
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> List[RuleVersion]:
    return list(db.scalars(select(RuleVersion).order_by(RuleVersion.created_at.desc())))
