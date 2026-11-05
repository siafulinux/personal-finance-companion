"""Lightweight, permission-scoped lookups shared by forecasts and AI tools."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FinancialAccount, User
from app.models.enums import AccountType
from app.services.balances import balances_for_accounts
from app.utils.money import ZERO, quantize


def eligible_cash_available(db: Session, user: User) -> Decimal:
    """Posted balance of accounts that contribute to Safe-to-Spend.

    Credit-card liabilities are never included, and archives are ignored.
    """
    accounts = list(
        db.scalars(
            select(FinancialAccount).where(
                FinancialAccount.user_id == user.id,
                FinancialAccount.is_archived.is_(False),
                FinancialAccount.include_in_safe_to_spend.is_(True),
            )
        )
    )
    accounts = [a for a in accounts if a.account_type != AccountType.CREDIT_CARD.value]
    balances = balances_for_accounts(db, user.id)
    total = sum((balances[a.id].posted_balance for a in accounts if a.id in balances), ZERO)
    return quantize(total)
