from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from backend.app.api import (
    assessments,
    auth,
    counterparties,
    documents,
    monitoring,
    screening,
    system,
    transactions,
)
from backend.app.config import settings
from backend.app.db import SessionLocal
from backend.app.models import User
from backend.app.security import hash_password


def initialize_database() -> None:
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == settings.initial_admin_email.lower()))
        if admin is None:
            db.add(
                User(
                    email=settings.initial_admin_email.lower(),
                    full_name="Initial Administrator",
                    password_hash=hash_password(settings.initial_admin_password),
                    role="admin",
                )
            )
            db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Explainable cross-border counterparty and transaction risk decision support.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(counterparties.router, prefix="/api")
app.include_router(transactions.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(screening.router, prefix="/api")
app.include_router(assessments.router, prefix="/api")
app.include_router(monitoring.router, prefix="/api")
app.include_router(system.router, prefix="/api")

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health", tags=["system"])
def health() -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "version": "0.1.0",
    }
