import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.audit import record_audit_event
from backend.app.models import (
    Counterparty,
    DataQualityIssue,
    DataQualityScan,
    Outcome,
    ScreeningList,
    ScreeningListVersion,
    ScreeningRun,
    SupportingDocument,
    TradeTransaction,
    User,
)
from backend.app.schemas import DataQualityScanRequest


RULESET_VERSION = "dq-v1"


@dataclass(frozen=True)
class Finding:
    entity_type: str
    entity_id: str
    code: str
    severity: str
    required_role: str
    title: str
    details: Dict[str, Any]

    @property
    def key(self) -> str:
        return "{}:{}:{}".format(self.code, self.entity_type, self.entity_id)


def _findings(db: Session, payload: DataQualityScanRequest, now: datetime) -> List[Finding]:
    findings: List[Finding] = []
    counterparties = list(
        db.scalars(select(Counterparty).where(Counterparty.status != "archived"))
    )
    counterparty_evidence = set(
        db.scalars(
            select(SupportingDocument.counterparty_id).where(
                SupportingDocument.counterparty_id.is_not(None),
                SupportingDocument.status == "active",
            )
        )
    )
    latest_screening: Dict[str, ScreeningRun] = {}
    for run in db.scalars(select(ScreeningRun).order_by(ScreeningRun.created_at.desc())):
        latest_screening.setdefault(run.counterparty_id, run)

    screening_cutoff = now - timedelta(days=payload.screening_stale_days)
    for counterparty in counterparties:
        details = {
            "legal_name": counterparty.legal_name,
            "jurisdiction": counterparty.jurisdiction,
        }
        if counterparty.id not in counterparty_evidence:
            findings.append(
                Finding(
                    "counterparty",
                    counterparty.id,
                    "DQ_COUNTERPARTY_NO_EVIDENCE",
                    "medium",
                    "business_user",
                    "Counterparty has no active evidence",
                    details,
                )
            )
        latest = latest_screening.get(counterparty.id)
        if latest is None:
            findings.append(
                Finding(
                    "counterparty",
                    counterparty.id,
                    "DQ_COUNTERPARTY_NEVER_SCREENED",
                    "high",
                    "compliance_reviewer",
                    "Counterparty has never been screened",
                    details,
                )
            )
        elif latest.created_at < screening_cutoff:
            findings.append(
                Finding(
                    "counterparty",
                    counterparty.id,
                    "DQ_COUNTERPARTY_SCREENING_STALE",
                    "high",
                    "compliance_reviewer",
                    "Counterparty screening is stale",
                    {
                        **details,
                        "last_screened_at": latest.created_at.isoformat(),
                        "stale_after_days": payload.screening_stale_days,
                    },
                )
            )

    list_cutoff = now - timedelta(days=payload.list_stale_days)
    for screening_list in db.scalars(select(ScreeningList)):
        details = {"code": screening_list.code, "name": screening_list.name}
        if not screening_list.active_version_id:
            findings.append(
                Finding(
                    "screening_list",
                    screening_list.id,
                    "DQ_SCREENING_LIST_NO_ACTIVE_VERSION",
                    "critical",
                    "compliance_reviewer",
                    "Screening list has no active version",
                    details,
                )
            )
            continue
        version = db.get(ScreeningListVersion, screening_list.active_version_id)
        if version is None or version.effective_at < list_cutoff:
            findings.append(
                Finding(
                    "screening_list",
                    screening_list.id,
                    "DQ_SCREENING_LIST_STALE",
                    "critical",
                    "compliance_reviewer",
                    "Active screening list version is stale",
                    {
                        **details,
                        "active_version": version.version if version else None,
                        "effective_at": version.effective_at.isoformat() if version else None,
                        "stale_after_days": payload.list_stale_days,
                    },
                )
            )

    transactions = list(
        db.scalars(select(TradeTransaction).where(TradeTransaction.status != "completed"))
    )
    transaction_evidence = set(
        db.scalars(
            select(SupportingDocument.transaction_id).where(
                SupportingDocument.transaction_id.is_not(None),
                SupportingDocument.status == "active",
            )
        )
    )
    transaction_outcomes = set(db.scalars(select(Outcome.transaction_id)))
    for transaction in transactions:
        details = {
            "reference": transaction.reference,
            "status": transaction.status,
            "currency": transaction.currency,
            "amount": str(transaction.amount),
        }
        if not transaction.end_use or not transaction.end_use.strip():
            findings.append(
                Finding(
                    "transaction",
                    transaction.id,
                    "DQ_TRANSACTION_MISSING_END_USE",
                    "high",
                    "business_user",
                    "Transaction is missing an end-use statement",
                    details,
                )
            )
        if transaction.id not in transaction_evidence:
            findings.append(
                Finding(
                    "transaction",
                    transaction.id,
                    "DQ_TRANSACTION_NO_EVIDENCE",
                    "medium",
                    "risk_reviewer",
                    "Transaction has no active supporting evidence",
                    details,
                )
            )
        outcome_due_at = transaction.created_at + timedelta(
            days=transaction.payment_terms_days + payload.outcome_grace_days
        )
        if transaction.id not in transaction_outcomes and outcome_due_at < now:
            findings.append(
                Finding(
                    "transaction",
                    transaction.id,
                    "DQ_TRANSACTION_OUTCOME_OVERDUE",
                    "high",
                    "risk_reviewer",
                    "Transaction outcome is overdue",
                    {
                        **details,
                        "outcome_due_at": outcome_due_at.isoformat(),
                        "grace_days": payload.outcome_grace_days,
                    },
                )
            )
    return findings


