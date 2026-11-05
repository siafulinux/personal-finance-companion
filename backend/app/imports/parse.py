"""CSV parsing primitives. Pure functions, independently testable."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

MAX_ROWS = 5000
MAX_FILE_BYTES = 5 * 1024 * 1024

DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%b %d, %Y",
    "%d %b %Y",
    "%d-%b-%Y",
    "%B %d, %Y",
    "%d-%B-%Y",
)

_TYPE_ALIASES = {
    "refund": "refund",
    "return": "refund",
    "reversal": "refund",
    "income": "income",
    "deposit": "income",
    "salary": "income",
    "paycheck": "income",
    "payment": "bill_payment",
    "bill": "bill_payment",
    "bill_payment": "bill_payment",
    "purchase": "purchase",
    "sale": "purchase",
    "debit": "purchase",
    "withdrawal": "purchase",
    "expense": "purchase",
    "fee": "purchase",
}

_TRANSFER_WORDS = ("transfer", "xfer", "move to", "move from")


class CsvError(ValueError):
    pass


@dataclass
class CsvDocument:
    headers: list[str]
    rows: list[dict[str, str]]
    delimiter: str
    has_header: bool
    encoding: str


@dataclass
class ParsedRow:
    row_number: int
    raw: dict[str, str]
    txn_date: date | None = None
    description: str = ""
    merchant: str | None = None
    amount: Decimal | None = None
    signed_amount: Decimal | None = None
    tx_type: str | None = None
    external_id: str | None = None
    status: str = "ok"  # ok | duplicate | error
    reason: str | None = None
    duplicate_of: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "row_number": self.row_number,
            "date": self.txn_date.isoformat() if self.txn_date else None,
            "description": self.description,
            "merchant": self.merchant,
            "amount": str(self.amount) if self.amount is not None else None,
            "signed_amount": str(self.signed_amount) if self.signed_amount is not None else None,
            "suggested_type": self.tx_type,
            "external_id": self.external_id,
            "status": self.status,
            "reason": self.reason,
            "duplicate_of": self.duplicate_of,
            "raw": self.raw,
        }


def decode_content(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CsvError("The file could not be decoded as text.")


def sniff_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample[:8192], delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        counts = {d: sample.count(d) for d in (",", ";", "\t", "|")}
        best = max(counts, key=counts.get)
        return best if counts[best] > 0 else ","


def parse_csv(content: bytes) -> CsvDocument:
    if len(content) > MAX_FILE_BYTES:
        raise CsvError("CSV files must be 5 MB or smaller.")
    text = decode_content(content)
    if not text.strip():
        raise CsvError("The file is empty.")
    delimiter = sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    raw_rows = []
    for index, row in enumerate(reader):
        if index > MAX_ROWS:
            raise CsvError(f"CSV files are limited to {MAX_ROWS} rows in Phase 1.")
        if not any(cell.strip() for cell in row):
            continue
        raw_rows.append(row)
    if not raw_rows:
        raise CsvError("No data rows were found in the file.")

    first = raw_rows[0]
    has_header = _looks_like_header(first, raw_rows[1] if len(raw_rows) > 1 else None)
    if has_header:
        headers = _dedupe_headers([cell.strip() or f"Column {i + 1}" for i, cell in enumerate(first)])
        data_rows = raw_rows[1:]
    else:
        width = max(len(r) for r in raw_rows)
        headers = [f"Column {i + 1}" for i in range(width)]
        data_rows = raw_rows

    rows: list[dict[str, str]] = []
    for row in data_rows:
        record = {}
        for i, header in enumerate(headers):
            record[header] = row[i].strip() if i < len(row) else ""
        rows.append(record)
    if not rows:
        raise CsvError("The file has a header row but no transactions.")
    return CsvDocument(
        headers=headers,
        rows=rows,
        delimiter=delimiter,
        has_header=has_header,
        encoding="utf-8",
    )


def _looks_like_header(row: list[str], following: list[str] | None = None) -> bool:
    joined = " ".join(row).lower()
    if not joined.strip():
        return False
    signals = (
        "date",
        "description",
        "amount",
        "memo",
        "payee",
        "debit",
        "credit",
        "balance",
        "transaction",
        "when",
        "what",
        "who",
    )
    hits = sum(1 for signal in signals if signal in joined)
    numeric_cells = sum(1 for cell in row if _is_numericish(cell))
    if hits >= 2 and numeric_cells < 2:
        return True
    # Generic detection for renamed columns: header row has no numbers, next row does.
    if (
        following
        and not any(_is_numericish(cell) for cell in row if cell.strip())
        and any(_is_numericish(cell) for cell in following)
    ):
        return True
    return False


def _is_numericish(cell: str) -> bool:
    cleaned = re.sub(r"[^0-9.,\-()$]", "", cell)
    return any(ch.isdigit() for ch in cleaned) and len(cleaned.strip("$()-,.")) > 0


def _dedupe_headers(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result = []
    for header in headers:
        count = seen.get(header, 0) + 1
        seen[header] = count
        result.append(header if count == 1 else f"{header} ({count})")
    return result


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def suggest_mapping(headers: list[str]) -> dict[str, str | None]:
    normalized = {normalize_header(h): h for h in headers}

    def find(*candidates: str, contains: tuple[str, ...] = ()) -> str | None:
        for candidate in candidates:
            if candidate in normalized:
                return normalized[candidate]
        for key, original in normalized.items():
            if any(token in key for token in contains):
                return original
        return None

    return {
        "date": find("date", "transaction date", "posted date", "posting date", contains=("date",)),
        "description": find(
            "description",
            "memo",
            "payee",
            "name",
            "details",
            "narrative",
            contains=("description", "memo", "payee", "narrative"),
        ),
        "amount": find("amount", "transaction amount", contains=("amount",)),
        "debit": find("debit", "withdrawal", "money out", contains=("debit", "withdrawal")),
        "credit": find("credit", "deposit", "money in", contains=("credit", "deposit")),
        "merchant": find("merchant", "vendor", contains=("merchant", "vendor")),
        "type": find("type", "transaction type", "kind", contains=("type",)),
        "category": find("category", contains=("category",)),
        "external_id": find(
            "transaction id", "id", "reference", "reference number", contains=("transaction id", "reference")
        ),
        "status": find("status", contains=("status",)),
    }


def parse_date(value: str) -> date:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Date is missing")
    # Strip time component if present.
    cleaned = cleaned.split("T")[0].split(" ")[0] if "T" in cleaned else cleaned
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    # Last resort: ISO-like with time.
    try:
        return datetime.fromisoformat(value.strip()).date()
    except ValueError as exc:
        raise ValueError(f"Unrecognised date format: {value!r}") from exc


def parse_amount(value: str) -> Decimal:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Amount is missing")
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()")
    cleaned = re.sub(r"[^\d,.\-+]", "", cleaned)
    if cleaned.startswith("-"):
        negative = True
        cleaned = cleaned[1:]
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    if not cleaned:
        raise ValueError("Amount is missing")
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts[-1]) == 2 and len(parts) == 2:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Unrecognised amount: {value!r}") from exc
    return -amount if negative else amount


def classify_type(raw_type: str | None, signed_amount: Decimal) -> str | None:
    if raw_type:
        lowered = raw_type.strip().lower()
        if any(word in lowered for word in _TRANSFER_WORDS):
            return "transfer"
        for key, value in _TYPE_ALIASES.items():
            if key in lowered:
                if value == "income" and signed_amount < 0:
                    return "purchase"
                return value
    return "income" if signed_amount > 0 else "purchase"


def build_rows(
    document: CsvDocument, mapping: dict[str, str | None]
) -> list[ParsedRow]:
    """Validate and normalise every row against a column mapping."""
    required_date = mapping.get("date")
    required_description = mapping.get("description")
    if not required_date or required_date not in document.headers:
        raise CsvError("Map a date column before previewing.")
    if not required_description or required_description not in document.headers:
        raise CsvError("Map a description column before previewing.")
    amount_col = mapping.get("amount")
    debit_col = mapping.get("debit")
    credit_col = mapping.get("credit")
    if not any(c and c in document.headers for c in (amount_col, debit_col, credit_col)):
        raise CsvError("Map an amount column, or separate debit and credit columns.")

    parsed: list[ParsedRow] = []
    for index, raw in enumerate(document.rows, start=1):
        row = ParsedRow(row_number=index, raw=raw)
        try:
            row.txn_date = parse_date(raw.get(required_date, ""))
            row.description = (raw.get(required_description) or "").strip()[:255]
            if not row.description:
                raise ValueError("Description is empty")
            merchant_col = mapping.get("merchant")
            row.merchant = (
                (raw.get(merchant_col) or "").strip()[:160] if merchant_col else None
            ) or None
            row.external_id = None
            external_col = mapping.get("external_id")
            if external_col and raw.get(external_col):
                row.external_id = raw[external_col].strip()[:160]

            if amount_col and raw.get(amount_col, "").strip():
                signed = parse_amount(raw[amount_col])
            else:
                debit = parse_amount(raw.get(debit_col, "0") or "0") if debit_col else Decimal("0")
                credit = parse_amount(raw.get(credit_col, "0") or "0") if credit_col else Decimal("0")
                # A debit is money out, a credit is money in.
                signed = credit - abs(debit)
            if abs(signed) == 0:
                raise ValueError("Amount is zero")
            row.signed_amount = signed
            row.amount = abs(signed)

            type_col = mapping.get("type")
            raw_type = raw.get(type_col) if type_col else None
            row.tx_type = classify_type(raw_type, signed)
            if row.tx_type == "transfer":
                row.status = "error"
                row.reason = (
                    "Transfers cannot be imported automatically because the destination "
                    "account is unknown. Record this transfer manually."
                )
                parsed.append(row)
                continue
            if row.tx_type == "income" and signed < 0:
                row.tx_type = "purchase"
            if row.tx_type not in ("income", "purchase", "refund", "bill_payment"):
                raise ValueError("Unsupported transaction type")
        except ValueError as exc:
            row.status = "error"
            row.reason = str(exc)
        parsed.append(row)
    return parsed
