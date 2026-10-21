from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from backend.app.audit import record_audit_event
from backend.app.db import get_db
from backend.app.decisioning import assessment_detail_query, orchestrate_assessment
from backend.app.deps import get_current_user, require_roles
from backend.app.models import Assessment, TradeTransaction, TransactionParty, User
from backend.app.schemas import AssessmentDetail, TransactionCreate, TransactionRead, TransactionUpdate


router = APIRouter(prefix="/transactions", tags=["transactions"])
write_user = require_roles({"admin", "business_user", "risk_reviewer", "compliance_reviewer"})


def _query_with_parties():
    return select(TradeTransaction).options(selectinload(TradeTransaction.parties))


@router.get("", response_model=List[TransactionRead])
def list_transactions(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> List[TradeTransaction]:
    return list(db.scalars(_query_with_parties().order_by(TradeTransaction.created_at.desc())).unique())


@router.post("", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(write_user),
) -> TradeTransaction:
    values = payload.model_dump(exclude={"parties"})
    transaction = TradeTransaction(**values, created_by_id=user.id)
    transaction.parties = [TransactionParty(**item.model_dump()) for item in payload.parties]
    db.add(transaction)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transaction reference already exists")
    record_audit_event(
        db,
        actor_id=user.id,
        action="transaction.created",
        object_type="transaction",
        object_id=transaction.id,
        details={"reference": transaction.reference, "amount": str(transaction.amount)},
    )
    db.commit()
    return db.scalar(_query_with_parties().where(TradeTransaction.id == transaction.id))


@router.get("/{transaction_id}", response_model=TransactionRead)
def get_transaction(
    transaction_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TradeTransaction:
    transaction = db.scalar(_query_with_parties().where(TradeTransaction.id == transaction_id))
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return transaction


@router.patch("/{transaction_id}", response_model=TransactionRead)
def update_transaction(
    transaction_id: str,
    payload: TransactionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(write_user),
) -> TradeTransaction:
    transaction = db.get(TradeTransaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    if transaction.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Submitted transactions cannot be edited; create a reassessment instead",
        )
    if transaction.version != payload.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Transaction was updated by another user; reload before saving",
        )

    changes = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    for field, value in changes.items():
        setattr(transaction, field, value)
    transaction.version += 1
    record_audit_event(
        db,
        actor_id=user.id,
        action="transaction.updated",
        object_type="transaction",
        object_id=transaction.id,
        details={"changed_fields": sorted(changes), "version": transaction.version},
    )
    db.commit()
    return db.scalar(_query_with_parties().where(TradeTransaction.id == transaction.id))


@router.post(
    "/{transaction_id}/assessments", response_model=AssessmentDetail, status_code=status.HTTP_201_CREATED
)
def submit_assessment(
    transaction_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(write_user),
) -> Assessment:
    transaction = db.scalar(_query_with_parties().where(TradeTransaction.id == transaction_id))
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    roles = {party.role for party in transaction.parties}
    missing = []
    if not roles.intersection({"buyer", "seller", "counterparty"}):
        missing.append("buyer, seller, or counterparty")
    if not transaction.end_use:
        missing.append("end_use")
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": "Critical information is missing", "fields": missing},
        )

    assessment = orchestrate_assessment(db, transaction, user)
    record_audit_event(
        db,
        actor_id=user.id,
        action="assessment.submitted",
        object_type="assessment",
        object_id=assessment.id,
        details={
            "transaction_id": transaction.id,
            "version": assessment.version,
            "recommendation": assessment.recommendation,
            "rule_version": assessment.rule_version,
        },
    )
    db.commit()
    return db.scalar(assessment_detail_query().where(Assessment.id == assessment.id))
