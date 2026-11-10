"""Administrator-managed provider configuration.

Adds ``provider_configs`` and the server-level ``provider_auto_select`` switch.

The table stores credentials as ciphertext in a nullable column: an installation that
configures providers purely through environment variables has rows (for priority and
enablement) with no ciphertext at all, and the service falls back to the environment.

Revision ID: 3f2c9a71b4d8
Revises: c4b1d2e6f7a8
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "3f2c9a71b4d8"
down_revision: str | None = "c4b1d2e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_configs",
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("environment", sa.String(length=20), nullable=False, server_default="sandbox"),
        sa.Column("credentials_ciphertext", sa.Text(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=True),
        sa.Column("last_test_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("name"),
    )
    # Teller primary, Plaid secondary. Seeded here so a fresh install has a usable
    # order before anyone opens the admin screen; credentials are not seeded.
    op.execute(
        """
        INSERT INTO provider_configs (name, enabled, priority, environment)
        VALUES ('teller', true, 10, 'sandbox'), ('plaid', true, 20, 'sandbox')
        ON CONFLICT (name) DO NOTHING
        """
    )
    op.add_column(
        "server_settings",
        sa.Column(
            "provider_auto_select",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("server_settings", "provider_auto_select")
    op.drop_table("provider_configs")
