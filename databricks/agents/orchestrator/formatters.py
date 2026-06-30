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
    if doc_type := entry.get("doc_type"):
        return f"Request and review {doc_type}"
    if item_id := entry.get("item_id"):
        return f"Complete diligence item: {str(item_id).replace('_', ' ')}"
    return ""


def format_diligence_entry(entry: dict[str, Any] | str) -> str:
    """Legal recommended_diligence row or legacy str(dict) → human question text."""
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
