import re
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.audit import record_audit_event
from backend.app.config import settings
from backend.app.db import get_db
from backend.app.deps import get_current_user, require_roles
from backend.app.models import Counterparty, SupportingDocument, TradeTransaction, User
from backend.app.schemas import SupportingDocumentRead


router = APIRouter(tags=["documents"])
write_user = require_roles({"admin", "business_user", "risk_reviewer", "compliance_reviewer"})

DOCUMENT_TYPES = {
    "business_registration",
    "tax_document",
    "ownership_document",
    "financial_statement",
    "purchase_order",
    "invoice",
    "contract",
    "bill_of_lading",
    "certificate_of_origin",
    "end_use_statement",
    "other",
}

ALLOWED_FILE_TYPES = {
    "application/pdf": {".pdf"},
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
    "text/csv": {".csv"},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {".xlsx"},
}


def _clean_filename(filename: str) -> str:
    basename = filename.replace("\\", "/").split("/")[-1]
    cleaned = re.sub(r"[^\w.()\- ]", "_", basename, flags=re.UNICODE).strip(" .")
    return (cleaned or "upload")[:255]


def _validate_metadata(filename: str, content_type: Optional[str], document_type: str) -> tuple:
    if document_type not in DOCUMENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": "Unsupported document type", "allowed": sorted(DOCUMENT_TYPES)},
        )

    clean_name = _clean_filename(filename)
    suffix = Path(clean_name).suffix.lower()
    allowed_extensions = ALLOWED_FILE_TYPES.get(content_type or "")
    if allowed_extensions is None or suffix not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Allowed files: PDF, PNG, JPG, CSV, and XLSX",
        )
    return clean_name, suffix


def _upload_root() -> Path:
    root = Path(settings.upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


async def _store_upload(upload: UploadFile, suffix: str) -> tuple:
    storage_key = "{}{}".format(uuid.uuid4().hex, suffix)
    destination = _upload_root() / storage_key
    size = 0
    try:
        with destination.open("xb") as output:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > settings.max_upload_size_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the configured upload-size limit",
                    )
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    if size == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Empty files cannot be uploaded",
        )
    return storage_key, size, destination


async def _create_document(
    *,
    upload: UploadFile,
    document_type: str,
    description: Optional[str],
    db: Session,
    user: User,
    counterparty_id: Optional[str] = None,
    transaction_id: Optional[str] = None,
) -> SupportingDocument:
    clean_name, suffix = _validate_metadata(
        upload.filename or "upload", upload.content_type, document_type
    )
    storage_key, size, destination = await _store_upload(upload, suffix)
    document = SupportingDocument(
        counterparty_id=counterparty_id,
        transaction_id=transaction_id,
        original_filename=clean_name,
        storage_key=storage_key,
        document_type=document_type,
        content_type=upload.content_type or "application/octet-stream",
        size_bytes=size,
        description=description,
        uploaded_by_id=user.id,
    )
    try:
        db.add(document)
        db.flush()
        record_audit_event(
            db,
            actor_id=user.id,
            action="document.uploaded",
            object_type="supporting_document",
            object_id=document.id,
            details={
                "counterparty_id": counterparty_id,
                "transaction_id": transaction_id,
                "document_type": document_type,
                "size_bytes": size,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise
    db.refresh(document)
    return document


@router.get(
    "/counterparties/{counterparty_id}/evidence",
    response_model=List[SupportingDocumentRead],
)
def list_counterparty_evidence(
    counterparty_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[SupportingDocument]:
    if db.get(Counterparty, counterparty_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Counterparty not found")
    query = (
        select(SupportingDocument)
        .where(
            SupportingDocument.counterparty_id == counterparty_id,
            SupportingDocument.status == "active",
        )
        .order_by(SupportingDocument.created_at.desc())
    )
    return list(db.scalars(query))


@router.post(
    "/counterparties/{counterparty_id}/evidence",
    response_model=SupportingDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_counterparty_evidence(
    counterparty_id: str,
    document_type: str = Form(...),
    description: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(write_user),
) -> SupportingDocument:
    if db.get(Counterparty, counterparty_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Counterparty not found")
    return await _create_document(
        upload=file,
        document_type=document_type,
        description=description,
        db=db,
        user=user,
        counterparty_id=counterparty_id,
    )


@router.get(
    "/transactions/{transaction_id}/documents",
    response_model=List[SupportingDocumentRead],
)
def list_transaction_documents(
    transaction_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[SupportingDocument]:
    if db.get(TradeTransaction, transaction_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    query = (
        select(SupportingDocument)
        .where(
            SupportingDocument.transaction_id == transaction_id,
            SupportingDocument.status == "active",
        )
        .order_by(SupportingDocument.created_at.desc())
    )
    return list(db.scalars(query))


@router.post(
    "/transactions/{transaction_id}/documents",
    response_model=SupportingDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_transaction_document(
    transaction_id: str,
    document_type: str = Form(...),
    description: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(write_user),
) -> SupportingDocument:
    if db.get(TradeTransaction, transaction_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return await _create_document(
        upload=file,
        document_type=document_type,
        description=description,
        db=db,
        user=user,
        transaction_id=transaction_id,
    )


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    document = db.get(SupportingDocument, document_id)
    if document is None or document.status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    path = _upload_root() / document.storage_key
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file not found")
    return FileResponse(path, media_type=document.content_type, filename=document.original_filename)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_document(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(write_user),
) -> None:
    document = db.get(SupportingDocument, document_id)
    if document is None or document.status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    document.status = "removed"
    record_audit_event(
        db,
        actor_id=user.id,
        action="document.removed",
        object_type="supporting_document",
        object_id=document.id,
        details={"retained_for_audit": True},
    )
    db.commit()
