from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.deps import require_roles
from backend.app.models import PortfolioStressTest, User
from backend.app.portfolio_service import build_portfolio_summary, execute_portfolio_stress_test
from backend.app.schemas import (
    PortfolioStressTestCreate,
    PortfolioStressTestRead,
    PortfolioSummary,
)


router = APIRouter(prefix="/portfolio", tags=["portfolio"])
portfolio_user = require_roles(
    {"admin", "business_user", "risk_reviewer", "compliance_reviewer", "model_developer"}
)
stress_user = require_roles({"admin", "risk_reviewer"})


@router.get("/summary", response_model=PortfolioSummary)
def get_portfolio_summary(
    db: Session = Depends(get_db),
    user: User = Depends(portfolio_user),
) -> PortfolioSummary:
    return build_portfolio_summary(db)


@router.post(
    "/stress-tests",
    response_model=PortfolioStressTestRead,
    status_code=status.HTTP_201_CREATED,
)
def create_portfolio_stress_test(
    payload: PortfolioStressTestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(stress_user),
) -> PortfolioStressTest:
    item = execute_portfolio_stress_test(db, payload=payload, user=user)
    db.commit()
    db.refresh(item)
    return item


@router.get("/stress-tests", response_model=List[PortfolioStressTestRead])
def list_portfolio_stress_tests(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(portfolio_user),
) -> List[PortfolioStressTest]:
    return list(
        db.scalars(
            select(PortfolioStressTest)
            .order_by(PortfolioStressTest.created_at.desc())
            .limit(limit)
        )
    )


@router.get("/stress-tests/{stress_test_id}", response_model=PortfolioStressTestRead)
def get_portfolio_stress_test(
    stress_test_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(portfolio_user),
) -> PortfolioStressTest:
    item = db.get(PortfolioStressTest, stress_test_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stress test not found")
    return item
