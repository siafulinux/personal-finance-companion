"""User registration, onboarding, preferences, data export and deletion."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    BalanceAdjustment,
    Bill,
    BudgetAllocation,
    BillOccurrence,
    BillPaymentMatch,
    Budget,
    Category,
    FinancialAccount,
    ImportRecord,
    IncomeSource,
    MerchantAlias,
    NotificationPreference,
    PlannedReserve,
    Transaction,
    TransactionImport,
    User,
    UserPreference,
)
from app.models.enums import AccountType, IncomeFrequency
from app.schemas.auth import (
    IncomeSourceCreate,
    IncomeSourceUpdate,
    NotificationPreferencesUpdate,
    OnboardingRequest,
    PreferencesUpdate,
)
from app.security.passwords import (
    hash_password,
    needs_rehash,
    validate_password_strength,
    verify_password,
)
from app.services.categories import seed_default_categories
from app.services.errors import AuthenticationError, ConflictError, NotFoundError, ValidationError
from app.utils.dates import today_in, utc_now
from app.utils.money import ZERO, quantize


def validate_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationError(f"Unknown timezone: {name}") from exc
    return name


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))


def get_user(db: Session, user_id: uuid.UUID) -> User | None:
    return db.scalar(
        select(User).where(User.id == user_id, User.is_active.is_(True), User.deleted_at.is_(None))
    )


def register_user(
    db: Session,
    *,
    email: str,
    password: str,
    display_name: str,
    timezone: str,
    currency: str = "USD",
) -> User:
    validate_password_strength(password)
    validate_timezone(timezone)
    normalized = email.strip().lower()
    if get_user_by_email(db, normalized) is not None:
        raise ConflictError("An account with that email already exists.")
    user = User(
        email=normalized,
        password_hash=hash_password(password),
        display_name=display_name.strip(),
        timezone=timezone,
        currency="USD",
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("An account with that email already exists.") from exc
    db.add(UserPreference(user_id=user.id, minimum_balance_buffer=ZERO))
    db.add(NotificationPreference(user_id=user.id))
    seed_default_categories(db, user.id)
    db.flush()
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        raise AuthenticationError("Incorrect email or password.")
    if user.deleted_at is not None or not user.is_active:
        raise AuthenticationError("This account is not available.")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = utc_now()
    db.flush()
    return user


def update_profile(db: Session, user: User, *, display_name: str | None, timezone: str | None) -> User:
    if display_name is not None:
        user.display_name = display_name.strip()
    if timezone is not None:
        user.timezone = validate_timezone(timezone)
    db.flush()
    return user


def get_preferences(db: Session, user_id: uuid.UUID) -> UserPreference:
    prefs = db.get(UserPreference, user_id)
    if prefs is None:
        prefs = UserPreference(user_id=user_id)
        db.add(prefs)
        db.flush()
    return prefs


def get_notification_preferences(db: Session, user_id: uuid.UUID) -> NotificationPreference:
    prefs = db.get(NotificationPreference, user_id)
    if prefs is None:
        prefs = NotificationPreference(user_id=user_id)
        db.add(prefs)
        db.flush()
    return prefs


def update_preferences(
    db: Session, user_id: uuid.UUID, payload: PreferencesUpdate
) -> UserPreference:
    prefs = get_preferences(db, user_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("safe_to_spend_horizon_days"):
        data["safe_to_spend_horizon_days"] = min(
            data["safe_to_spend_horizon_days"], settings.max_safe_to_spend_horizon_days
        )
    for field, value in data.items():
        if hasattr(value, "value"):
            value = value.value
        setattr(prefs, field, value)
    db.flush()
    if prefs.suggestion_threshold >= prefs.auto_match_threshold:
        raise ValidationError(
            "The suggestion threshold must be lower than the auto-match threshold."
        )
    return prefs


def update_notification_preferences(
    db: Session, user_id: uuid.UUID, payload: NotificationPreferencesUpdate
) -> NotificationPreference:
    prefs = get_notification_preferences(db, user_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(prefs, field, value)
    db.flush()
    return prefs


def profile_payload(db: Session, user: User) -> dict[str, object]:
    return {
        "user": user,
        "preferences": get_preferences(db, user.id),
        "notification_preferences": get_notification_preferences(db, user.id),
    }


def complete_onboarding(db: Session, user: User, payload: OnboardingRequest) -> User:
    validate_timezone(payload.timezone)
    user.display_name = payload.display_name.strip()
    user.timezone = payload.timezone
    user.currency = "USD"
    prefs = get_preferences(db, user.id)
    prefs.minimum_balance_buffer = quantize(payload.minimum_balance_buffer)
    seed_default_categories(db, user.id)

    existing_accounts = db.scalar(
        select(func.count(FinancialAccount.id)).where(FinancialAccount.user_id == user.id)
    )
    if not existing_accounts:
        if payload.accounts:
            for item in payload.accounts:
                account_type = item.account_type
                if account_type not in {t.value for t in AccountType}:
                    raise ValidationError(f"Unknown account type: {account_type}")
                db.add(
                    FinancialAccount(
                        user_id=user.id,
                        name=item.name.strip(),
                        account_type=account_type,
                        opening_balance=quantize(item.opening_balance),
                        opening_balance_date=today_in(payload.timezone),
                        include_in_safe_to_spend=(
                            item.include_in_safe_to_spend
                            and account_type != AccountType.CREDIT_CARD.value
                        ),
                    )
                )
        else:
            db.add(
                FinancialAccount(
                    user_id=user.id,
                    name="Everyday Checking",
                    account_type=AccountType.CHECKING.value,
                    opening_balance=quantize(payload.starting_balance),
                    opening_balance_date=today_in(payload.timezone),
                    include_in_safe_to_spend=True,
                    description="Created during onboarding",
                )
            )
        db.flush()

    if payload.income_amount and payload.income_frequency:
        db.add(
            IncomeSource(
                user_id=user.id,
                name="Primary income",
                amount=quantize(payload.income_amount),
                frequency=payload.income_frequency.value,
                next_payday=payload.next_payday,
                is_active=True,
            )
        )
        if payload.seed_budget:
            _seed_first_budget(db, user, payload)
    user.onboarding_completed_at = utc_now()
    db.flush()
    return user


def _seed_first_budget(db: Session, user: User, payload: OnboardingRequest) -> None:
    """A deliberately small starting budget: 10% savings, everything else unallocated."""
    from app.models import Budget, BudgetAllocation
    from app.utils.dates import month_bounds

    today = today_in(user.timezone)
    first, _ = month_bounds(today.year, today.month)
    existing = db.scalar(
        select(Budget).where(
            Budget.user_id == user.id, Budget.year == today.year, Budget.month == today.month
        )
    )
    if existing or not payload.income_amount:
        return
    savings = db.scalar(
        select(Category).where(Category.user_id == user.id, Category.name == "Savings")
    )
    budget = Budget(
        user_id=user.id,
        year=today.year,
        month=today.month,
        name="First budget",
        notes="Starting point created during onboarding. Adjust it to match your priorities.",
    )
    db.add(budget)
    db.flush()
    if savings:
        allocation = quantize(quantize(payload.income_amount) * Decimal("0.10"))
        db.add(
            BudgetAllocation(
                budget_id=budget.id,
                category_id=savings.id,
                amount=allocation,
                carryover_enabled=False,
            )
        )


def add_income_source(
    db: Session, user_id: uuid.UUID, payload: IncomeSourceCreate
) -> IncomeSource:
    if payload.account_id:
        account = db.scalar(
            select(FinancialAccount).where(
                FinancialAccount.id == payload.account_id, FinancialAccount.user_id == user_id
            )
        )
        if account is None:
            raise ValidationError("The selected account does not exist.")
    source = IncomeSource(
        user_id=user_id,
        name=payload.name.strip(),
        amount=quantize(payload.amount),
        frequency=payload.frequency.value,
        next_payday=payload.next_payday,
        account_id=payload.account_id,
        notes=payload.notes,
    )
    db.add(source)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("An income source with that name already exists.") from exc
    return source


def list_income_sources(db: Session, user_id: uuid.UUID) -> list[IncomeSource]:
    return list(
        db.scalars(
            select(IncomeSource)
            .where(IncomeSource.user_id == user_id)
            .order_by(IncomeSource.created_at)
        )
    )


def update_income_source(
    db: Session, user_id: uuid.UUID, source_id: uuid.UUID, payload: IncomeSourceUpdate
) -> IncomeSource:
    source = db.scalar(
        select(IncomeSource).where(
            IncomeSource.id == source_id, IncomeSource.user_id == user_id
        )
    )
    if source is None:
        raise NotFoundError("Income source not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if hasattr(value, "value"):
            value = value.value
        if field == "amount" and value is not None:
            value = quantize(value)
        setattr(source, field, value)
    db.flush()
    return source


def delete_income_source(db: Session, user_id: uuid.UUID, source_id: uuid.UUID) -> None:
    source = db.scalar(
        select(IncomeSource).where(
            IncomeSource.id == source_id, IncomeSource.user_id == user_id
        )
    )
    if source is None:
        raise NotFoundError("Income source not found.")
    db.delete(source)
    db.flush()


def _iso(value):
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, (date,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def export_user_data(db: Session, user: User) -> dict[str, object]:
    """Complete, machine-readable export of everything owned by a user."""
    accounts = list(
        db.scalars(select(FinancialAccount).where(FinancialAccount.user_id == user.id))
    )
    account_ids = [a.id for a in accounts]
    transactions = list(
        db.scalars(select(Transaction).where(Transaction.user_id == user.id))
    )
    categories = list(db.scalars(select(Category).where(Category.user_id == user.id)))
    budgets = list(db.scalars(select(Budget).where(Budget.user_id == user.id)))
    allocations = db.scalars(
        select(BudgetAllocation).where(
            BudgetAllocation.budget_id.in_([b.id for b in budgets])
        )
    ).all()
    bills = list(db.scalars(select(Bill).where(Bill.user_id == user.id)))
    occurrences = list(
        db.scalars(select(BillOccurrence).where(BillOccurrence.user_id == user.id))
    )
    matches = list(
        db.scalars(select(BillPaymentMatch).where(BillPaymentMatch.user_id == user.id))
    )
    imports = list(
        db.scalars(select(TransactionImport).where(TransactionImport.user_id == user.id))
    )
    import_records = db.scalars(
        select(ImportRecord).where(ImportRecord.import_id.in_([i.id for i in imports]))
    ).all()
    reserves = list(
        db.scalars(select(PlannedReserve).where(PlannedReserve.user_id == user.id))
    )
    income = list(
        db.scalars(select(IncomeSource).where(IncomeSource.user_id == user.id))
    )
    aliases = list(
        db.scalars(select(MerchantAlias).where(MerchantAlias.user_id == user.id))
    )
    prefs = get_preferences(db, user.id)
    notifications = get_notification_preferences(db, user.id)

    def rows(items, fields):
        return [{f: _iso(getattr(item, f)) for f in fields} for item in items]

    return {
        "exported_at": utc_now().isoformat(),
        "user": {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "timezone": user.timezone,
            "currency": user.currency,
            "created_at": _iso(user.created_at),
        },
        "preferences": {
            "minimum_balance_buffer": _iso(prefs.minimum_balance_buffer),
            "safe_to_spend_horizon_days": prefs.safe_to_spend_horizon_days,
            "auto_bill_matching": prefs.auto_bill_matching,
        },
        "accounts": rows(
            accounts,
            [
                "id",
                "name",
                "account_type",
                "opening_balance",
                "opening_balance_date",
                "currency",
                "include_in_safe_to_spend",
                "credit_limit",
                "description",
                "is_archived",
            ],
        ),
        "categories": rows(
            categories, ["id", "name", "kind", "color", "is_archived", "sort_order"]
        ),
        "transactions": rows(
            transactions,
            [
                "id",
                "account_id",
                "transfer_account_id",
                "description",
                "merchant",
                "amount",
                "tx_type",
                "status",
                "txn_date",
                "posting_date",
                "category_id",
                "notes",
                "tags",
                "source",
                "external_id",
            ],
        ),
        "budgets": [
            {
                "id": str(b.id),
                "year": b.year,
                "month": b.month,
                "name": b.name,
                "notes": b.notes,
                "allocations": [
                    {
                        "category_id": str(a.category_id),
                        "amount": _iso(a.amount),
                        "carryover_enabled": a.carryover_enabled,
                    }
                    for a in allocations
                    if a.budget_id == b.id
                ],
            }
            for b in budgets
        ],
        "bills": rows(
            bills,
            [
                "id",
                "name",
                "merchant",
                "expected_amount",
                "minimum_amount",
                "due_day",
                "anchor_date",
                "frequency",
                "custom_interval_days",
                "account_id",
                "category_id",
                "is_essential",
                "reserve_in_safe_to_spend",
                "is_active",
                "notes",
            ],
        ),
        "bill_occurrences": rows(
            occurrences,
            ["id", "bill_id", "due_date", "expected_amount", "paid_amount", "status"],
        ),
        "bill_payment_matches": rows(
            matches,
            [
                "id",
                "occurrence_id",
                "transaction_id",
                "amount",
                "confidence",
                "status",
                "is_automatic",
                "reason",
            ],
        ),
        "imports": rows(
            imports,
            [
                "id",
                "filename",
                "status",
                "row_count",
                "imported_count",
                "duplicate_count",
                "rejected_count",
                "created_at",
            ],
        ),
        "import_records": rows(
            import_records, ["import_id", "row_number", "status", "reason", "transaction_id"]
        ),
        "income_sources": rows(
            income, ["id", "name", "amount", "frequency", "next_payday", "is_active"]
        ),
        "merchant_aliases": rows(aliases, ["id", "alias", "canonical_merchant"]),
        "reserves": rows(
            reserves,
            [
                "id",
                "name",
                "amount",
                "is_savings",
                "start_date",
                "end_date",
                "is_active",
            ],
        ),
        "notification_preferences": {
            "shopping_assistant_enabled": notifications.shopping_assistant_enabled,
            "bill_reminders_enabled": notifications.bill_reminders_enabled,
            "low_money_warnings_enabled": notifications.low_money_warnings_enabled,
            "quiet_hours_start": notifications.quiet_hours_start,
            "quiet_hours_end": notifications.quiet_hours_end,
        },
        "counts": {
            "accounts": len(accounts),
            "transactions": len(transactions),
            "bills": len(bills),
            "budgets": len(budgets),
            "imports": len(imports),
        },
        "account_ids": [str(i) for i in account_ids],
    }


def delete_user_account(db: Session, user: User, password: str, confirm: str) -> None:
    if confirm != "DELETE":
        raise ValidationError("Type DELETE exactly to confirm permanent deletion.")
    if not verify_password(password, user.password_hash):
        raise AuthenticationError("Password is incorrect.")
    # Delete in dependency order so financial history cannot block the cascade.
    db.execute(sa_delete(ImportRecord).where(ImportRecord.import_id.in_(
        select(TransactionImport.id).where(TransactionImport.user_id == user.id)
    )))
    db.execute(sa_delete(BillPaymentMatch).where(BillPaymentMatch.user_id == user.id))
    db.execute(sa_delete(BillOccurrence).where(BillOccurrence.user_id == user.id))
    db.execute(sa_delete(Bill).where(Bill.user_id == user.id))
    db.execute(sa_delete(Transaction).where(Transaction.user_id == user.id))
    db.execute(sa_delete(TransactionImport).where(TransactionImport.user_id == user.id))
    db.execute(sa_delete(PlannedReserve).where(PlannedReserve.user_id == user.id))
    db.execute(sa_delete(FinancialAccount).where(FinancialAccount.user_id == user.id))
    db.execute(sa_delete(BalanceAdjustment).where(BalanceAdjustment.user_id == user.id))
    db.execute(sa_delete(IncomeSource).where(IncomeSource.user_id == user.id))
    db.execute(sa_delete(MerchantAlias).where(MerchantAlias.user_id == user.id))
    budgets = list(db.scalars(select(Budget).where(Budget.user_id == user.id)))
    for budget in budgets:
        db.delete(budget)
    db.execute(sa_delete(Category).where(Category.user_id == user.id))
    db.execute(sa_delete(UserPreference).where(UserPreference.user_id == user.id))
    db.execute(sa_delete(NotificationPreference).where(NotificationPreference.user_id == user.id))
    db.delete(user)
    db.flush()
