from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.audit import record_audit_event
from backend.app.db import get_db
from backend.app.deps import require_roles
from backend.app.models import Counterparty, CounterpartyCreditPolicy, User
from backend.app.schemas import (
    CounterpartyCreditPolicyAction,
    CounterpartyCreditPolicyCreate,
    CounterpartyCreditPolicyRead,
)


router = APIRouter(tags=["credit policies"])
policy_reader = require_roles(
    {"admin", "business_user", "risk_reviewer", "compliance_reviewer"}
)
policy_reviewer = require_roles({"admin", "risk_reviewer"})


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.get(
    "/counterparties/{counterparty_id}/credit-policies",
    response_model=List[CounterpartyCreditPolicyRead],
)
def list_credit_policies(
    counterparty_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(policy_reader),
) -> List[CounterpartyCreditPolicy]:
    if db.get(Counterparty, counterparty_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Counterparty not found")
    return list(
        db.scalars(
            select(CounterpartyCreditPolicy)
            .where(CounterpartyCreditPolicy.counterparty_id == counterparty_id)
            .order_by(
                CounterpartyCreditPolicy.currency,
                CounterpartyCreditPolicy.policy_version.desc(),
            )
        )
    )


@router.post(
    "/counterparties/{counterparty_id}/credit-policies",
    response_model=CounterpartyCreditPolicyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_credit_policy(
    counterparty_id: str,
    payload: CounterpartyCreditPolicyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(policy_reviewer),
) -> CounterpartyCreditPolicy:
    counterparty = db.get(Counterparty, counterparty_id)
    if counterparty is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Counterparty not found")
    if counterparty.status == "archived":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Credit policies cannot be created for an archived counterparty",
        )

    effective_from = _utc_naive(payload.effective_from or datetime.utcnow())
    expires_at = _utc_naive(payload.expires_at)
    if expires_at <= effective_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="expires_at must be later than effective_from",
        )
    latest_version = db.scalar(
        select(func.max(CounterpartyCreditPolicy.policy_version)).where(
            CounterpartyCreditPolicy.counterparty_id == counterparty_id,
            CounterpartyCreditPolicy.currency == payload.currency,
        )
    ) or 0
    policy = CounterpartyCreditPolicy(
        counterparty_id=counterparty_id,
        currency=payload.currency,
        policy_version=latest_version + 1,
        risk_tier=payload.risk_tier,
        credit_limit=payload.credit_limit,
        max_payment_terms_days=payload.max_payment_terms_days,
        minimum_deposit_percentage=payload.minimum_deposit_percentage,
        rationale=payload.rationale,
        effective_from=effective_from,
        expires_at=expires_at,
        created_by_id=user.id,
    )
    db.add(policy)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A competing policy version was created; reload and try again",
        )
    record_audit_event(
        db,
        actor_id=user.id,
        action="credit_policy.created",
        object_type="counterparty_credit_policy",
        object_id=policy.id,
        details={
            "counterparty_id": counterparty_id,
            "currency": policy.currency,
            "policy_version": policy.policy_version,
            "risk_tier": policy.risk_tier,
        },
    )
    db.commit()
    db.refresh(policy)
    return policy


@router.post(
    "/credit-policies/{policy_id}/actions",
    response_model=CounterpartyCreditPolicyRead,
)
def act_on_credit_policy(
    policy_id: str,
    payload: CounterpartyCreditPolicyAction,
    db: Session = Depends(get_db),
    user: User = Depends(policy_reviewer),
) -> CounterpartyCreditPolicy:
    policy = db.get(CounterpartyCreditPolicy, policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credit policy not found")
    if policy.record_version != payload.expected_record_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Credit policy was updated by another user; reload before reviewing",
        )

    now = datetime.utcnow()
    superseded_ids = []
    if payload.action == "activate":
        if policy.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only draft credit policies can be activated",
            )
        if policy.effective_from > now or policy.expires_at <= now:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Credit policy must be currently effective before activation",
            )
        active_policies = db.scalars(
            select(CounterpartyCreditPolicy).where(
                CounterpartyCreditPolicy.counterparty_id == policy.counterparty_id,
                CounterpartyCreditPolicy.currency == policy.currency,
                CounterpartyCreditPolicy.status == "active",
                CounterpartyCreditPolicy.id != policy.id,
            )
        )
        for active in active_policies:
            active.status = "retired"
            active.record_version += 1
            superseded_ids.append(active.id)
        policy.status = "active"
        policy.approved_by_id = user.id
        policy.approved_at = now
    else:
        if policy.status not in {"draft", "active"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only draft or active credit policies can be retired",
            )
        policy.status = "retired"

    policy.record_version += 1
    record_audit_event(
        db,
        actor_id=user.id,
        action="credit_policy.{}".format(payload.action),
        object_type="counterparty_credit_policy",
        object_id=policy.id,
        details={
            "counterparty_id": policy.counterparty_id,
            "currency": policy.currency,
            "policy_version": policy.policy_version,
            "rationale": payload.rationale,
            "superseded_policy_ids": superseded_ids,
            "record_version": policy.record_version,
        },
    )
    db.commit()
    db.refresh(policy)
    return policy
