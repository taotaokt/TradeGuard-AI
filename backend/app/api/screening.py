import csv
import hashlib
import io
import json
import re
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from backend.app.audit import record_audit_event
from backend.app.config import settings
from backend.app.db import get_db
from backend.app.deps import get_current_user, require_roles
from backend.app.models import (
    Counterparty,
    ScreeningCandidate,
    ScreeningEntry,
    ScreeningList,
    ScreeningListVersion,
    ScreeningRun,
    User,
)
from backend.app.monitoring import create_screening_alert
from backend.app.schemas import (
    ScreeningCandidateRead,
    ScreeningListCreate,
    ScreeningListRead,
    ScreeningListVersionRead,
    ScreeningRequest,
    ScreeningResolution,
    ScreeningRunRead,
)
from backend.app.screening import best_name_match, normalize_name


router = APIRouter(tags=["screening"])
admin_user = require_roles({"admin"})
screening_user = require_roles({"admin", "business_user", "risk_reviewer", "compliance_reviewer"})
compliance_user = require_roles({"admin", "compliance_reviewer"})


def _run_query():
    return select(ScreeningRun).options(selectinload(ScreeningRun.candidates))


def _safe_csv_name(filename: str) -> str:
    basename = filename.replace("\\", "/").split("/")[-1]
    cleaned = re.sub(r"[^\w.()\- ]", "_", basename, flags=re.UNICODE).strip(" .")
    return (cleaned or "screening-list.csv")[:255]


def _parse_effective_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="effective_at must be an ISO-8601 date or datetime",
        )
    return parsed.replace(tzinfo=None)


def _parse_entries(content: bytes) -> List[dict]:
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Screening CSV must use UTF-8 encoding",
        )
    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    required = {"source_id", "name"}
    if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Screening CSV requires source_id and name columns",
        )

    rows = []
    seen_ids = set()
    for line_number, row in enumerate(reader, start=2):
        source_id = (row.get("source_id") or "").strip()
        name = (row.get("name") or "").strip()
        if not source_id or not name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="CSV line {} has an empty source_id or name".format(line_number),
            )
        if source_id in seen_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="CSV contains duplicate source_id {}".format(source_id),
            )
        seen_ids.add(source_id)
        country = (row.get("country") or "").strip().upper() or None
        if country is not None and len(country) != 2:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="CSV line {} country must be a two-letter code".format(line_number),
            )
        aliases = [item.strip() for item in (row.get("aliases") or "").split("|") if item.strip()]
        raw_identifiers = (row.get("identifiers") or "").strip()
        if raw_identifiers:
            try:
                identifiers = json.loads(raw_identifiers)
            except json.JSONDecodeError:
                identifiers = {"source_value": raw_identifiers}
        else:
            identifiers = {}
        rows.append(
            {
                "source_entry_id": source_id,
                "primary_name": name,
                "normalized_name": normalize_name(name),
                "entity_type": (row.get("entity_type") or "entity").strip() or "entity",
                "country": country,
                "address": (row.get("address") or "").strip() or None,
                "program": (row.get("program") or "").strip() or None,
                "aliases_json": json.dumps(aliases, ensure_ascii=False),
                "identifiers_json": json.dumps(identifiers, ensure_ascii=False, sort_keys=True),
                "remarks": (row.get("remarks") or "").strip() or None,
            }
        )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Screening CSV must contain at least one entry",
        )
    return rows


