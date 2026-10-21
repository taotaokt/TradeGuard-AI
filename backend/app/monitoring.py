import json
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.audit import record_audit_event
from backend.app.models import Alert, ScreeningCandidate, ScreeningRun, TransactionParty, User


def create_screening_alert(
    db: Session,
    *,
    run: ScreeningRun,
    candidates: Iterable[ScreeningCandidate],
    actor: User,
) -> Alert:
    candidate_list = list(candidates)
    exact_matches = sum(item.match_type == "exact" for item in candidate_list)
    affected_transaction_ids = list(
        db.scalars(
            select(TransactionParty.transaction_id)
            .where(TransactionParty.counterparty_id == run.counterparty_id)
            .distinct()
        )
    )
    alert = Alert(
        alert_type="screening_match",
        severity="high" if exact_matches else "medium",
        required_role="compliance_reviewer",
        title="New screening candidates require review",
        description=(
            "Screening produced {} candidate match(es), including {} exact match(es). "
            "A compliance reviewer must classify the candidates."
        ).format(len(candidate_list), exact_matches),
        counterparty_id=run.counterparty_id,
        screening_run_id=run.id,
        created_by_id=actor.id,
        source_reference_json=json.dumps(
            {
                "candidate_ids": [item.id for item in candidate_list],
                "affected_transaction_ids": affected_transaction_ids,
                "list_version_ids": sorted({item.list_version_id for item in candidate_list}),
            },
            sort_keys=True,
        ),
    )
    db.add(alert)
    db.flush()
    record_audit_event(
        db,
        actor_id=actor.id,
        action="alert.created",
        object_type="alert",
        object_id=alert.id,
        details={
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "counterparty_id": run.counterparty_id,
            "screening_run_id": run.id,
            "candidate_count": len(candidate_list),
        },
    )
    return alert
