"""AI financial assistant endpoints.

Read-only by construction: there is no endpoint here that can change financial data.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy.orm import Session

from app.ai.assistant import answer_question, assistant_status, set_ai_consent
from app.database.base import get_db
from app.models import User
from app.schemas.common import APIModel
from app.security.deps import get_current_user

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AskRequest(APIModel):
    question: str = Field(min_length=1, max_length=400)


class ConsentRequest(APIModel):
    consent: bool


@router.get("/status")
def status(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return assistant_status(db, user)


@router.post("/ask")
def ask(
    payload: AskRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return answer_question(db, user, payload.question)


@router.post("/consent")
def consent(
    payload: ConsentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    prefs = set_ai_consent(db, user, payload.consent)
    return {"ai_consent": prefs.ai_consent}
