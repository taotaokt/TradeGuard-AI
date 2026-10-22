from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.audit import record_audit_event
from backend.app.db import get_db
from backend.app.deps import require_roles
from backend.app.duplicate_service import refresh_counterparty_duplicate_status
from backend.app.models import CounterpartyDuplicateCandidate, User
from backend.app.schemas import (
    CounterpartyDuplicateCandidateRead,
    CounterpartyDuplicateResolution,
)


router = APIRouter(prefix="/counterparty-duplicates", tags=["counterparty-duplicates"])
duplicate_user = require_roles(
    {"admin", "business_user", "risk_reviewer", "compliance_reviewer"}
)
duplicate_reviewer = require_roles({"admin", "risk_reviewer"})


@router.get("", response_model=List[CounterpartyDuplicateCandidateRead])
def list_duplicate_candidates(
    candidate_status: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(duplicate_user),
) -> List[CounterpartyDuplicateCandidate]:
    query = select(CounterpartyDuplicateCandidate)
    if candidate_status:
        query = query.where(CounterpartyDuplicateCandidate.status == candidate_status)
    return list(
        db.scalars(
            query.order_by(CounterpartyDuplicateCandidate.created_at.desc()).limit(limit)
        )
    )


@router.post(
    "/{candidate_id}/resolve", response_model=CounterpartyDuplicateCandidateRead
)
def resolve_duplicate_candidate(
    candidate_id: str,
    payload: CounterpartyDuplicateResolution,
    db: Session = Depends(get_db),
    user: User = Depends(duplicate_reviewer),
) -> CounterpartyDuplicateCandidate:
    candidate = db.get(CounterpartyDuplicateCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Duplicate candidate not found"
        )
    if candidate.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate candidate is already resolved",
        )
    if candidate.version != payload.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate candidate was updated by another user; reload before saving",
        )

    candidate.status = payload.classification
    candidate.rationale = payload.rationale.strip()
    candidate.reviewed_by_id = user.id
    candidate.reviewed_at = datetime.utcnow()
    candidate.version += 1
    db.flush()
    refresh_counterparty_duplicate_status(db, candidate.possible_duplicate_id)
    record_audit_event(
        db,
        actor_id=user.id,
        action="counterparty_duplicate.resolved",
        object_type="counterparty_duplicate_candidate",
        object_id=candidate.id,
        details={
            "classification": payload.classification,
            "rationale": candidate.rationale,
            "existing_counterparty_id": candidate.existing_counterparty_id,
            "possible_duplicate_id": candidate.possible_duplicate_id,
            "version": candidate.version,
        },
    )
    db.commit()
    db.refresh(candidate)
    return candidate
