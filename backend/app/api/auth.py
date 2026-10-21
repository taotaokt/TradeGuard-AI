from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.audit import record_audit_event
from backend.app.deps import get_current_user
from backend.app.models import User
from backend.app.schemas import LoginRequest, TokenResponse, UserRead
from backend.app.security import create_access_token, verify_password


router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        record_audit_event(
            db,
            actor_id=user.id if user else None,
            action="authentication.failed",
            object_type="user",
            object_id=user.id if user else None,
            details={"email": payload.email.lower().strip()},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    record_audit_event(
        db,
        actor_id=user.id,
        action="authentication.succeeded",
        object_type="user",
        object_id=user.id,
        details={"role": user.role},
    )
    db.commit()
    return TokenResponse(access_token=create_access_token(user.id, user.role))


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> User:
    return user
