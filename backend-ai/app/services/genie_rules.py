from typing import Any

from app.config import Settings, resolve_rules_ai_mode
from app.prompts.rules_engine import RULES_ENGINE_GENIE_INSTRUCTIONS, RULES_ENGINE_JSON_PROMPT
from app.services.genie_message import GenieMessageError, display_summary_from_genie_text, extract_genie_response_text
from app.services.response_parser import ParseError, parse_rules_interpretation


class GenieRulesError(RuntimeError):
    pass


def _default_rule_config(user_prompt: str, genie_text: str) -> dict[str, Any]:
    name = user_prompt.strip()[:60] or "Natural language rule"
    return {
        "name": name,
        "description": display_summary_from_genie_text(genie_text),
        "intent": "evaluate_opportunity",
        "source": "genie_text",
        "conditions": [],
        "metadata": {"user_prompt": user_prompt.strip()},
    }


def _rule_config_from_genie_text(genie_text: str, user_prompt: str) -> dict[str, Any]:
    try:
        _summary, rule_config = parse_rules_interpretation(genie_text)
        return rule_config
    except ParseError:
        return _default_rule_config(user_prompt, genie_text)


def _compose_genie_message(user_prompt: str, *, retry_feedback: str | None = None) -> str:
    parts = [RULES_ENGINE_GENIE_INSTRUCTIONS.strip(), "", "Rule request:", user_prompt.strip()]
    if retry_feedback:
        parts.extend(
            [
                "",
                "The prior interpretation was rejected. Apply this feedback and restate your understanding declaratively.",
                f"Feedback: {retry_feedback.strip()}",
            ]
        )
    return "\n".join(parts)


def _mock_interpret(user_prompt: str, *, retry_feedback: str | None = None) -> tuple[str, dict[str, Any], str]:
    name_hint = user_prompt.strip()[:80] or "Untitled rule"
    summary = (
        f"(Mock AI) This rule will evaluate opportunities using the criteria described in your request "
        f"(“{name_hint}”). Existing system capabilities are assumed available."
    )
    if retry_feedback:
        summary = (
            f"(Mock AI) Revised understanding after feedback: the rule will reflect “{retry_feedback.strip()}” "
            f"while still applying your original request about “{name_hint}”."
        )

    rule_config: dict[str, Any] = {
        "name": name_hint[:60],
        "description": user_prompt.strip(),
        "intent": "evaluate_opportunity",
        "source": "nl_prompt",
        "conditions": [
            {
                "field": "prompt_text",
                "operator": "matches_intent",
                "value": user_prompt.strip(),
            }
        ],
        "metadata": {"mock": True, "retry": bool(retry_feedback)},
    }
    import json as json_module

    raw = json_module.dumps({"summary": summary, "rule": rule_config})
    return summary, rule_config, raw


def _genie_client(settings: Settings):
    from databricks.sdk import WorkspaceClient

    host = settings.databricks_host.strip()
    if not host:
        raise GenieRulesError("DATABRICKS_SERVER_HOSTNAME is not configured.")
    if not host.startswith("https://"):
        host = f"https://{host}"

    token = settings.databricks_token.strip()
    if not token:
        raise GenieRulesError("DATABRICKS_TOKEN is not configured.")

    return WorkspaceClient(host=host, token=token)


def _message_status_name(message) -> str | None:
    status = getattr(message, "status", None)
    return getattr(status, "value", status) if status is not None else status


def _genie_send_message(
    settings: Settings,
    content: str,
    *,
    conversation_id: str | None = None,
):
    space_id = settings.databricks_genie_space_id.strip()
    if not space_id:
        raise GenieRulesError("DATABRICKS_GENIE_SPACE_ID is not configured.")

    client = _genie_client(settings)

    if conversation_id:
        message = client.genie.create_message_and_wait(space_id, conversation_id, content)
    else:
        message = client.genie.start_conversation_and_wait(space_id, content)
        conversation_id = getattr(message, "conversation_id", None) or ""

    status_name = _message_status_name(message)
    if status_name == "FAILED":
        err = getattr(message, "error", None)
        raise GenieRulesError(f"Genie failed to generate a response: {err}")

    return conversation_id, getattr(message, "message_id", "") or "", message


def _interpret_genie_message(
    message,
    *,
    user_prompt: str,
) -> tuple[str, dict[str, Any], str]:
    genie_text = extract_genie_response_text(message)
    summary = display_summary_from_genie_text(genie_text)
    rule_config = _rule_config_from_genie_text(genie_text, user_prompt)
    return summary, rule_config, genie_text


def interpret_prompt(
    settings: Settings,
    user_prompt: str,
    *,
    conversation_id: str | None = None,
    retry_feedback: str | None = None,
) -> tuple[str, dict[str, Any], str, str | None, str]:
    """
    Returns (summary, rule_config, raw_response, conversation_id, message_id).
    """
    mode = resolve_rules_ai_mode(settings)
    if mode == "mock":
        summary, rule_config, raw = _mock_interpret(user_prompt, retry_feedback=retry_feedback)
        return summary, rule_config, raw, None, ""

    user_message = _compose_genie_message(user_prompt, retry_feedback=retry_feedback)

    try:
        conv_id, msg_id, message = _genie_send_message(
            settings, user_message, conversation_id=conversation_id
        )
        summary, rule_config, raw = _interpret_genie_message(message, user_prompt=user_prompt)
        return summary, rule_config, raw, conv_id, msg_id
    except GenieMessageError as exc:
        if not conversation_id:
            raise GenieRulesError(str(exc)) from exc
        conv_id, msg_id, repair_message = _genie_send_message(
            settings, RULES_ENGINE_JSON_PROMPT, conversation_id=conversation_id
        )
        try:
            summary, rule_config, raw = _interpret_genie_message(repair_message, user_prompt=user_prompt)
            return summary, rule_config, raw, conv_id, msg_id
        except GenieMessageError as repair_exc:
            raise GenieRulesError(str(repair_exc)) from repair_exc
