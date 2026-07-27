from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ConversationMode(StrEnum):
    SINGLE_TURN = "single_turn"
    MULTI_TURN = "multi_turn"


class SessionStatus(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    WAITING = "waiting"
    CLOSED = "closed"


class Session(BaseModel):
    id: str

    conversation_mode: ConversationMode
    status: SessionStatus = SessionStatus.CREATED

    title: str
    run_ids: list[str] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime