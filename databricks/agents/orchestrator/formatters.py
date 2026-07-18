"""Pure formatting helpers for orchestrator TL;DR compression and populate dedupe."""

from __future__ import annotations

import ast
import re
from typing import Any

_OPERATOR_GAP_PATTERNS: tuple[str, ...] = (
    "LLM response was truncated",
    "token limit",
    "Partial JSON was recovered",
    "not extracted",
    "retrieval coverage",
    "check system prompt",
    "re-run the agent",
    "workstream-tagged",
    "chunks retrieved but no extractable",
    "Consider raising max_tokens",
    "reducing retrieved context",
)

_FLAG_MAX_LEN = 220


def normalize_gap(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for gap dedupe keys."""
    lowered = text.lower()
    lowered = re.sub(r"[^\w\s]", "", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def is_operator_gap(item: str) -> bool:
    """True when item matches operator/pipeline diagnostic vocabulary (spec §4.4)."""
    lowered = item.lower()
    return any(pattern.lower() in lowered for pattern in _OPERATOR_GAP_PATTERNS)


def format_agent_flag(flag: dict[str, Any]) -> str:
    """Delta Flag shape → stakeholder prose; never ``str(dict)``."""
    note = flag.get("note")
    if note:
        text = str(note)
    else:
        metric = str(flag.get("metric") or "")
        value = str(flag.get("value") or "")
        source_doc = str(flag.get("source_doc") or "")
        text = f"{metric}: {value} — {source_doc}".strip(" :—")
    if len(text) > _FLAG_MAX_LEN:
        cut = text[: _FLAG_MAX_LEN - 3]
        last_space = cut.rfind(" ")
        if last_space > 0:
            cut = cut[:last_space]
        return cut + "..."
    return text


def _diligence_text_from_entry(entry: dict[str, Any]) -> str:
    if question := entry.get("question"):
        return str(question)
    if item := entry.get("item"):
        return str(item)
    if mq := entry.get("management_question"):
        return str(mq)
    if kn := entry.get("kpi_name"):
        return f"Provide supporting data for KPI: {kn}"
    if doc_type := entry.get("doc_type"):
        return f"Request and review {doc_type}"
    if item_id := entry.get("item_id"):
        return f"Complete diligence item: {str(item_id).replace('_', ' ')}"
    return ""


_KPI_DESCRIPTION_KEYS: tuple[str, ...] = (
    "description",
    "note",
    "text",
    "stated",
    "value",
    "management_question",
    "kpi_name",
)


def _kpi_text_from_dict(item: dict[str, Any]) -> str:
    for key in _KPI_DESCRIPTION_KEYS:
        if raw := item.get(key):
            text = str(raw).strip()
            if text and text.lower() not in ("null", "none"):
                return text
    type_val = str(item.get("type") or "").strip()
    status = str(item.get("status") or "").strip()
    if type_val and status:
        return f"{type_val.replace('_', ' ')} ({status})"
    if type_val:
        return type_val.replace("_", " ")
    parts: list[str] = []
    for key, raw in item.items():
        if raw in (None, "", [], {}):
            continue
        if isinstance(raw, (dict, list)):
            formatted = format_kpi_value(raw)
        else:
            formatted = str(raw).strip()
        if not formatted or formatted.lower() in ("null", "none"):
            continue
        label = str(key).replace("_", " ")
        parts.append(f"{label}: {formatted}")
    return "; ".join(parts)


def format_kpi_value(stated: Any) -> str:
    """KPI stated field → stakeholder text; never ``str(dict)`` or list repr."""
    if stated is None:
        return ""
    if isinstance(stated, bool):
        return "true" if stated else "false"
    if isinstance(stated, (int, float)):
        return str(stated)
    if isinstance(stated, str):
        return stated
    if isinstance(stated, dict):
        return _kpi_text_from_dict(stated)
    if isinstance(stated, list):
        parts = [format_kpi_value(item) for item in stated]
        parts = [part for part in parts if part]
        return "; ".join(parts)
    return str(stated)


def format_diligence_entry(entry: dict[str, Any] | str) -> str:
    """Legal recommended_diligence, kpi_agent missing_kpis dict, or legacy str(dict) → question text."""
    if isinstance(entry, dict):
        return _diligence_text_from_entry(entry)
    if isinstance(entry, str):
        stripped = entry.strip()
        if stripped.startswith("{"):
            try:
                parsed = ast.literal_eval(stripped)
            except (ValueError, SyntaxError):
                parsed = None
            if isinstance(parsed, dict):
                return _diligence_text_from_entry(parsed)
        if stripped:
            return stripped
    return ""