def execute_data_quality_scan(
    db: Session,
    *,
    payload: DataQualityScanRequest,
    user: User,
) -> DataQualityScan:
    now = datetime.utcnow()
    scan = DataQualityScan(
        status="running",
        ruleset_version=RULESET_VERSION,
        parameters_json=json.dumps(payload.model_dump(), sort_keys=True),
        initiated_by_id=user.id,
        started_at=now,
    )
    db.add(scan)
    db.flush()

    findings = _findings(db, payload, now)
    existing = {
        issue.issue_key: issue for issue in db.scalars(select(DataQualityIssue))
    }
    seen_keys = set()
    counts = {
        "findings": len(findings),
        "new": 0,
        "recurring": 0,
        "reopened": 0,
        "auto_resolved": 0,
    }

    for finding in findings:
        seen_keys.add(finding.key)
        issue = existing.get(finding.key)
        if issue is None:
            issue = DataQualityIssue(
                issue_key=finding.key,
                detected_by_scan_id=scan.id,
                entity_type=finding.entity_type,
                entity_id=finding.entity_id,
                code=finding.code,
                severity=finding.severity,
                required_role=finding.required_role,
                title=finding.title,
                details_json=json.dumps(finding.details, sort_keys=True),
                status="open",
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(issue)
            counts["new"] += 1
            continue

        issue.detected_by_scan_id = scan.id
        issue.severity = finding.severity
        issue.required_role = finding.required_role
        issue.title = finding.title
        issue.details_json = json.dumps(finding.details, sort_keys=True)
        issue.last_seen_at = now
        issue.version += 1
        if issue.status == "resolved":
            issue.status = "open"
            issue.resolution_rationale = None
            issue.resolved_by_id = None
            issue.resolved_at = None
            counts["reopened"] += 1
        else:
            counts["recurring"] += 1

    for issue in existing.values():
        if issue.issue_key not in seen_keys and issue.status in {"open", "acknowledged"}:
            issue.status = "resolved"
            issue.resolution_rationale = (
                "Automatically resolved because the condition was not detected in scan {}."
            ).format(scan.id)
            issue.resolved_by_id = user.id
            issue.resolved_at = now
            issue.version += 1
            counts["auto_resolved"] += 1

    db.flush()
    counts["open"] = db.scalar(
        select(func.count()).select_from(DataQualityIssue).where(
            DataQualityIssue.status.in_({"open", "acknowledged"})
        )
    ) or 0
    scan.status = "completed"
    scan.counters_json = json.dumps(counts, sort_keys=True)
    scan.completed_at = now
    record_audit_event(
        db,
        actor_id=user.id,
        action="data_quality.scan_completed",
        object_type="data_quality_scan",
        object_id=scan.id,
        details={"ruleset_version": RULESET_VERSION, **counts},
    )
    return scan
