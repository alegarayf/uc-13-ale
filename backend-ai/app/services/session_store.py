import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class InterpretationSession:
    id: str
    prompt: str
    summary: str
    rule_config: dict[str, Any]
    raw_response: str
    conversation_id: str | None
    deny_count: int = 0
    confirmed: bool = False
    config_file: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, InterpretationSession] = {}

    def create(
        self,
        *,
        prompt: str,
        summary: str,
        rule_config: dict[str, Any],
        raw_response: str,
        conversation_id: str | None,
    ) -> InterpretationSession:
        session = InterpretationSession(
            id=str(uuid.uuid4()),
            prompt=prompt,
            summary=summary,
            rule_config=rule_config,
            raw_response=raw_response,
            conversation_id=conversation_id,
        )
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> InterpretationSession | None:
        return self._sessions.get(session_id)

    def update_interpretation(
        self,
        session: InterpretationSession,
        *,
        summary: str,
        rule_config: dict[str, Any],
        raw_response: str,
        conversation_id: str | None,
    ) -> None:
        session.summary = summary
        session.rule_config = rule_config
        session.raw_response = raw_response
        if conversation_id:
            session.conversation_id = conversation_id

    def mark_confirmed(self, session: InterpretationSession, config_file: str) -> None:
        session.confirmed = True
        session.config_file = config_file


_store = SessionStore()


def get_session_store() -> SessionStore:
    return _store
