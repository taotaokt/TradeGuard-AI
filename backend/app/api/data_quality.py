from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.audit import record_audit_event
from backend.app.data_quality_service import execute_data_quality_scan
from backend.app.db import get_db
from backend.app.deps import require_roles
from backend.app.models import DataQualityIssue, DataQualityScan, User
from backend.app.schemas import (
    DataQualityIssueAction,
    DataQualityIssueRead,
    DataQualityScanRead,
    DataQualityScanRequest,
)


router = APIRouter(prefix="/data-quality", tags=["data-quality"])
data_quality_user = require_roles(
    {"admin", "business_user", "risk_reviewer", "compliance_reviewer"}
)
scan_user = require_roles({"admin", "risk_reviewer", "compliance_reviewer"})


@router.post(
    "/scans", response_model=DataQualityScanRead, status_code=status.HTTP_201_CREATED
)
def run_scan(
    payload: DataQualityScanRequest,
    db: Session = Depends(get_db),
    user: User = Depends(scan_user),
) -> DataQualityScan:
    scan = execute_data_quality_scan(db, payload=payload, user=user)
    db.commit()
    db.refresh(scan)
    return scan


@router.get("/scans", response_model=List[DataQualityScanRead])
def list_scans(
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(data_quality_user),
) -> List[DataQualityScan]:
    return list(
        db.scalars(
            select(DataQualityScan).order_by(DataQualityScan.started_at.desc()).limit(limit)
        )
    )


@router.get("/issues", response_model=List[DataQualityIssueRead])
def list_issues(
    issue_status: Optional[str] = Query(default=None, alias="status"),
    code: Optional[str] = None,
    severity: Optional[str] = None,
    assigned_to_me: bool = False,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(data_quality_user),
) -> List[DataQualityIssue]:
    query = select(DataQualityIssue)
    if user.role != "admin":
        query = query.where(DataQualityIssue.required_role == user.role)
    if issue_status:
        query = query.where(DataQualityIssue.status == issue_status)
    if code:
        query = query.where(DataQualityIssue.code == code)
    if severity:
        query = query.where(DataQualityIssue.severity == severity)
    if assigned_to_me:
        query = query.where(DataQualityIssue.assigned_to_id == user.id)
    return list(
        db.scalars(query.order_by(DataQualityIssue.last_seen_at.desc()).limit(limit))
    )


@router.post("/issues/{issue_id}/actions", response_model=DataQualityIssueRead)
def act_on_issue(
    issue_id: str,
    payload: DataQualityIssueAction,
    db: Session = Depends(get_db),
    user: User = Depends(data_quality_user),
) -> DataQualityIssue:
    issue = db.get(DataQualityIssue, issue_id)
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    if user.role != "admin" and issue.required_role != user.role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This issue requires the {} role".format(issue.required_role),
        )
    if issue.status in {"resolved", "dismissed"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Closed issues cannot be changed",
        )

    now = datetime.utcnow()
    if payload.action == "assign":
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
        if assignee.role not in {"admin", issue.required_role}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Assignee does not have the required role",
            )
        issue.assigned_to_id = assignee.id
    elif payload.action == "acknowledge":
        issue.status = "acknowledged"
        issue.assigned_to_id = issue.assigned_to_id or user.id
    else:
        issue.status = "dismissed" if payload.action == "dismiss" else "resolved"
        issue.resolution_rationale = payload.rationale.strip()
        issue.resolved_by_id = user.id
        issue.resolved_at = now

    issue.version += 1
    record_audit_event(
        db,
        actor_id=user.id,
        action="data_quality.issue_{}".format(payload.action),
        object_type="data_quality_issue",
        object_id=issue.id,
        details={
            "issue_key": issue.issue_key,
            "rationale": payload.rationale.strip(),
            "assignee_id": payload.assignee_id,
            "version": issue.version,
        },
    )
    db.commit()
    db.refresh(issue)
    return issue
