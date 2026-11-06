"""Financial assistant built on the deterministic tool layer.

Two providers share one contract:

* ``DeterministicAssistant`` — always available. It routes the question to
  ``assistant_tools``, then narrates the exact figures those tools returned. No model is
  involved, so it cannot invent a number and it works with no configuration at all.
* ``OpenAICompatModel`` — optional. It receives only the JSON those same tools produced,
  and only after the user has opted in. It is asked to explain, never to calculate or act.

The assistant has no write path. Nothing here can move money, change a category or pay a
bill; those remain explicit, separately confirmed endpoints.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.provider import AssistantAnswer
from app.config import settings
from app.models import Category, User, UserPreference
from app.services.assistant_tools import call_tool
from app.services.errors import ValidationError
from app.utils.money import quantize

MAX_QUESTION_CHARS = 400

_AMOUNT = re.compile(r"\$?\s?(\d[\d,]*(?:\.\d{1,2})?)")

_SYSTEM_PROMPT = (
    "You are a personal finance explainer. You are given JSON produced by a deterministic "
    "finance engine plus one user question. Rules: (1) Use only the numbers in the JSON; "
    "never compute, estimate or assume a figure that is not present. (2) If the data does "
    "not answer the question, say so plainly. (3) Be concise and concrete, and mention the "
    "figures that support each statement. (4) You cannot make changes: if asked to pay, "
    "transfer or edit anything, explain that you are read-only. (5) Do not give investment, "
    "tax or legal advice."
)


@dataclass
class Snapshot:
    question: str
    tools: dict[str, Any] = field(default_factory=dict)


def _prefs(db: Session, user: User) -> UserPreference | None:
    return db.get(UserPreference, user.id)


def _detect_amount(question: str) -> Decimal | None:
    for match in _AMOUNT.finditer(question):
        raw = match.group(1).replace(",", "")
        # Ignore bare years and similar noise.
        if len(raw) >= 4 and raw.isdigit():
            continue
        try:
            value = Decimal(raw)
        except ArithmeticError:  # pragma: no cover - regex prevents this
            continue
        if value > 0:
            return quantize(value)
    return None


def _detect_category(db: Session, user: User, question: str) -> Category | None:
    lowered = question.lower()
    categories = list(
        db.scalars(
            select(Category).where(
                Category.user_id == user.id, Category.is_archived.is_(False)
            )
        )
    )
    # Longest name first so "Fast food" wins over shorter overlapping names.
    for category in sorted(categories, key=lambda c: len(c.name), reverse=True):
        if category.name.lower() in lowered:
            return category
    return None


def build_snapshot(db: Session, user: User, question: str) -> Snapshot:
    lowered = question.lower()
    snapshot = Snapshot(question=question)
    wants = set()

    if any(
        word in lowered
        for word in ("safe to spend", "safe", "afford", "available", "left", "how much")
    ):
        wants.add("safe_to_spend")
    if any(word in lowered for word in ("bill", "due", "owe")):
        wants.add("upcoming_bills")
    if any(word in lowered for word in ("payday", "paycheck", "income", "next week", "month")):
        wants.add("forecast")
    if any(word in lowered for word in ("subscription", "recurring", "membership")):
        wants.add("recurring_payments")
    if "budget" in lowered:
        wants.add("budget")
    if any(word in lowered for word in ("spend", "spent", "spending", "where did")):
        wants.add("spending")
        wants.add("category_trends")

    category = _detect_category(db, user, question)
    if category is not None:
        wants.add("category_availability")

    if not wants:
        wants = {"safe_to_spend", "upcoming_bills", "budget"}

    for tool in sorted(wants):
        if tool == "category_availability":
            assert category is not None
            snapshot.tools[tool] = call_tool(db, user, tool, category_id=category.id)
        else:
            snapshot.tools[tool] = call_tool(db, user, tool)
    if category is not None:
        snapshot.tools["matched_category"] = {"name": category.name, "id": str(category.id)}
    return snapshot


def deterministic_answer(snapshot: Snapshot) -> str:
    """Narrate exactly what the tools returned, in the order a person would ask."""
    tools = snapshot.tools
    lines: list[str] = []

    safe = tools.get("safe_to_spend")
    if safe:
        lines.append(
            f"Safe-to-Spend is {safe['safe_to_spend']} through {safe['horizon_end']}"
            + (f", with your next payday on {safe['payday']}" if safe.get("payday") else "")
            + ". It is your eligible balance minus "
            f"{safe['bill_reserves']} reserved for bills, "
            f"{safe['minimum_buffer']} of buffer and "
            f"{safe['explicit_reserves']} in planned reserves."
        )
        if safe.get("projected_shortfall") not in (None, "0.00"):
            lines.append(
                f"You are projected short by {safe['projected_shortfall']} before your next payday."
            )

    availability = tools.get("category_availability")
    if availability:
        lines.append(
            f"In {availability['category_name']} you have {availability['remaining']} remaining "
            f"of {availability['budgeted']} budgeted "
            f"({availability['spent']} spent, {availability['upcoming_commitments']} committed to bills)."
        )

    amount = _detect_amount(snapshot.question)
    if amount is not None:
        if availability:
            affordable = Decimal(str(availability["remaining"])) >= amount
            lines.append(
                f"A {amount} purchase would "
                + ("fit" if affordable else "not fit")
                + f" within the {availability['remaining']} left in {availability['category_name']}."
            )
        elif safe:
            affordable = Decimal(str(safe["safe_to_spend"])) >= amount
            lines.append(
                f"A {amount} purchase would "
                + ("fit" if affordable else "not fit")
                + f" inside your {safe['safe_to_spend']} Safe-to-Spend."
            )

    bills = tools.get("upcoming_bills")
    if bills:
        rows = bills.get("bills", [])[:5]
        if rows:
            described = ", ".join(
                f"{row['bill_name']} {row['remaining_amount']} on {row['due_date']}"
                for row in rows
            )
            lines.append(f"Upcoming bills: {described}. Total due: {bills['total_due']}.")
        else:
            lines.append(f"No bills are due before {bills['horizon_end']}.")

    forecast = tools.get("forecast")
    if forecast:
        lines.append(
            f"Forecast to {forecast['end_date']}: {forecast['starting_available_cash']} available "
            f"now, {forecast['bills_total']} of bills and {forecast['expected_income_total']} of "
            f"expected income, leaving {forecast['projected_end_balance']} "
            f"(lowest point {forecast['lowest_projected_balance']})."
        )

    budget = tools.get("budget")
    if budget and budget.get("budget"):
        row = budget["budget"]
        lines.append(
            f"This month's budget: {row['total_spent']} spent of {row['total_allocated']} "
            f"allocated, {row['total_remaining']} remaining."
        )
    elif budget:
        lines.append("You have no budget for this month yet.")

    recurring = tools.get("recurring_payments")
    if recurring:
        rows = recurring.get("recurring_payments", [])
        if rows:
            total = sum((Decimal(row["amount"]) for row in rows), Decimal("0"))
            named = ", ".join(
                f"{row['name']} {row['amount']}/{row['frequency']}" for row in rows[:6]
            )
            lines.append(f"Recurring payments ({quantize(total)} per cycle): {named}.")
        else:
            lines.append("No recurring bills are recorded.")

    spending = tools.get("spending")
    if spending:
        lines.append(
            f"Over the last 30 days you earned {spending['income']}, spent {spending['spending']} "
            f"and kept {spending['net']}."
        )
        by_category = spending.get("by_category") or []
        if by_category[:3]:
            top = ", ".join(
                f"{row['category_name']} {row['spent']}"
                for row in by_category[:3]
                if row.get("spent")
            )
            if top:
                lines.append(f"Largest categories: {top}.")

    if not lines:
        return (
            "I could not find a figure that answers that question. I can explain balances, "
            "Safe-to-Spend, upcoming bills, budgets, subscriptions and cash-flow forecasts."
        )
    return " ".join(lines)


class OpenAICompatModel:
    """A configurable OpenAI-compatible chat model. Explains, never calculates."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._client = client

    # Configuration is resolved per call, not captured at import, so changing settings
    # takes effect without a restart (and tests can override it).
    @property
    def base_url(self) -> str:
        return (self._base_url or settings.ai_base_url).rstrip("/")

    @property
    def api_key(self) -> str | None:
        return self._api_key or settings.ai_api_key

    @property
    def model(self) -> str:
        return self._model or settings.ai_model

    def available(self) -> bool:
        return settings.ai_provider == "openai_compatible" and bool(self.api_key)

    def explain(self, snapshot: Snapshot) -> AssistantAnswer:
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 500,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Question: {snapshot.question}\n\n"
                        f"Engine data (JSON):\n{snapshot.tools}"
                    ),
                },
            ],
        }
        client = self._client or httpx.Client(timeout=settings.ai_timeout_seconds)
        try:
            response = client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            response.raise_for_status()
            data = response.json()
            text = (data["choices"][0]["message"]["content"] or "").strip()
            if not text:
                raise ValueError("empty completion")
        except (httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
            raise RuntimeError("The language model is unavailable.") from exc
        finally:
            if self._client is None:
                client.close()
        return AssistantAnswer(
            text=text,
            provider=f"model:{self.model}",
            used_tools=sorted(snapshot.tools),
        )


_model = OpenAICompatModel()


def assistant_status(db: Session, user: User) -> dict[str, object]:
    prefs = _prefs(db, user)
    consent = bool(prefs.ai_consent) if prefs else False
    return {
        "mode": "model" if (_model.available() and consent) else "deterministic",
        "model_configured": _model.available(),
        "model": _model.model if _model.available() else None,
        "consent_required": _model.available() and not consent,
        "ai_consent": consent,
        "capabilities": [
            "balances",
            "safe_to_spend",
            "upcoming_bills",
            "budget_status",
            "subscriptions",
            "cash_flow_forecast",
            "spending_by_category",
        ],
        "can_modify_data": False,
        "note": (
            "Answers are computed by the deterministic finance engine. "
            "The assistant cannot move money or change your data."
        ),
    }


def answer_question(db: Session, user: User, question: str) -> dict[str, object]:
    question = (question or "").strip()
    if not question:
        raise ValidationError("Ask a question first.")
    if len(question) > MAX_QUESTION_CHARS:
        raise ValidationError(
            f"Questions are limited to {MAX_QUESTION_CHARS} characters."
        )

    snapshot = build_snapshot(db, user, question)
    deterministic = deterministic_answer(snapshot)
    prefs = _prefs(db, user)
    consent = bool(prefs.ai_consent) if prefs else False

    result: dict[str, object] = {
        "question": question,
        "answer": deterministic,
        "mode": "deterministic",
        "used_tools": sorted(k for k in snapshot.tools if k != "matched_category"),
        "data": snapshot.tools,
        "can_modify_data": False,
        "disclaimer": (
            "Figures come from the deterministic finance engine. This assistant cannot "
            "move money or change your data."
        ),
    }

    if _model.available() and consent:
        try:
            model_answer = _model.explain(snapshot)
            result["answer"] = model_answer.text
            result["mode"] = "model"
            result["provider"] = model_answer.provider
        except RuntimeError:
            # Never fail a question because a model is down.
            result["mode"] = "deterministic_fallback"
            result["note"] = "The language model was unavailable, so the engine's own wording is shown."
    elif _model.available() and not consent:
        result["note"] = (
            "A language model is configured but AI data sharing is not enabled in your "
            "preferences, so this answer was produced on-device from the finance engine."
        )
    return result


def set_ai_consent(db: Session, user: User, consent: bool) -> UserPreference:
    prefs = _prefs(db, user)
    if prefs is None:
        prefs = UserPreference(user_id=user.id)
        db.add(prefs)
    prefs.ai_consent = consent
    db.flush()
    return prefs
