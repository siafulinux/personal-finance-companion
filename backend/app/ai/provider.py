"""AI provider interface.

Phase 1 ships without an AI provider: every feature works from deterministic
calculations. Future phases inject an implementation (hosted model, local model,
or an on-device assistant) behind this interface. Providers receive only the
structured, permission-checked payloads from ``assistant_tools`` - never a
database session and never raw SQL.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.config import settings


@dataclass
class AssistantContext:
    user_id: str
    timezone: str
    currency: str
    data: dict[str, Any] = field(default_factory=dict)
    question: str | None = None


@dataclass
class AssistantAnswer:
    text: str
    provider: str
    used_tools: list[str] = field(default_factory=list)
    disclaimer: str = (
        "Figures come from the deterministic finance engine. This assistant cannot move money."
    )


class AIProvider(ABC):
    name: str

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def answer(self, context: AssistantContext) -> AssistantAnswer: ...


class NullAIProvider(AIProvider):
    """Default provider. Explains that AI features are not configured."""

    name = "disabled"

    def available(self) -> bool:
        return False

    def answer(self, context: AssistantContext) -> AssistantAnswer:
        raise RuntimeError(
            "AI features are not enabled in Phase 1. The financial engine is fully "
            "functional without them."
        )


_provider: AIProvider = NullAIProvider()


def get_ai_provider() -> AIProvider:
    return _provider


def set_ai_provider(provider: AIProvider) -> None:
    global _provider
    _provider = provider


def ai_status() -> dict[str, object]:
    provider = get_ai_provider()
    return {
        "enabled": provider.available(),
        "provider": provider.name,
        "phase": "AI-ready foundation (Phase 1 does not require AI)",
        "environment": settings.environment,
    }
