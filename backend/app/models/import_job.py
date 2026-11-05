"""CSV import sessions and per-row outcomes (auditable, retry-safe)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey, str_enum
from app.models.enums import ImportRowStatus, ImportStatus


class TransactionImport(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "transaction_imports"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    delimiter: Mapped[str] = mapped_column(String(3), nullable=False, server_default=",")
    has_header: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    status: Mapped[str] = mapped_column(
        str_enum(ImportStatus, "import_status_enum"),
        nullable=False,
        server_default=ImportStatus.UPLOADED.value,
    )
    column_mapping: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_rows: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    records: Mapped[list["ImportRecord"]] = relationship(
        back_populates="import_job", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_transaction_imports_user_created", "user_id", "created_at"),
        Index("ix_transaction_imports_sha", "user_id", "account_id", "file_sha256"),
    )


class ImportRecord(Base, UUIDPrimaryKey):
    __tablename__ = "import_records"

    import_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transaction_imports.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(
        str_enum(ImportRowStatus, "import_row_status_enum"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    import_job: Mapped[TransactionImport] = relationship(back_populates="records")

    __table_args__ = (Index("ix_import_records_import", "import_id", "row_number"),)
