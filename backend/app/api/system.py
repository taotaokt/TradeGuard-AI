from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.deps import require_roles
from backend.app.models import Assessment, AuditEvent, Counterparty, ReviewCase, TradeTransaction, User
from backend.app.schemas import AuditEventRead, DashboardSummary


router = APIRouter(tags=["system"])
audit_user = require_roles({"admin", "risk_reviewer", "compliance_reviewer"})


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(
    db: Session = Depends(get_db), user: User = Depends(audit_user)
) -> DashboardSummary:
    return DashboardSummary(
        counterparties=db.scalar(select(func.count(Counterparty.id))) or 0,
        transactions=db.scalar(select(func.count(TradeTransaction.id))) or 0,
        pending_reviews=db.scalar(
            select(func.count(ReviewCase.id)).where(ReviewCase.status == "pending_review")
        ) or 0,
        compliance_holds=db.scalar(
            select(func.count(Assessment.id)).where(Assessment.status == "compliance_hold")
        ) or 0,
    )


@router.get("/audit-events", response_model=List[AuditEventRead])
def list_audit_events(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(audit_user),
) -> List[AuditEvent]:
    return list(db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)))
