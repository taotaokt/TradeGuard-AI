import json
from decimal import Decimal
from typing import List, Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.audit import record_audit_event
from backend.app.models import Counterparty, CounterpartyDuplicateCandidate, User
from backend.app.screening import normalize_name, similarity_score


def _website_domain(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    parsed = urlparse(value if "://" in value else "https://" + value)
    domain = (parsed.hostname or "").casefold()
    return domain[4:] if domain.startswith("www.") else domain or None


def _names(counterparty: Counterparty) -> List[str]:
    return [counterparty.legal_name] + [alias.name for alias in counterparty.aliases]


def detect_counterparty_duplicates(
    db: Session,
    *,
    counterparty: Counterparty,
    user: User,
) -> List[CounterpartyDuplicateCandidate]:
    existing_records = list(
        db.scalars(
            select(Counterparty)
            .options(selectinload(Counterparty.aliases))
            .where(
                Counterparty.id != counterparty.id,
                Counterparty.status != "archived",
            )
        ).unique()
    )
    candidate_names = _names(counterparty)
    candidate_domain = _website_domain(counterparty.website)
    created: List[CounterpartyDuplicateCandidate] = []

    for existing in existing_records:
        best_score = 0.0
        best_name = existing.legal_name
        for left in candidate_names:
            for right in _names(existing):
                score = similarity_score(normalize_name(left), normalize_name(right))
                if score > best_score:
                    best_score = score
                    best_name = right

        same_jurisdiction = counterparty.jurisdiction == existing.jurisdiction
        same_registration = (
            counterparty.registration_number.casefold()
            == existing.registration_number.casefold()
        )
        existing_domain = _website_domain(existing.website)
        same_domain = bool(candidate_domain and candidate_domain == existing_domain)
        threshold = 88.0 if same_jurisdiction else 94.0
        if not (
            best_score >= threshold
            or (same_domain and best_score >= 70.0)
            or (same_registration and best_score >= 70.0)
        ):
            continue

        signals = []
        signals.append("NAME_EXACT" if best_score == 100.0 else "NAME_FUZZY")
        if same_jurisdiction:
            signals.append("SAME_JURISDICTION")
        if same_registration:
            signals.append("SAME_REGISTRATION_NUMBER")
        if same_domain:
            signals.append("SAME_WEBSITE_DOMAIN")
        pair_key = ":".join(sorted([existing.id, counterparty.id]))
        item = CounterpartyDuplicateCandidate(
            pair_key=pair_key,
            existing_counterparty_id=existing.id,
            possible_duplicate_id=counterparty.id,
            name_similarity=Decimal(str(best_score)),
            matched_name=best_name,
            signals_json=json.dumps(signals, sort_keys=True),
        )
        db.add(item)
        created.append(item)

    if created:
        counterparty.duplicate_status = "review_required"
        db.flush()
        record_audit_event(
            db,
            actor_id=user.id,
            action="counterparty.duplicate_candidates_created",
            object_type="counterparty",
            object_id=counterparty.id,
            details={
                "candidate_ids": [item.id for item in created],
                "candidate_count": len(created),
            },
        )
    return created


def refresh_counterparty_duplicate_status(db: Session, counterparty_id: str) -> None:
    counterparty = db.get(Counterparty, counterparty_id)
    if counterparty is None:
        return
    candidates = list(
        db.scalars(
            select(CounterpartyDuplicateCandidate).where(
                CounterpartyDuplicateCandidate.possible_duplicate_id == counterparty_id
            )
        )
    )
    confirmed = next(
        (item for item in candidates if item.status == "confirmed_duplicate"), None
    )
    if confirmed:
        counterparty.duplicate_status = "confirmed_duplicate"
        counterparty.canonical_counterparty_id = confirmed.existing_counterparty_id
    elif any(item.status == "pending" for item in candidates):
        counterparty.duplicate_status = "review_required"
        counterparty.canonical_counterparty_id = None
    else:
        counterparty.duplicate_status = "clear"
        counterparty.canonical_counterparty_id = None
