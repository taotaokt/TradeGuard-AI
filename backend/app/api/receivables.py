from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from backend.app.audit import record_audit_event
from backend.app.db import get_db
from backend.app.deps import require_roles
from backend.app.models import (
    Assessment,
    Outcome,
    ReceivablePayment,
    TradeReceivable,
    TradeTransaction,
    User,
)
from backend.app.monitoring import create_outcome_alert
from backend.app.schemas import (
    ReceivablePaymentCreate,
    TradeReceivableCreate,
    TradeReceivableRead,
)


router = APIRouter(tags=["receivables"])
receivable_user = require_roles(
    {"admin", "business_user", "risk_reviewer", "compliance_reviewer"}
)


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _receivable_query():
    return select(TradeReceivable).options(selectinload(TradeReceivable.payments))


@router.get("/receivables", response_model=List[TradeReceivableRead])
def list_receivables(
    receivable_status: Optional[str] = Query(default=None, alias="status"),
    counterparty_id: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(receivable_user),
) -> List[TradeReceivable]:
    query = _receivable_query()
    if receivable_status:
        query = query.where(TradeReceivable.status == receivable_status)
    if counterparty_id:
        query = query.where(TradeReceivable.counterparty_id == counterparty_id)
    return list(
        db.scalars(query.order_by(TradeReceivable.due_at, TradeReceivable.created_at).limit(limit))
        .unique()
    )


@router.get(
    "/transactions/{transaction_id}/receivable",
    response_model=TradeReceivableRead,
)
def get_transaction_receivable(
    transaction_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(receivable_user),
) -> TradeReceivable:
    receivable = db.scalar(
        _receivable_query().where(TradeReceivable.transaction_id == transaction_id)
    )
    if receivable is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receivable not found")
    return receivable


@router.post(
    "/transactions/{transaction_id}/receivable",
    response_model=TradeReceivableRead,
    status_code=status.HTTP_201_CREATED,
)
def create_transaction_receivable(
    transaction_id: str,
    payload: TradeReceivableCreate,
    db: Session = Depends(get_db),
    user: User = Depends(receivable_user),
) -> TradeReceivable:
    transaction = db.get(TradeTransaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    if transaction.status in {"completed", "stopped"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A receivable cannot be opened for a completed or stopped transaction",
        )
    linked_counterparties = {
        party.counterparty_id for party in transaction.parties if party.counterparty_id
    }
    if payload.counterparty_id not in linked_counterparties:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="counterparty_id must be linked to the transaction",
        )
    if payload.invoice_amount > transaction.amount:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invoice_amount cannot exceed the transaction amount",
        )
    issued_at = _utc_naive(payload.issued_at)
    due_at = _utc_naive(payload.due_at)
    if due_at <= issued_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="due_at must be later than issued_at",
        )

    receivable = TradeReceivable(
        transaction_id=transaction.id,
        counterparty_id=payload.counterparty_id,
        invoice_reference=payload.invoice_reference,
        invoice_amount=payload.invoice_amount,
        outstanding_amount=payload.invoice_amount,
        currency=transaction.currency,
        issued_at=issued_at,
        due_at=due_at,
        notes=payload.notes,
        created_by_id=user.id,
    )
    db.add(receivable)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A receivable already exists for this transaction or invoice reference",
        )
    record_audit_event(
        db,
        actor_id=user.id,
        action="receivable.created",
        object_type="trade_receivable",
        object_id=receivable.id,
        details={
            "transaction_id": transaction.id,
            "counterparty_id": receivable.counterparty_id,
            "invoice_reference": receivable.invoice_reference,
            "invoice_amount": str(receivable.invoice_amount),
            "currency": receivable.currency,
            "due_at": receivable.due_at.isoformat(),
        },
    )
    db.commit()
    return db.scalar(_receivable_query().where(TradeReceivable.id == receivable.id))


@router.post(
    "/receivables/{receivable_id}/payments",
    response_model=TradeReceivableRead,
)
def record_receivable_payment(
    receivable_id: str,
    payload: ReceivablePaymentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(receivable_user),
) -> TradeReceivable:
    receivable = db.scalar(
        _receivable_query().where(TradeReceivable.id == receivable_id)
    )
    if receivable is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receivable not found")
    if receivable.version != payload.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Receivable was updated by another user; reload before recording payment",
        )
    if receivable.status == "paid":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A paid receivable cannot accept another payment",
        )
    if db.scalar(
        select(ReceivablePayment).where(
            ReceivablePayment.payment_reference == payload.payment_reference
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="payment_reference has already been recorded",
        )
    if payload.amount > receivable.outstanding_amount:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Payment cannot exceed the outstanding receivable balance",
        )
    received_at = _utc_naive(payload.received_at or datetime.utcnow())
    if received_at < receivable.issued_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Payment cannot predate the invoice issue time",
        )

    payment = ReceivablePayment(
        payment_reference=payload.payment_reference,
        amount=payload.amount,
        received_at=received_at,
        notes=payload.notes,
        recorded_by_id=user.id,
    )
    receivable.payments.append(payment)
    receivable.outstanding_amount = (
        Decimal(receivable.outstanding_amount) - payload.amount
    ).quantize(Decimal("0.01"))
    receivable.status = "paid" if receivable.outstanding_amount == 0 else "partially_paid"
    receivable.version += 1

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="payment_reference has already been recorded",
        )

    transaction = db.get(TradeTransaction, receivable.transaction_id)
    outcome_id = None
    if receivable.status == "paid" and transaction is not None:
        transaction.status = "completed"
        existing_outcome = db.scalar(
            select(Outcome).where(Outcome.transaction_id == transaction.id)
        )
        if existing_outcome is None:
            latest_assessment_id = db.scalar(
                select(Assessment.id)
                .where(Assessment.transaction_id == transaction.id)
                .order_by(Assessment.version.desc())
                .limit(1)
            )
            days_past_due = max(0, (received_at.date() - receivable.due_at.date()).days)
            outcome = Outcome(
                transaction_id=transaction.id,
                assessment_id=latest_assessment_id,
                outcome_type="delayed" if days_past_due else "paid_on_time",
                due_at=receivable.due_at,
                settled_at=received_at,
                days_past_due=days_past_due,
                notes="Generated from the completed receivable payment ledger.",
                reported_by_id=user.id,
            )
            db.add(outcome)
            db.flush()
            outcome_id = outcome.id
            if days_past_due >= 30:
                create_outcome_alert(db, outcome=outcome, transaction=transaction, actor=user)

    db.flush()
    record_audit_event(
        db,
        actor_id=user.id,
        action="receivable.payment_recorded",
        object_type="trade_receivable",
        object_id=receivable.id,
        details={
            "payment_id": payment.id,
            "payment_reference": payment.payment_reference,
            "amount": str(payment.amount),
            "outstanding_amount": str(receivable.outstanding_amount),
            "status": receivable.status,
            "outcome_id": outcome_id,
            "version": receivable.version,
        },
    )
    db.commit()
    return db.scalar(_receivable_query().where(TradeReceivable.id == receivable.id))
