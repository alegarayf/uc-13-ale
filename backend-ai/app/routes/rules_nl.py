from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings, resolve_rules_ai_mode
from app.services.genie_rules import GenieRulesError, interpret_prompt
from app.services.rules_config_store import (
    list_rule_configs,
    read_rule_config,
    update_rule_config,
    write_rule_config,
)
from app.services.session_store import get_session_store

router = APIRouter(prefix="/api/ai/rules", tags=["rules-nl"])


class InterpretRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)


class InterpretResponse(BaseModel):
    sessionId: str
    summary: str
    ruleConfig: dict[str, Any]
    aiMode: str
    canDeny: bool


class DenyRequest(BaseModel):
    feedback: str | None = Field(default=None, max_length=2000)


class ConfirmRequest(BaseModel):
    updateFilename: str | None = Field(default=None, max_length=128)


class ConfirmResponse(BaseModel):
    sessionId: str
    configFile: str
    ruleConfig: dict[str, Any]


class ConfigListItem(BaseModel):
    filename: str
    id: str | None = None
    name: str | None = None
    summary: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class ConfigDetail(BaseModel):
    filename: str
    id: str | None = None
    sessionId: str | None = None
    prompt: str
    summary: str
    rule: dict[str, Any]
    createdAt: str | None = None
    updatedAt: str | None = None


@router.get("/configs", response_model=list[ConfigListItem])
def list_configs() -> list[ConfigListItem]:
    settings = get_settings()
    items = list_rule_configs(settings.rules_config_dir)
    return [ConfigListItem(**item) for item in items]


@router.get("/configs/{filename}", response_model=ConfigDetail)
def get_config(filename: str) -> ConfigDetail:
    settings = get_settings()
    try:
        data = read_rule_config(settings.rules_config_dir, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Config not found.") from exc
    return ConfigDetail(**data)


@router.post("/interpret", response_model=InterpretResponse)
def interpret(body: InterpretRequest) -> InterpretResponse:
    settings = get_settings()
    try:
        summary, rule_config, raw, conversation_id, _msg_id = interpret_prompt(
            settings, body.prompt
        )
    except GenieRulesError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    session = get_session_store().create(
        prompt=body.prompt,
        summary=summary,
        rule_config=rule_config,
        raw_response=raw,
        conversation_id=conversation_id,
    )

    return InterpretResponse(
        sessionId=session.id,
        summary=summary,
        ruleConfig=rule_config,
        aiMode=resolve_rules_ai_mode(settings),
        canDeny=True,
    )


@router.post("/sessions/{session_id}/confirm", response_model=ConfirmResponse)
def confirm(session_id: str, body: ConfirmRequest | None = None) -> ConfirmResponse:
    settings = get_settings()
    store = get_session_store()
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session.confirmed:
        raise HTTPException(status_code=409, detail="Session already confirmed.")

    update_filename = body.updateFilename if body else None
    try:
        if update_filename:
            filename, _path = update_rule_config(
                settings.rules_config_dir,
                update_filename,
                rule_config=session.rule_config,
                prompt=session.prompt,
                summary=session.summary,
                session_id=session.id,
            )
        else:
            filename, _path = write_rule_config(
                settings.rules_config_dir,
                rule_config=session.rule_config,
                prompt=session.prompt,
                summary=session.summary,
                session_id=session.id,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Config not found.") from exc

    store.mark_confirmed(session, filename)

    return ConfirmResponse(
        sessionId=session.id,
        configFile=filename,
        ruleConfig=session.rule_config,
    )


@router.post("/sessions/{session_id}/deny", response_model=InterpretResponse)
def deny(session_id: str, body: DenyRequest) -> InterpretResponse:
    settings = get_settings()
    store = get_session_store()
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session.confirmed:
        raise HTTPException(status_code=409, detail="Session already confirmed.")
    if session.deny_count >= settings.rules_ai_max_denies:
        raise HTTPException(
            status_code=409,
            detail="No retries remaining for this session. Start a new rule.",
        )

    session.deny_count += 1
    feedback = body.feedback or "The interpretation does not match what I intended."

    try:
        summary, rule_config, raw, conversation_id, _msg_id = interpret_prompt(
            settings,
            session.prompt,
            conversation_id=session.conversation_id,
            retry_feedback=feedback,
        )
    except GenieRulesError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    store.update_interpretation(
        session,
        summary=summary,
        rule_config=rule_config,
        raw_response=raw,
        conversation_id=conversation_id,
    )

    can_deny = session.deny_count < settings.rules_ai_max_denies
    return InterpretResponse(
        sessionId=session.id,
        summary=summary,
        ruleConfig=rule_config,
        aiMode=resolve_rules_ai_mode(settings),
        canDeny=can_deny,
    )
