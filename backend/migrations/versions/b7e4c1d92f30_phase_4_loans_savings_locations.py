"""Phase 4: loans, savings goals, shopping locations and visits.

Additive only. Existing account, bill, budget and transaction rows are untouched;
the two new account/preference columns are nullable or defaulted so an existing
installation keeps working without a data migration.

Revision ID: b7e4c1d92f30
Revises: 3f2c9a71b4d8
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e4c1d92f30"
down_revision: str | None = "3f2c9a71b4d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOAN_TYPE = sa.Enum(
    "personal",
    "payday",
    "cash_advance",
    "earned_wage_access",
    "buy_now_pay_later",
    "installment",
    "credit_agreement",
    "other",
    name="loan_type_enum",
    native_enum=False,
    length=40,
)
BALANCE_SOURCE = sa.Enum(
    "user", "provider", "derived", name="loan_balance_source_enum", native_enum=False, length=40
)
LOAN_STATUS = sa.Enum(
    "active", "paid_off", "defaulted", name="loan_status_enum", native_enum=False, length=40
)
LOAN_FREQUENCY = sa.Enum(
    "weekly",
    "biweekly",
    "monthly",
    "every_two_months",
    "quarterly",
    "semiannual",
    "annual",
    "custom",
    name="loan_frequency_enum",
    native_enum=False,
    length=40,
)
MATCH_STATUS = sa.Enum(
    "suggested",
    "confirmed",
    "rejected",
    name="loan_payment_status_enum",
    native_enum=False,
    length=40,
)
SAVINGS_MODE = sa.Enum(
    "virtual", "account", name="savings_mode_enum", native_enum=False, length=40
)
SAVINGS_STATUS = sa.Enum(
    "active", "completed", "archived", name="savings_status_enum", native_enum=False, length=40
)
SAVINGS_FREQUENCY = sa.Enum(
    "weekly",
    "biweekly",
    "monthly",
    "every_two_months",
    "quarterly",
    "semiannual",
    "annual",
    "custom",
    name="savings_frequency_enum",
    native_enum=False,
    length=40,
)
LOCATION_SOURCE = sa.Enum(
    "geofence", "discovery", "manual", name="location_source_enum", native_enum=False, length=40
)
VISIT_SOURCE = sa.Enum(
    "geofence", "discovery", "manual", name="visit_source_enum", native_enum=False, length=40
)
VISIT_STATUS = sa.Enum(
    "detected",
    "suggested",
    "confirmed",
    "ignored",
    name="visit_status_enum",
    native_enum=False,
    length=40,
)


def upgrade() -> None:
    op.add_column("financial_accounts", sa.Column("minimum_payment", sa.Numeric(18, 2), nullable=True))

    for column in (
        sa.Column(
            "shopping_intelligence_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("discovery_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "notification_cooldown_minutes", sa.Integer(), nullable=False, server_default="120"
        ),
        sa.Column(
            "visit_history_retention_days", sa.Integer(), nullable=False, server_default="90"
        ),
        sa.Column("location_paused_until", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("notification_preferences", column)

    op.create_table(
        "loans",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("lender", sa.String(length=120), nullable=True),
        sa.Column("loan_type", LOAN_TYPE, server_default="personal", nullable=False),
        sa.Column("original_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("opening_balance", sa.Numeric(18, 2), nullable=False),
        sa.Column("balance_as_of", sa.Date(), nullable=False),
        sa.Column("balance_source", BALANCE_SOURCE, server_default="user", nullable=False),
        sa.Column("apr", sa.Numeric(12, 4), nullable=True),
        sa.Column("interest_charged", sa.Numeric(18, 2), nullable=True),
        sa.Column("fees_charged", sa.Numeric(18, 2), nullable=True),
        sa.Column("next_payment_date", sa.Date(), nullable=True),
        sa.Column("scheduled_payment", sa.Numeric(18, 2), nullable=True),
        sa.Column("payment_frequency", LOAN_FREQUENCY, nullable=True),
        sa.Column("remaining_payments", sa.Integer(), nullable=True),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("category_id", sa.UUID(), nullable=True),
        sa.Column("status", LOAN_STATUS, server_default="active", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("original_amount > 0", name=op.f("ck_loans_original_amount_positive")),
        sa.CheckConstraint(
            "opening_balance >= 0", name=op.f("ck_loans_opening_balance_non_negative")
        ),
        sa.CheckConstraint("apr IS NULL OR apr >= 0", name=op.f("ck_loans_apr_non_negative")),
        sa.CheckConstraint(
            "scheduled_payment IS NULL OR scheduled_payment > 0",
            name=op.f("ck_loans_scheduled_payment_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_loans_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["financial_accounts.id"],
            name=op.f("fk_loans_account_id_financial_accounts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_loans_category_id_categories"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_loans")),
        sa.UniqueConstraint("user_id", "name", name="uq_loans_user_name"),
    )
    op.create_index("ix_loans_user_status", "loans", ["user_id", "status"], unique=False)

    op.create_table(
        "loan_payments",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("loan_id", sa.UUID(), nullable=False),
        sa.Column("transaction_id", sa.UUID(), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("principal_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("interest_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("fee_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("status", MATCH_STATUS, server_default="confirmed", nullable=False),
        sa.Column("confidence", sa.Numeric(12, 4), server_default="1.000", nullable=False),
        sa.Column("is_automatic", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_ambiguous", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "amount > 0", name=op.f("ck_loan_payments_loan_payment_amount_positive")
        ),
        sa.CheckConstraint(
            "principal_amount IS NULL OR principal_amount >= 0",
            name=op.f("ck_loan_payments_principal_non_negative"),
        ),
        sa.CheckConstraint(
            "interest_amount IS NULL OR interest_amount >= 0",
            name=op.f("ck_loan_payments_interest_non_negative"),
        ),
        sa.CheckConstraint(
            "fee_amount IS NULL OR fee_amount >= 0", name=op.f("ck_loan_payments_fee_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_loan_payments_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["loan_id"],
            ["loans.id"],
            name=op.f("fk_loan_payments_loan_id_loans"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name=op.f("fk_loan_payments_transaction_id_transactions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_loan_payments")),
    )
    op.create_index("ix_loan_payments_user_paid", "loan_payments", ["user_id", "paid_on"])
    op.create_index("ix_loan_payments_loan_status", "loan_payments", ["loan_id", "status"])
    op.create_index(
        "uq_loan_payments_transaction",
        "loan_payments",
        ["transaction_id"],
        unique=True,
        postgresql_where=sa.text("transaction_id IS NOT NULL"),
    )

    op.create_table(
        "savings_goals",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("target_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("mode", SAVINGS_MODE, server_default="virtual", nullable=False),
        sa.Column("saved_amount", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("category_id", sa.UUID(), nullable=True),
        sa.Column("contribution_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("contribution_frequency", SAVINGS_FREQUENCY, nullable=True),
        sa.Column("status", SAVINGS_STATUS, server_default="active", nullable=False),
        sa.Column("color", sa.String(length=9), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "target_amount > 0", name=op.f("ck_savings_goals_savings_target_positive")
        ),
        sa.CheckConstraint(
            "saved_amount >= 0", name=op.f("ck_savings_goals_savings_saved_non_negative")
        ),
        sa.CheckConstraint(
            "contribution_amount IS NULL OR contribution_amount > 0",
            name=op.f("ck_savings_goals_savings_contribution_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_savings_goals_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["financial_accounts.id"],
            name=op.f("fk_savings_goals_account_id_financial_accounts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_savings_goals_category_id_categories"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_savings_goals")),
        sa.UniqueConstraint("user_id", "name", name="uq_savings_goals_user_name"),
    )
    op.create_index("ix_savings_goals_user_status", "savings_goals", ["user_id", "status"])

    op.create_table(
        "savings_contributions",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("goal_id", sa.UUID(), nullable=False),
        sa.Column("transaction_id", sa.UUID(), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("contributed_on", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_transfer_recorded", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "amount > 0", name=op.f("ck_savings_contributions_contribution_amount_positive")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_savings_contributions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["goal_id"],
            ["savings_goals.id"],
            name=op.f("fk_savings_contributions_goal_id_savings_goals"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name=op.f("fk_savings_contributions_transaction_id_transactions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_savings_contributions")),
    )
    op.create_index(
        "ix_savings_contributions_goal_date",
        "savings_contributions",
        ["goal_id", "contributed_on"],
    )

    op.create_table(
        "insight_dismissals",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column(
            "dismissed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_insight_dismissals_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_insight_dismissals")),
        sa.UniqueConstraint("user_id", "key", name="uq_insight_dismissals_user_key"),
    )

    op.create_table(
        "tracked_locations",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("merchant", sa.String(length=160), nullable=True),
        sa.Column("merchant_key", sa.String(length=160), nullable=True),
        sa.Column("address", sa.String(length=240), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("radius_m", sa.Integer(), server_default="150", nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=True),
        sa.Column("monthly_budget", sa.Numeric(18, 2), nullable=True),
        sa.Column("notify_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("source", LOCATION_SOURCE, server_default="manual", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name=op.f("ck_tracked_locations_tracked_latitude_range"),
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name=op.f("ck_tracked_locations_tracked_longitude_range"),
        ),
        sa.CheckConstraint(
            "radius_m BETWEEN 50 AND 2000", name=op.f("ck_tracked_locations_tracked_radius_range")
        ),
        sa.CheckConstraint(
            "monthly_budget IS NULL OR monthly_budget >= 0",
            name=op.f("ck_tracked_locations_tracked_budget_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_tracked_locations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_tracked_locations_category_id_categories"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tracked_locations")),
        sa.UniqueConstraint("user_id", "name", name="uq_tracked_locations_user_name"),
    )
    op.create_index(
        "ix_tracked_locations_user_active", "tracked_locations", ["user_id", "is_active"]
    )

    op.create_table(
        "shopping_visits",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("tracked_location_id", sa.UUID(), nullable=True),
        sa.Column("business_name", sa.String(length=160), nullable=False),
        sa.Column("merchant_key", sa.String(length=160), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=True),
        sa.Column("visited_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("visit_day", sa.Date(), nullable=False),
        sa.Column("status", VISIT_STATUS, server_default="detected", nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), server_default="1.000", nullable=False),
        sa.Column("distance_m", sa.Integer(), nullable=True),
        sa.Column("source", VISIT_SOURCE, server_default="geofence", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_shopping_visits_visit_confidence_range"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_shopping_visits_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tracked_location_id"],
            ["tracked_locations.id"],
            name=op.f("fk_shopping_visits_tracked_location_id_tracked_locations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_shopping_visits_category_id_categories"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shopping_visits")),
        sa.UniqueConstraint(
            "user_id", "merchant_key", "visit_day", name="uq_shopping_visits_user_place_day"
        ),
    )
    op.create_index("ix_shopping_visits_user_visited", "shopping_visits", ["user_id", "visited_at"])
    op.create_index("ix_shopping_visits_user_status", "shopping_visits", ["user_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_shopping_visits_user_status", table_name="shopping_visits")
    op.drop_index("ix_shopping_visits_user_visited", table_name="shopping_visits")
    op.drop_table("shopping_visits")
    op.drop_index("ix_tracked_locations_user_active", table_name="tracked_locations")
    op.drop_table("tracked_locations")
    op.drop_table("insight_dismissals")
    op.drop_index("ix_savings_contributions_goal_date", table_name="savings_contributions")
    op.drop_table("savings_contributions")
    op.drop_index("ix_savings_goals_user_status", table_name="savings_goals")
    op.drop_table("savings_goals")
    op.drop_index("uq_loan_payments_transaction", table_name="loan_payments")
    op.drop_index("ix_loan_payments_loan_status", table_name="loan_payments")
    op.drop_index("ix_loan_payments_user_paid", table_name="loan_payments")
    op.drop_table("loan_payments")
    op.drop_index("ix_loans_user_status", table_name="loans")
    op.drop_table("loans")
    for name in (
        "location_paused_until",
        "visit_history_retention_days",
        "notification_cooldown_minutes",
        "discovery_enabled",
        "shopping_intelligence_enabled",
    ):
        op.drop_column("notification_preferences", name)
    op.drop_column("financial_accounts", "minimum_payment")
