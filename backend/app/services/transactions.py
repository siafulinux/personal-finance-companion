"""Transaction creation, editing, filtering and accounting-safe deletion."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models import (
    BillOccurrence,
    BillPaymentMatch,
    Category,
    FinancialAccount,
    Transaction,
    User,
)
from app.models.enums import MatchStatus, TransactionSource, TransactionStatus, TransactionType
from app.matching.normalize import normalize_merchant
from app.schemas.finance import TransactionCreate, TransactionListParams, TransactionUpdate
from app.services.bill_matching import match_transaction
from app.services.bills import recompute_occurrence
from app.services.dedupe import normalize_text, transaction_fingerprint
from app.services.errors import ConflictError, NotFoundError, ValidationError
from app.utils.dates import today_in
from app.utils.money import ZERO, quantize

SORTABLE = {
    "txn_date": Transaction.txn_date,
    "amount": Transaction.amount,
    "created_at": Transaction.created_at,
    "description": Transaction.description,
    "merchant": Transaction.merchant,
}


def get_transaction(db: Session, user_id: uuid.UUID, txn_id: uuid.UUID) -> Transaction:
    txn = db.scalar(
        select(Transaction)
        .options(
            joinedload(Transaction.account),
            joinedload(Transaction.transfer_account),
            joinedload(Transaction.category),
        )
        .where(Transaction.id == txn_id, Transaction.user_id == user_id)
    )
    if txn is None:
        raise NotFoundError("Transaction not found.")
    return txn


def _get_account(db: Session, user_id: uuid.UUID, account_id: uuid.UUID) -> FinancialAccount:
    account = db.scalar(
        select(FinancialAccount).where(
            FinancialAccount.id == account_id, FinancialAccount.user_id == user_id
        )
    )
    if account is None:
        raise ValidationError("The selected account does not exist.")
    if account.is_archived:
        raise ValidationError("The selected account is archived.")
    return account


def _get_category(db: Session, user_id: uuid.UUID, category_id: uuid.UUID | None) -> Category | None:
    if category_id is None:
        return None
    category = db.scalar(
        select(Category).where(Category.id == category_id, Category.user_id == user_id)
    )
    if category is None:
        raise ValidationError("The selected category does not exist.")
    if category.is_archived:
        raise ValidationError("The selected category is archived.")
    return category


def _reject_future_posted(user: User, txn_date, status: str) -> None:
    """A posted row represents money that already moved; never count future cash."""
    if status == TransactionStatus.POSTED.value and txn_date > today_in(user.timezone):
        raise ValidationError(
            "A posted transaction cannot be dated in the future. "
            "Choose today or earlier, or save it as pending."
        )


def create_transaction(
    db: Session,
    user: User,
    payload: TransactionCreate,
    *,
    source: TransactionSource | None = None,
    import_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
    run_matching: bool = True,
) -> tuple[Transaction, dict | None]:
    _reject_future_posted(user, payload.txn_date, payload.status.value)
    account = _get_account(db, user.id, payload.account_id)
    transfer_account = None
    if payload.tx_type == TransactionType.TRANSFER:
        assert payload.transfer_account_id is not None
        transfer_account = _get_account(db, user.id, payload.transfer_account_id)
        if transfer_account.id == account.id:
            raise ValidationError("A transfer needs two different accounts.")
        if transfer_account.currency != account.currency:
            raise ValidationError("Phase 1 supports transfers between USD accounts only.")
    category = _get_category(db, user.id, payload.category_id)
    if payload.tx_type == TransactionType.TRANSFER and category is not None:
        raise ValidationError("Internal transfers do not belong to a spending category.")

    txn_source = source or payload.source
    if dedupe_key is None and txn_source in (
        TransactionSource.CSV,
        TransactionSource.PROVIDER,
    ):
        dedupe_key = transaction_fingerprint(
            account_id=account.id,
            txn_date=payload.txn_date,
            amount=payload.amount,
            description=payload.description,
            merchant=payload.merchant,
            tx_type=payload.tx_type.value,
            external_id=payload.external_id,
        )

    txn = Transaction(
        user_id=user.id,
        account_id=account.id,
        transfer_account_id=transfer_account.id if transfer_account else None,
        description=payload.description.strip(),
        merchant=payload.merchant.strip() if payload.merchant else None,
        amount=quantize(payload.amount),
        tx_type=payload.tx_type.value,
        status=payload.status.value,
        txn_date=payload.txn_date,
        posting_date=payload.posting_date,
        category_id=category.id if category else None,
        notes=payload.notes,
        tags=payload.tags,
        source=txn_source.value,
        external_id=payload.external_id,
        import_id=import_id,
        dedupe_key=dedupe_key,
    )
    try:
        # A savepoint keeps a duplicate row from rolling back an entire import batch.
        with db.begin_nested():
            db.add(txn)
            db.flush()
    except IntegrityError as exc:
        raise ConflictError("This transaction already exists (duplicate import).") from exc

    match_info = None
    if run_matching and txn.status == "posted" and txn.tx_type in (
        TransactionType.PURCHASE.value,
        TransactionType.BILL_PAYMENT.value,
    ):
        match_info = match_transaction(db, user, txn)
    return txn, match_info


def possible_duplicates(
    db: Session, user: User, payload: TransactionCreate, *, exclude_id: uuid.UUID | None = None
) -> list[dict]:
    query = select(Transaction).where(
        Transaction.user_id == user.id,
        Transaction.account_id == payload.account_id,
        Transaction.amount == quantize(payload.amount),
        Transaction.txn_date >= payload.txn_date - timedelta(days=1),
        Transaction.txn_date <= payload.txn_date + timedelta(days=1),
    )
    if exclude_id:
        query = query.where(Transaction.id != exclude_id)
    rows = list(db.scalars(query.limit(10)))
    target = normalize_text(payload.description)
    target_merchant = normalize_merchant(payload.merchant or payload.description)
    results: list[dict] = []
    for row in rows:
        other = normalize_text(row.description)
        other_merchant = normalize_merchant(row.merchant or row.description)
        similar = (
            target == other
            or target_merchant == other_merchant
            or (target and target in other)
            or (other and other in target)
        )
        if similar:
            results.append(
                {
                    "transaction_id": str(row.id),
                    "description": row.description,
                    "amount": str(quantize(row.amount)),
                    "txn_date": row.txn_date.isoformat(),
                    "account_id": str(row.account_id),
                    "reason": "Same account, amount and a very similar description on a nearby date",
                }
            )
    return results[:5]


def _revert_matches(db: Session, txn: Transaction) -> None:
    matches = list(
        db.scalars(
            select(BillPaymentMatch).where(BillPaymentMatch.transaction_id == txn.id)
        )
    )
    occurrences: dict[uuid.UUID, BillOccurrence] = {}
    for match in matches:
        if match.status == MatchStatus.CONFIRMED.value:
            occurrence = db.get(BillOccurrence, match.occurrence_id)
            if occurrence is not None:
                occurrences[occurrence.id] = occurrence
        match.status = MatchStatus.REJECTED.value
        match.confirmed_at = None
    db.flush()
    for occurrence in occurrences.values():
        recompute_occurrence(db, occurrence)


def update_transaction(
    db: Session, user: User, txn_id: uuid.UUID, payload: TransactionUpdate
) -> Transaction:
    txn = get_transaction(db, user.id, txn_id)
    data = payload.model_dump(exclude_unset=True)
    significant = {"account_id", "amount", "txn_date", "tx_type", "merchant", "transfer_account_id"}
    match_affecting = bool(significant & set(data))

    if "account_id" in data and data["account_id"]:
        _get_account(db, user.id, data["account_id"])
    if data.get("transfer_account_id"):
        _get_account(db, user.id, data["transfer_account_id"])
    if "category_id" in data:
        _get_category(db, user.id, data["category_id"])

    new_type = data.get("tx_type", txn.tx_type)
    if hasattr(new_type, "value"):
        new_type = new_type.value
    new_transfer = data.get("transfer_account_id", txn.transfer_account_id)
    if new_type == TransactionType.TRANSFER.value and not new_transfer:
        raise ValidationError("Transfers require a destination account.")
    if new_type != TransactionType.TRANSFER.value and new_transfer:
        data["transfer_account_id"] = None
    if new_type == TransactionType.TRANSFER.value and data.get("category_id") is not None:
        raise ValidationError("Internal transfers do not belong to a spending category.")
    if new_type == TransactionType.TRANSFER.value:
        data["category_id"] = None

    if match_affecting:
        _revert_matches(db, txn)

    for field, value in data.items():
        if hasattr(value, "value"):
            value = value.value
        if field == "amount" and value is not None:
            value = quantize(value)
        if field in ("description", "merchant") and isinstance(value, str):
            value = value.strip()
        setattr(txn, field, value)

    _reject_future_posted(user, txn.txn_date, txn.status)
    if txn.transfer_account_id == txn.account_id:
        raise ValidationError("A transfer needs two different accounts.")
    if txn.source in (TransactionSource.CSV.value, TransactionSource.PROVIDER.value):
        txn.dedupe_key = transaction_fingerprint(
            account_id=txn.account_id,
            txn_date=txn.txn_date,
            amount=txn.amount,
            description=txn.description,
            merchant=txn.merchant,
            tx_type=txn.tx_type,
            external_id=txn.external_id,
        )
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("This edit would duplicate another transaction.") from exc

    if (
        match_affecting
        and txn.status == "posted"
        and txn.tx_type in (TransactionType.PURCHASE.value, TransactionType.BILL_PAYMENT.value)
    ):
        match_transaction(db, user, txn)
    return txn


def delete_transaction(db: Session, user: User, txn_id: uuid.UUID) -> None:
    txn = get_transaction(db, user.id, txn_id)
    _revert_matches(db, txn)
    db.delete(txn)
    db.flush()


def _apply_filters(query, user_id: uuid.UUID, params: TransactionListParams):
    query = query.where(Transaction.user_id == user_id)
    if params.account_id:
        query = query.where(
            or_(
                Transaction.account_id == params.account_id,
                Transaction.transfer_account_id == params.account_id,
            )
        )
    if params.category_id:
        query = query.where(Transaction.category_id == params.category_id)
    if params.tx_type:
        query = query.where(Transaction.tx_type == params.tx_type.value)
    if params.status:
        query = query.where(Transaction.status == params.status.value)
    if params.start_date:
        query = query.where(Transaction.txn_date >= params.start_date)
    if params.end_date:
        query = query.where(Transaction.txn_date <= params.end_date)
    if params.min_amount is not None:
        query = query.where(Transaction.amount >= params.min_amount)
    if params.max_amount is not None:
        query = query.where(Transaction.amount <= params.max_amount)
    if params.merchant:
        query = query.where(Transaction.merchant.ilike(f"%{params.merchant}%"))
    if params.search:
        term = f"%{params.search.strip()}%"
        query = query.where(
            or_(
                Transaction.description.ilike(term),
                Transaction.merchant.ilike(term),
                Transaction.notes.ilike(term),
            )
        )
    return query


def list_transactions(
    db: Session, user_id: uuid.UUID, params: TransactionListParams
) -> tuple[list[Transaction], int, dict[str, str]]:
    base = _apply_filters(select(Transaction), user_id, params)
    total = db.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0

    sort_field = params.sort.lstrip("-")
    column = SORTABLE.get(sort_field, Transaction.txn_date)
    ordering = column.desc() if params.sort.startswith("-") else column.asc()
    query = (
        base.options(
            joinedload(Transaction.account),
            joinedload(Transaction.transfer_account),
            joinedload(Transaction.category),
        )
        .order_by(ordering, Transaction.created_at.desc())
        .limit(params.limit)
        .offset(params.offset)
    )
    items = list(db.scalars(query))

    totals_query = _apply_filters(
        select(Transaction.tx_type, func.coalesce(func.sum(Transaction.amount), 0)),
        user_id,
        params,
    ).group_by(Transaction.tx_type)
    totals = {t.value: ZERO for t in TransactionType}
    for tx_type, value in db.execute(totals_query).all():
        totals[tx_type] = quantize(value or 0)
    income = totals[TransactionType.INCOME.value]
    spending = (
        totals[TransactionType.PURCHASE.value]
        + totals[TransactionType.BILL_PAYMENT.value]
        - totals[TransactionType.REFUND.value]
    )
    totals_out = {
        "income": str(quantize(income)),
        "spending": str(quantize(spending if spending > ZERO else ZERO)),
        "transfers": str(totals[TransactionType.TRANSFER.value]),
        "refunds": str(totals[TransactionType.REFUND.value]),
    }
    return items, int(total), totals_out


def serialize_transaction(txn: Transaction) -> dict[str, object]:
    return {
        "id": txn.id,
        "account_id": txn.account_id,
        "transfer_account_id": txn.transfer_account_id,
        "description": txn.description,
        "merchant": txn.merchant,
        "amount": txn.amount,
        "tx_type": txn.tx_type,
        "status": txn.status,
        "txn_date": txn.txn_date,
        "posting_date": txn.posting_date,
        "category_id": txn.category_id,
        "notes": txn.notes,
        "tags": txn.tags,
        "source": txn.source,
        "external_id": txn.external_id,
        "import_id": txn.import_id,
        "created_at": txn.created_at,
        "account_name": txn.account.name if txn.account else None,
        "transfer_account_name": txn.transfer_account.name if txn.transfer_account else None,
        "category_name": txn.category.name if txn.category else None,
        "category_color": txn.category.color if txn.category else None,
    }


def recent_transactions(db: Session, user_id: uuid.UUID, limit: int = 8) -> list[Transaction]:
    return list(
        db.scalars(
            select(Transaction)
            .options(
                joinedload(Transaction.account),
                joinedload(Transaction.category),
                joinedload(Transaction.transfer_account),
            )
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.txn_date.desc(), Transaction.created_at.desc())
            .limit(limit)
        )
    )


def transaction_amount_for_stats(tx_type: str, amount: Decimal) -> Decimal:
    """Utility used by tests and forecasts; transfers never affect income/spending."""
    if tx_type == TransactionType.TRANSFER.value:
        return ZERO
    if tx_type in (TransactionType.PURCHASE.value, TransactionType.BILL_PAYMENT.value):
        return -amount
    if tx_type in (TransactionType.INCOME.value, TransactionType.REFUND.value):
        return amount
    return ZERO
