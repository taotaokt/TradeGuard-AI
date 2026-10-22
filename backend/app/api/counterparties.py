from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from backend.app.audit import record_audit_event
from backend.app.db import get_db
from backend.app.deps import get_current_user, require_roles
from backend.app.duplicate_service import detect_counterparty_duplicates
from backend.app.models import Counterparty, CounterpartyAlias, RelatedParty, User
from backend.app.schemas import CounterpartyCreate, CounterpartyRead, CounterpartyUpdate


router = APIRouter(prefix="/counterparties", tags=["counterparties"])
write_user = require_roles({"admin", "business_user", "risk_reviewer", "compliance_reviewer"})


def _query_with_children():
    return select(Counterparty).options(
        selectinload(Counterparty.aliases), selectinload(Counterparty.related_parties)
    )


@router.get("", response_model=List[CounterpartyRead])
def list_counterparties(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> List[Counterparty]:
    return list(db.scalars(_query_with_children().order_by(Counterparty.created_at.desc())).unique())


@router.post("", response_model=CounterpartyRead, status_code=status.HTTP_201_CREATED)
def create_counterparty(
    payload: CounterpartyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(write_user),
) -> Counterparty:
    counterparty = Counterparty(
        legal_name=payload.legal_name.strip(),
        jurisdiction=payload.jurisdiction,
        registration_number=payload.registration_number.strip(),
        website=payload.website,
        primary_address=payload.primary_address,
        notes=payload.notes,
        created_by_id=user.id,
    )
    counterparty.aliases = [CounterpartyAlias(**item.model_dump()) for item in payload.aliases]
    counterparty.related_parties = [RelatedParty(**item.model_dump()) for item in payload.related_parties]
    db.add(counterparty)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A counterparty with this jurisdiction and registration number already exists",
        )
    duplicate_candidates = detect_counterparty_duplicates(
        db, counterparty=counterparty, user=user
    )
    record_audit_event(
        db,
        actor_id=user.id,
        action="counterparty.created",
        object_type="counterparty",
        object_id=counterparty.id,
        details={
            "legal_name": counterparty.legal_name,
            "duplicate_candidate_count": len(duplicate_candidates),
        },
    )
    db.commit()
    return db.scalar(_query_with_children().where(Counterparty.id == counterparty.id))


@router.get("/{counterparty_id}", response_model=CounterpartyRead)
def get_counterparty(
    counterparty_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Counterparty:
    counterparty = db.scalar(_query_with_children().where(Counterparty.id == counterparty_id))
    if counterparty is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Counterparty not found")
    return counterparty


@router.patch("/{counterparty_id}", response_model=CounterpartyRead)
def update_counterparty(
    counterparty_id: str,
    payload: CounterpartyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(write_user),
) -> Counterparty:
    counterparty = db.get(Counterparty, counterparty_id)
    if counterparty is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Counterparty not found")
    if counterparty.status == "archived":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Archived counterparties cannot be edited",
        )
    if counterparty.version != payload.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Counterparty was updated by another user; reload before saving",
        )

    changes = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    for field, value in changes.items():
        setattr(counterparty, field, value)
    counterparty.version += 1
    record_audit_event(
        db,
        actor_id=user.id,
        action="counterparty.updated",
        object_type="counterparty",
        object_id=counterparty.id,
        details={"changed_fields": sorted(changes)},
    )
    db.commit()
    return db.scalar(_query_with_children().where(Counterparty.id == counterparty.id))


@router.post("/{counterparty_id}/archive", response_model=CounterpartyRead)
def archive_counterparty(
    counterparty_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(write_user),
) -> Counterparty:
    counterparty = db.get(Counterparty, counterparty_id)
    if counterparty is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Counterparty not found")
    if counterparty.status != "archived":
        counterparty.status = "archived"
        counterparty.version += 1
        record_audit_event(
            db,
            actor_id=user.id,
            action="counterparty.archived",
            object_type="counterparty",
            object_id=counterparty.id,
            details={"retained_for_audit": True},
        )
        db.commit()
    return db.scalar(_query_with_children().where(Counterparty.id == counterparty.id))
