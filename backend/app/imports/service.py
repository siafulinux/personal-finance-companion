"""CSV import sessions: upload -> preview -> commit, with idempotent retries."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.imports.adapters import get_adapter
from app.imports.parse import MAX_FILE_BYTES, CsvDocument, CsvError, ParsedRow, build_rows
from app.models import (
    Category,
    FinancialAccount,
    ImportRecord,
    Transaction,
    TransactionImport,
    User,
)
from app.models.enums import ImportRowStatus, ImportStatus, TransactionSource
from app.models.enums import TransactionStatus, TransactionType
from app.schemas.finance import TransactionCreate
from app.services.bill_matching import match_transaction
from app.services.dedupe import file_fingerprint, normalize_text, transaction_fingerprint
from app.services.errors import ConflictError, NotFoundError, ValidationError
from app.utils.dates import utc_now
from app.utils.money import ZERO, quantize


def get_import(db: Session, user_id: uuid.UUID, import_id: uuid.UUID) -> TransactionImport:
    record = db.scalar(
        select(TransactionImport).where(
            TransactionImport.id == import_id, TransactionImport.user_id == user_id
        )
    )
    if record is None:
        raise NotFoundError("Import not found.")
    return record


def create_import(
    db: Session,
    user: User,
    *,
    account_id: uuid.UUID,
    filename: str,
    content: bytes,
) -> TransactionImport:
    if not content:
        raise ValidationError("The uploaded file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise ValidationError("CSV files must be 5 MB or smaller.")
    account = db.scalar(
        select(FinancialAccount).where(
            FinancialAccount.id == account_id, FinancialAccount.user_id == user.id
        )
    )
    if account is None:
        raise ValidationError("Select a valid account for this import.")
    if account.is_archived:
        raise ValidationError("Cannot import into an archived account.")

    adapter = get_adapter("csv")
    try:
        document = adapter.read(content)
    except CsvError as exc:
        raise ValidationError(str(exc)) from exc

    import_job = TransactionImport(
        user_id=user.id,
        account_id=account.id,
        filename=filename[:255],
        file_sha256=file_fingerprint(content),
        file_size=len(content),
        delimiter=document.delimiter,
        has_header=document.has_header,
        status=ImportStatus.UPLOADED.value,
        raw_rows=document.rows,
        row_count=len(document.rows),
    )
    db.add(import_job)
    db.flush()
    return import_job


def _document_from_job(job: TransactionImport) -> CsvDocument:
    rows = job.raw_rows or []
    if not rows:
        raise ValidationError("This import has no rows to preview.")
    headers = list(rows[0].keys())
    return CsvDocument(
        headers=headers,
        rows=rows,
        delimiter=job.delimiter,
        has_header=job.has_header,
        encoding="utf-8",
    )


def _existing_index(
    db: Session, user_id: uuid.UUID, account_id: uuid.UUID
) -> tuple[set[str], set[tuple[date, Decimal, str]]]:
    rows = db.execute(
        select(
            Transaction.dedupe_key,
            Transaction.txn_date,
            Transaction.amount,
            Transaction.description,
            Transaction.source,
        ).where(
            Transaction.user_id == user_id,
            Transaction.account_id == account_id,
        )
    ).all()
    keys: set[str] = set()
    soft: set[tuple[date, Decimal, str]] = set()
    for dedupe_key, txn_date, amount, description, source in rows:
        if dedupe_key:
            keys.add(dedupe_key)
        # Do not treat two manual entries with identical text as duplicates of an import;
        # only imported rows provide a reliable soft signature.
        if source in (TransactionSource.CSV.value, TransactionSource.PROVIDER.value):
            soft.add((txn_date, quantize(amount), normalize_text(description)))
    return keys, soft


def _mark_duplicates(
    db: Session, user: User, job: TransactionImport, rows: list[ParsedRow]
) -> list[ParsedRow]:
    keys, soft = _existing_index(db, user.id, job.account_id)
    batch_keys: set[str] = set()
    batch_soft: set[tuple[date, Decimal, str]] = set()
    for row in rows:
        if row.status != "ok" or row.amount is None or row.txn_date is None:
            continue
        key = transaction_fingerprint(
            account_id=job.account_id,
            txn_date=row.txn_date,
            amount=row.amount,
            description=row.description,
            merchant=row.merchant,
            tx_type=row.tx_type or "purchase",
            external_id=row.external_id,
        )
        signature = (row.txn_date, quantize(row.amount), normalize_text(row.description))
        if key in keys or (signature in soft and not row.external_id) or key in batch_keys or signature in batch_soft:
            row.status = "duplicate"
            row.reason = "Already imported or duplicated within this file"
        else:
            batch_keys.add(key)
            batch_soft.add(signature)
    return rows


def preview_import(
    db: Session,
    user: User,
    import_id: uuid.UUID,
    mapping: dict[str, str | None] | None = None,
) -> dict[str, object]:
    job = get_import(db, user.id, import_id)
    document = _document_from_job(job)
    adapter = get_adapter("csv")
    try:
        preview = adapter.preview(document, mapping or job.column_mapping)
    except CsvError as exc:
        raise ValidationError(str(exc)) from exc
    rows = _mark_duplicates(db, user, job, preview.rows)
    job.column_mapping = preview.mapping
    if job.status == ImportStatus.UPLOADED.value:
        job.status = ImportStatus.PREVIEWED.value
    db.flush()

    ok = [r for r in rows if r.status == "ok"]
    duplicates = [r for r in rows if r.status == "duplicate"]
    errors = [r for r in rows if r.status == "error"]
    total = sum((r.amount for r in ok if r.amount), ZERO)
    return {
        "import_id": str(job.id),
        "filename": job.filename,
        "account_id": str(job.account_id),
        "headers": document.headers,
        "mapping": preview.mapping,
        "suggested_mapping": preview.suggested_mapping,
        "has_header": document.has_header,
        "delimiter": document.delimiter,
        "rows": [r.as_dict() for r in rows[:300]],
        "truncated": len(rows) > 300,
        "summary": {
            "total_rows": len(rows),
            "ready": len(ok),
            "duplicates": len(duplicates),
            "rejected": len(errors),
            "ready_total": str(quantize(total)),
        },
    }


def commit_import(
    db: Session,
    user: User,
    import_id: uuid.UUID,
    mapping: dict[str, str | None] | None = None,
) -> dict[str, object]:
    job = get_import(db, user.id, import_id)
    if job.status == ImportStatus.COMMITTED.value:
        return {
            "import_id": str(job.id),
            "already_committed": True,
            "imported": job.imported_count,
            "duplicates": job.duplicate_count,
            "rejected": job.rejected_count,
            "committed_at": job.committed_at.isoformat() if job.committed_at else None,
        }
    document = _document_from_job(job)
    adapter = get_adapter("csv")
    try:
        preview = adapter.preview(document, mapping or job.column_mapping)
    except CsvError as exc:
        raise ValidationError(str(exc)) from exc
    rows = _mark_duplicates(db, user, job, preview.rows)
    job.column_mapping = preview.mapping

    categories = {
        c.name.strip().lower(): c
        for c in db.scalars(
            select(Category).where(Category.user_id == user.id, Category.is_archived.is_(False))
        )
    }
    category_col = preview.mapping.get("category")
    if category_col and category_col not in document.headers:
        category_col = None

    created: list[Transaction] = []
    imported = duplicates = rejected = 0
    for row in rows:
        if row.status == "error":
            rejected += 1
            db.add(
                ImportRecord(
                    import_id=job.id,
                    row_number=row.row_number,
                    raw_data=row.raw,
                    status=ImportRowStatus.REJECTED.value,
                    reason=row.reason,
                )
            )
            continue
        if row.status == "duplicate":
            duplicates += 1
            db.add(
                ImportRecord(
                    import_id=job.id,
                    row_number=row.row_number,
                    raw_data=row.raw,
                    status=ImportRowStatus.DUPLICATE.value,
                    reason=row.reason,
                )
            )
            continue
        assert row.amount is not None and row.txn_date is not None
        category_id = None
        if category_col and row.raw.get(category_col):
            category = categories.get(row.raw[category_col].strip().lower())
            category_id = category.id if category else None
        payload = TransactionCreate(
            account_id=job.account_id,
            description=row.description or "Imported transaction",
            merchant=row.merchant,
            amount=quantize(row.amount),
            tx_type=TransactionType(row.tx_type or "purchase"),
            status=TransactionStatus.POSTED,
            txn_date=row.txn_date,
            category_id=category_id,
            external_id=row.external_id,
            source=TransactionSource.CSV,
            notes=f"Imported from {job.filename}",
        )
        dedupe_key = transaction_fingerprint(
            account_id=job.account_id,
            txn_date=row.txn_date,
            amount=row.amount,
            description=row.description,
            merchant=row.merchant,
            tx_type=row.tx_type or "purchase",
            external_id=row.external_id,
        )
        from app.services.transactions import create_transaction

        try:
            txn, _ = create_transaction(
                db,
                user,
                payload,
                source=TransactionSource.CSV,
                import_id=job.id,
                dedupe_key=dedupe_key,
                run_matching=False,
            )
        except ConflictError as exc:
            duplicates += 1
            db.add(
                ImportRecord(
                    import_id=job.id,
                    row_number=row.row_number,
                    raw_data=row.raw,
                    status=ImportRowStatus.DUPLICATE.value,
                    reason=str(exc),
                )
            )
            continue
        imported += 1
        created.append(txn)
        db.add(
            ImportRecord(
                import_id=job.id,
                row_number=row.row_number,
                raw_data=row.raw,
                status=ImportRowStatus.IMPORTED.value,
                transaction_id=txn.id,
            )
        )

    # Bill matching runs after all rows exist so ambiguous candidates stay ambiguous.
    match_results = []
    for txn in created:
        info = match_transaction(db, user, txn)
        if info and info.get("outcome") in ("auto", "suggest"):
            match_results.append(info)

    auto_matched = sum(1 for info in match_results if info.get("outcome") == "auto")
    suggested_matches = sum(1 for info in match_results if info.get("outcome") == "suggest")

    job.status = ImportStatus.COMMITTED.value
    job.imported_count = imported
    job.duplicate_count = duplicates
    job.rejected_count = rejected
    job.committed_at = utc_now()
    db.flush()
    return {
        "import_id": str(job.id),
        "already_committed": False,
        "imported": imported,
        "duplicates": duplicates,
        "rejected": rejected,
        "matched_bills": len(match_results),
        "auto_matched": auto_matched,
        "suggested_matches": suggested_matches,
        "match_suggestions": match_results,
        "committed_at": job.committed_at.isoformat() if job.committed_at else None,
    }


def list_imports(db: Session, user_id: uuid.UUID, limit: int = 50) -> list[TransactionImport]:
    return list(
        db.scalars(
            select(TransactionImport)
            .where(TransactionImport.user_id == user_id)
            .order_by(TransactionImport.created_at.desc())
            .limit(limit)
        )
    )


def import_records(db: Session, user_id: uuid.UUID, import_id: uuid.UUID) -> list[ImportRecord]:
    job = get_import(db, user_id, import_id)
    return list(
        db.scalars(
            select(ImportRecord)
            .where(ImportRecord.import_id == job.id)
            .order_by(ImportRecord.row_number)
            .limit(1000)
        )
    )
