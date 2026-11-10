"""Model registry: import all models so metadata and Alembic see them."""

from app.database.base import Base
from app.models.account import BalanceAdjustment, Category, FinancialAccount
from app.models.bill import Bill, BillOccurrence, BillPaymentMatch, MerchantAlias
from app.models.budget import Budget, BudgetAllocation, PlannedReserve
from app.models.connectivity import (
    CategorySuggestion,
    ProviderLink,
    ProviderLinkSecret,
    RecurringSeries,
    SyncRun,
)
from app.models.import_job import ImportRecord, TransactionImport
from app.models.loan import Loan, LoanPayment
from app.models.location import ShoppingVisit, TrackedLocation
from app.models.provider import PROVIDER_NAMES, ProviderConfig
from app.models.savings import InsightDismissal, SavingsContribution, SavingsGoal
from app.models.server import PairingToken, ServerSettings
from app.models.transaction import Transaction
from app.models.user import (
    IncomeSource,
    NotificationPreference,
    RevokedToken,
    User,
    UserPreference,
)

__all__ = [
    "Base",
    "BalanceAdjustment",
    "Bill",
    "BillOccurrence",
    "BillPaymentMatch",
    "Budget",
    "BudgetAllocation",
    "Category",
    "CategorySuggestion",
    "FinancialAccount",
    "ImportRecord",
    "IncomeSource",
    "InsightDismissal",
    "Loan",
    "LoanPayment",
    "MerchantAlias",
    "NotificationPreference",
    "PROVIDER_NAMES",
    "PairingToken",
    "PlannedReserve",
    "ProviderConfig",
    "ProviderLink",
    "ProviderLinkSecret",
    "RecurringSeries",
    "RevokedToken",
    "SavingsContribution",
    "SavingsGoal",
    "ServerSettings",
    "ShoppingVisit",
    "SyncRun",
    "TrackedLocation",
    "Transaction",
    "TransactionImport",
    "User",
    "UserPreference",
]
