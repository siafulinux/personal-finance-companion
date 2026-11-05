"""CSV import endpoints: upload, preview, commit and history."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.imports.service import (
    commit_import,
    create_import,
    get_import,
    import_records,
    list_imports,
    preview_import,
)
from app.models import User
from app.schemas.imports import ImportMappingRequest, ImportOut, ImportRecordOut
from app.security.deps import get_current_user

router = APIRouter(prefix="/imports", tags=["imports"])


@router.get("", response_model=list[ImportOut])
def get_imports(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ImportOut]:
    return [ImportOut.model_validate(i) for i in list_imports(db, user.id)]


@router.post("", status_code=201)
async def upload_csv(
    file: UploadFile = File(...),
    account_id: uuid.UUID = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    content = await file.read()
    job = create_import(
        db,
        user,
        account_id=account_id,
        filename=file.filename or "upload.csv",
        content=content,
    )
    # Return a preview when the columns can be auto-mapped, plus the raw headers so the
    # client can always render the mapping controls (even for unusual column names).
    from app.imports.parse import suggest_mapping
    from app.services.errors import DomainError

    headers = list(job.raw_rows[0].keys()) if job.raw_rows else []
    suggested = suggest_mapping(headers)
    preview = None
    preview_error = None
    try:
        preview = preview_import(db, user, job.id, suggested)
    except DomainError as exc:
        preview_error = exc.message
    return {
        "import": ImportOut.model_validate(job).model_dump(),
        "headers": headers,
        "suggested_mapping": suggested,
        "preview": preview,
        "preview_error": preview_error,
    }


@router.get("/{import_id}/records", response_model=list[ImportRecordOut])
def get_records(
    import_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ImportRecordOut]:
    return [ImportRecordOut.model_validate(r) for r in import_records(db, user.id, import_id)]


@router.get("/{import_id}", response_model=ImportOut)
def get_one_import(
    import_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportOut:
    return ImportOut.model_validate(get_import(db, user.id, import_id))


@router.post("/{import_id}/preview")
def preview(
    import_id: uuid.UUID,
    payload: ImportMappingRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return preview_import(db, user, import_id, payload.mapping)


@router.post("/{import_id}/commit")
def commit(
    import_id: uuid.UUID,
    payload: ImportMappingRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return commit_import(db, user, import_id, payload.mapping)
