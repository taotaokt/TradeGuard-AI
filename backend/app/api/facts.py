import hashlib
import json
import re
import unicodedata
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.audit import record_audit_event
from backend.app.db import get_db
from backend.app.deps import get_current_user, require_roles
from backend.app.models import Counterparty, CounterpartyFact, SupportingDocument, User
from backend.app.schemas import CounterpartyFactAction, CounterpartyFactCreate, CounterpartyFactRead


router = APIRouter(tags=["counterparty facts"])
write_user = require_roles({"admin", "business_user", "risk_reviewer", "compliance_reviewer"})
review_user = require_roles({"admin", "risk_reviewer", "compliance_reviewer"})


def _normalized_value(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"\s+", " ", normalized)[:500]


def _fact_key(
    *,
    counterparty_id: str,
    fact_type: str,
    normalized_value: str,
    source_url: Optional[str],
    source_document_id: Optional[str],
) -> str:
    canonical = json.dumps(
        {
            "counterparty_id": counterparty_id,
            "fact_type": fact_type,
            "normalized_value": normalized_value,
            "source_url": source_url or "",
            "source_document_id": source_document_id or "",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@router.get(
    "/counterparties/{counterparty_id}/facts",
    response_model=List[CounterpartyFactRead],
)
def list_counterparty_facts(
    counterparty_id: str,
    fact_status: Optional[str] = None,
    verification_status: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(write_user),
) -> List[CounterpartyFact]:
    if db.get(Counterparty, counterparty_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Counterparty not found")
    query = select(CounterpartyFact).where(CounterpartyFact.counterparty_id == counterparty_id)
    if fact_status:
        query = query.where(CounterpartyFact.status == fact_status)
    if verification_status:
        query = query.where(CounterpartyFact.verification_status == verification_status)
    return list(db.scalars(query.order_by(CounterpartyFact.created_at.desc())))


@router.post(
    "/counterparties/{counterparty_id}/facts",
    response_model=CounterpartyFactRead,
    status_code=status.HTTP_201_CREATED,
)
def create_counterparty_fact(
    counterparty_id: str,
    payload: CounterpartyFactCreate,
    db: Session = Depends(get_db),
    user: User = Depends(write_user),
) -> CounterpartyFact:
    counterparty = db.get(Counterparty, counterparty_id)
    if counterparty is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Counterparty not found")
    if counterparty.status == "archived":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Facts cannot be added to an archived counterparty",
        )

    if payload.source_document_id:
        document = db.get(SupportingDocument, payload.source_document_id)
        if (
            document is None
            or document.status != "active"
            or document.counterparty_id != counterparty_id
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Source document must be active evidence for this counterparty",
            )

    normalized_value = _normalized_value(payload.value)
    fact = CounterpartyFact(
        fact_key=_fact_key(
            counterparty_id=counterparty_id,
            fact_type=payload.fact_type,
            normalized_value=normalized_value,
            source_url=payload.source_url,
            source_document_id=payload.source_document_id,
        ),
        counterparty_id=counterparty_id,
        fact_type=payload.fact_type,
        value=payload.value.strip(),
        normalized_value=normalized_value,
        source_url=payload.source_url,
        source_document_id=payload.source_document_id,
        valid_from=payload.valid_from,
        expires_at=payload.expires_at,
        created_by_id=user.id,
    )
    db.add(fact)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This fact and source combination already exists",
        )
    record_audit_event(
        db,
        actor_id=user.id,
        action="counterparty_fact.created",
        object_type="counterparty_fact",
        object_id=fact.id,
        details={
            "counterparty_id": counterparty_id,
            "fact_type": fact.fact_type,
            "has_source_url": bool(fact.source_url),
            "source_document_id": fact.source_document_id,
        },
    )
    db.commit()
    db.refresh(fact)
    return fact


@router.post(
    "/counterparty-facts/{fact_id}/actions",
    response_model=CounterpartyFactRead,
)
def review_counterparty_fact(
    fact_id: str,
    payload: CounterpartyFactAction,
    db: Session = Depends(get_db),
    user: User = Depends(review_user),
) -> CounterpartyFact:
    fact = db.get(CounterpartyFact, fact_id)
    if fact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Counterparty fact not found")
    if fact.version != payload.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Counterparty fact was updated by another user; reload before reviewing",
        )
    if fact.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only active counterparty facts can be reviewed",
        )
    if payload.action in {"verify", "reject"} and fact.verification_status != "unverified":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only unverified facts can be verified or rejected",
        )

    now = datetime.utcnow()
    if payload.action == "retire":
        fact.status = "retired"
    else:
        fact.verification_status = "verified" if payload.action == "verify" else "rejected"
    fact.verification_rationale = payload.rationale.strip()
    fact.verified_by_id = user.id
    fact.verified_at = now
    fact.version += 1
    record_audit_event(
        db,
        actor_id=user.id,
        action="counterparty_fact.{}".format(payload.action),
        object_type="counterparty_fact",
        object_id=fact.id,
        details={
            "counterparty_id": fact.counterparty_id,
            "fact_type": fact.fact_type,
            "rationale": fact.verification_rationale,
            "version": fact.version,
        },
    )
    db.commit()
    db.refresh(fact)
    return fact
