"""password change ends existing sessions

Revision ID: c4b1d2e6f7a8
Revises: a7804f0fa670
Create Date: 2026-11-07 18:05:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'c4b1d2e6f7a8'
down_revision: str | None = 'a7804f0fa670'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Access tokens carry this number; a password change increments it and every
    # token minted with an older value stops being accepted. Existing accounts
    # start at 0, which is the version their tokens already carry, so deploying
    # this does not sign anyone out.
    op.add_column(
        'users',
        sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('users', 'token_version')