@router.get("/screening/lists", response_model=List[ScreeningListRead])
def list_screening_lists(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> List[ScreeningList]:
    return list(db.scalars(select(ScreeningList).order_by(ScreeningList.code)))


@router.post(
    "/screening/lists", response_model=ScreeningListRead, status_code=status.HTTP_201_CREATED
)
def create_screening_list(
    payload: ScreeningListCreate,
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> ScreeningList:
    screening_list = ScreeningList(**payload.model_dump())
    db.add(screening_list)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="List code already exists")
    record_audit_event(
        db,
        actor_id=user.id,
        action="screening_list.created",
        object_type="screening_list",
        object_id=screening_list.id,
        details={"code": screening_list.code, "authority": screening_list.authority},
    )
    db.commit()
    db.refresh(screening_list)
    return screening_list


@router.get(
    "/screening/lists/{screening_list_id}/versions",
    response_model=List[ScreeningListVersionRead],
)
def list_screening_list_versions(
    screening_list_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[ScreeningListVersion]:
    if db.get(ScreeningList, screening_list_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screening list not found")
    query = (
        select(ScreeningListVersion)
        .where(ScreeningListVersion.screening_list_id == screening_list_id)
        .order_by(ScreeningListVersion.created_at.desc())
    )
    return list(db.scalars(query))


@router.post(
    "/screening/lists/{screening_list_id}/versions/import",
    response_model=ScreeningListVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def import_screening_list_version(
    screening_list_id: str,
    version: str = Form(..., min_length=1, max_length=100),
    effective_at: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> ScreeningListVersion:
    screening_list = db.get(ScreeningList, screening_list_id)
    if screening_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screening list not found")
    filename = _safe_csv_name(file.filename or "screening-list.csv")
    if Path(filename).suffix.lower() != ".csv":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Screening-list imports must be UTF-8 CSV files",
        )
    content = await file.read(settings.max_upload_size_bytes + 1)
    await file.close()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(status_code=413, detail="List file exceeds the configured size limit")
    entries = _parse_entries(content)
    effective_datetime = _parse_effective_at(effective_at)
    existing = db.scalar(
        select(ScreeningListVersion).where(
            ScreeningListVersion.screening_list_id == screening_list_id,
            ScreeningListVersion.version == version,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="List version already exists")

    checksum = hashlib.sha256(content).hexdigest()
    list_storage = Path(settings.upload_dir).resolve() / "screening-lists"
    list_storage.mkdir(parents=True, exist_ok=True)
    source_file_key = "{}.csv".format(uuid.uuid4().hex)
    source_path = list_storage / source_file_key
    source_path.write_bytes(content)

    list_version = ScreeningListVersion(
        screening_list_id=screening_list_id,
        version=version,
        status="validated",
        effective_at=effective_datetime,
        checksum_sha256=checksum,
        source_filename=filename,
        source_file_key=source_file_key,
        entry_count=len(entries),
        imported_by_id=user.id,
    )
    try:
        db.add(list_version)
        db.flush()
        db.add_all(
            [ScreeningEntry(list_version_id=list_version.id, **entry) for entry in entries]
        )
        record_audit_event(
            db,
            actor_id=user.id,
            action="screening_list_version.imported",
            object_type="screening_list_version",
            object_id=list_version.id,
            details={"version": version, "checksum_sha256": checksum, "entry_count": len(entries)},
        )
        db.commit()
    except Exception:
        db.rollback()
        source_path.unlink(missing_ok=True)
        raise
    db.refresh(list_version)
    return list_version


@router.post(
    "/screening/versions/{version_id}/activate", response_model=ScreeningListVersionRead
)
def activate_screening_list_version(
    version_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(admin_user),
) -> ScreeningListVersion:
    list_version = db.get(ScreeningListVersion, version_id)
    if list_version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List version not found")
    screening_list = db.get(ScreeningList, list_version.screening_list_id)
    if screening_list.active_version_id and screening_list.active_version_id != list_version.id:
        previous = db.get(ScreeningListVersion, screening_list.active_version_id)
        if previous is not None:
            previous.status = "retired"
    screening_list.active_version_id = list_version.id
    list_version.status = "active"
    record_audit_event(
        db,
        actor_id=user.id,
        action="screening_list_version.activated",
        object_type="screening_list_version",
        object_id=list_version.id,
        details={"screening_list_id": screening_list.id, "version": list_version.version},
    )
    db.commit()
    db.refresh(list_version)
    return list_version


@router.post("/counterparties/{counterparty_id}/screen", response_model=ScreeningRunRead)
def screen_counterparty(
    counterparty_id: str,
    payload: ScreeningRequest,
    db: Session = Depends(get_db),
    user: User = Depends(screening_user),
) -> ScreeningRun:
    counterparty = db.scalar(
        select(Counterparty)
        .options(selectinload(Counterparty.aliases), selectinload(Counterparty.related_parties))
        .where(Counterparty.id == counterparty_id)
    )
    if counterparty is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Counterparty not found")
    if counterparty.status == "archived":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Archived counterparty")
    active_lists = list(
        db.scalars(select(ScreeningList).where(ScreeningList.active_version_id.is_not(None)))
    )
    if not active_lists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active screening-list version is configured",
        )

    run = ScreeningRun(
        counterparty_id=counterparty.id,
        fuzzy_threshold=payload.fuzzy_threshold,
        screened_by_id=user.id,
    )
    db.add(run)
    db.flush()

    subjects = [
        (
            [counterparty.legal_name] + [alias.name for alias in counterparty.aliases],
            None,
            counterparty.jurisdiction,
            counterparty.registration_number,
        )
    ]
    subjects.extend(
        ([party.name], party.id, party.country, party.identifier)
        for party in counterparty.related_parties
    )

    for source in active_lists:
        entries = list(
            db.scalars(
                select(ScreeningEntry).where(
                    ScreeningEntry.list_version_id == source.active_version_id
                )
            )
        )
        for screened_names, related_party_id, screened_country, screened_identifier in subjects:
            for entry in entries:
                aliases = json.loads(entry.aliases_json)
                matched_name = None
                screened_name = screened_names[0]
                score = 0.0
                match_type = "fuzzy"
                for subject_name in screened_names:
                    candidate_name, candidate_score, candidate_type = best_name_match(
                        subject_name, [entry.primary_name] + aliases
                    )
                    if candidate_score > score:
                        screened_name = subject_name
                        matched_name = candidate_name
                        score = candidate_score
                        match_type = candidate_type
                if matched_name is None or score < payload.fuzzy_threshold:
                    continue
                run.candidates.append(
                    ScreeningCandidate(
                        counterparty_id=counterparty.id,
                        related_party_id=related_party_id,
                        list_version_id=entry.list_version_id,
                        screening_entry_id=entry.id,
                        source_list_code=source.code,
                        screened_name=screened_name,
                        normalized_screened_name=normalize_name(screened_name),
                        screened_country=screened_country,
                        screened_identifier=screened_identifier,
                        matched_name=matched_name,
                        match_type=match_type,
                        score=Decimal(str(score)),
                        program=entry.program,
                        matched_country=entry.country,
                        matched_address=entry.address,
                        matched_identifiers_json=entry.identifiers_json,
                    )
                )

    db.flush()
    if run.candidates:
        create_screening_alert(db, run=run, candidates=run.candidates, actor=user)
    counterparty.status = "screening_review" if run.candidates else "active"
    counterparty.version += 1
    record_audit_event(
        db,
        actor_id=user.id,
        action="counterparty.screened",
        object_type="screening_run",
        object_id=run.id,
        details={
            "counterparty_id": counterparty.id,
            "candidate_count": len(run.candidates),
            "fuzzy_threshold": payload.fuzzy_threshold,
            "list_versions": [item.active_version_id for item in active_lists],
        },
    )
    db.commit()
    return db.scalar(_run_query().where(ScreeningRun.id == run.id))


@router.get("/screening/runs/{run_id}", response_model=ScreeningRunRead)
def get_screening_run(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScreeningRun:
    run = db.scalar(_run_query().where(ScreeningRun.id == run_id))
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screening run not found")
    return run


@router.post(
    "/screening/candidates/{candidate_id}/resolve", response_model=ScreeningCandidateRead
)
def resolve_screening_candidate(
    candidate_id: str,
    payload: ScreeningResolution,
    db: Session = Depends(get_db),
    user: User = Depends(compliance_user),
) -> ScreeningCandidate:
    candidate = db.get(ScreeningCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    previous_status = candidate.status
    candidate.status = payload.classification
    candidate.rationale = payload.rationale.strip()
    candidate.reviewed_by_id = user.id
    candidate.reviewed_at = datetime.utcnow()
    db.flush()

    counterparty = db.get(Counterparty, candidate.counterparty_id)
    if payload.classification == "confirmed":
        counterparty.status = "compliance_hold"
    else:
        confirmed = db.scalar(
            select(ScreeningCandidate.id).where(
                ScreeningCandidate.counterparty_id == counterparty.id,
                ScreeningCandidate.status == "confirmed",
            ).limit(1)
        )
        unresolved = db.scalar(
            select(ScreeningCandidate.id).where(
                ScreeningCandidate.counterparty_id == counterparty.id,
                ScreeningCandidate.status.in_(
                    ["pending", "possible", "confirmed", "insufficient_information"]
                ),
            ).limit(1)
        )
        if confirmed:
            counterparty.status = "compliance_hold"
        else:
            counterparty.status = "screening_review" if unresolved else "active"
    counterparty.version += 1
    record_audit_event(
        db,
        actor_id=user.id,
        action="screening_candidate.resolved",
        object_type="screening_candidate",
        object_id=candidate.id,
        details={
            "from": previous_status,
            "to": payload.classification,
            "rationale": candidate.rationale,
            "counterparty_status": counterparty.status,
        },
    )
    db.commit()
    db.refresh(candidate)
    return candidate
