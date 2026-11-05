"""Model registry: import all models so metadata and Alembic see them."""

from app.database.base import Base
from app.models.account import BalanceAdjustment, Category, FinancialAccount
from app.models.bill import Bill, BillOccurrence, BillPaymentMatch, MerchantAlias
from app.models.budget import Budget, BudgetAllocation, PlannedReserve
from app.models.import_job import ImportRecord, TransactionImport
from app.models.transaction import Transaction
from app.models.user import IncomeSource, NotificationPreference, User, UserPreference

__all__ = [
    "Base",
    "BalanceAdjustment",
    "Bill",
    "BillOccurrence",
    "BillPaymentMatch",
    "Budget",
    "BudgetAllocation",
    "Category",
    "FinancialAccount",
    "ImportRecord",
    "IncomeSource",
    "MerchantAlias",
    "NotificationPreference",
    "PlannedReserve",
    "Transaction",
    "TransactionImport",
    "User",
    "UserPreference",
]
