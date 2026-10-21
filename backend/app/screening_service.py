import json
from decimal import Decimal
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.audit import record_audit_event
from backend.app.models import (
    Counterparty,
    ScreeningCandidate,
    ScreeningEntry,
    ScreeningList,
    ScreeningRun,
    User,
)
from backend.app.monitoring import create_screening_alert
from backend.app.screening import best_name_match, normalize_name


def run_counterparty_screening(
    db: Session,
    *,
    counterparty: Counterparty,
    active_lists: List[ScreeningList],
    user: User,
    fuzzy_threshold: int,
) -> ScreeningRun:
    run = ScreeningRun(
        counterparty_id=counterparty.id,
        fuzzy_threshold=fuzzy_threshold,
        screened_by_id=user.id,
    )
    db.add(run)
    db.flush()

    subjects = [
        (
            [counterparty.legal_name] + [alias.name for alias in counterparty.aliases],
            None,
            counterparty.jurisdiction,
            counterparty.registration_number,
        )
    ]
    subjects.extend(
        ([party.name], party.id, party.country, party.identifier)
        for party in counterparty.related_parties
    )

    for source in active_lists:
        entries = list(
            db.scalars(
                select(ScreeningEntry).where(
                    ScreeningEntry.list_version_id == source.active_version_id
                )
            )
        )
        for screened_names, related_party_id, screened_country, screened_identifier in subjects:
            for entry in entries:
                aliases = json.loads(entry.aliases_json)
                matched_name = None
                screened_name = screened_names[0]
                score = 0.0
                match_type = "fuzzy"
                for subject_name in screened_names:
                    candidate_name, candidate_score, candidate_type = best_name_match(
                        subject_name, [entry.primary_name] + aliases
                    )
                    if candidate_score > score:
                        screened_name = subject_name
                        matched_name = candidate_name
                        score = candidate_score
                        match_type = candidate_type
                if matched_name is None or score < fuzzy_threshold:
                    continue
                run.candidates.append(
                    ScreeningCandidate(
                        counterparty_id=counterparty.id,
                        related_party_id=related_party_id,
                        list_version_id=entry.list_version_id,
                        screening_entry_id=entry.id,
                        source_list_code=source.code,
                        screened_name=screened_name,
                        normalized_screened_name=normalize_name(screened_name),
                        screened_country=screened_country,
                        screened_identifier=screened_identifier,
                        matched_name=matched_name,
                        match_type=match_type,
                        score=Decimal(str(score)),
                        program=entry.program,
                        matched_country=entry.country,
                        matched_address=entry.address,
                        matched_identifiers_json=entry.identifiers_json,
                    )
                )

    db.flush()
    if run.candidates:
        create_screening_alert(db, run=run, candidates=run.candidates, actor=user)
    has_confirmed_match = db.scalar(
        select(ScreeningCandidate.id)
        .where(
            ScreeningCandidate.counterparty_id == counterparty.id,
            ScreeningCandidate.status == "confirmed",
        )
        .limit(1)
    )
    if has_confirmed_match:
        counterparty.status = "compliance_hold"
    else:
        counterparty.status = "screening_review" if run.candidates else "active"
    counterparty.version += 1
    record_audit_event(
        db,
        actor_id=user.id,
        action="counterparty.screened",
        object_type="screening_run",
        object_id=run.id,
        details={
            "counterparty_id": counterparty.id,
            "candidate_count": len(run.candidates),
            "fuzzy_threshold": fuzzy_threshold,
            "list_versions": [item.active_version_id for item in active_lists],
            "counterparty_status": counterparty.status,
        },
    )
    return run
