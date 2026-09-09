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
        return summarize_breakdown(parts)
    return str(stated)


# A KPI field holding a per-role or per-segment breakdown is a table in
# disguise. Joining every entry produced a single cell 7,315 characters long
# — Clearsulting's bill_rates_by_role, every practice at every level, which
# ran for a page and a half of the rendered report and pushed the sections
# after it off their own pages.
_BREAKDOWN_PREVIEW = 3


def summarize_breakdown(parts: list[str]) -> str:
    """First few entries of a breakdown, then a count of the rest.

    Deliberately lossy: the point of this cell is to tell the reader the
    breakdown exists and roughly what it looks like. The full detail belongs
    in the data room, not in a summary table, and an unbounded join makes the
    page unreadable without making it more informative.
    """
    if not parts:
        return ""
    if len(parts) <= _BREAKDOWN_PREVIEW:
        return "; ".join(parts)
    shown = "; ".join(parts[:_BREAKDOWN_PREVIEW])
    return f"{shown}; and {len(parts) - _BREAKDOWN_PREVIEW} more"


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


# ---------------------------------------------------------------------------
# Period ordering and money magnitude.
#
# Both live here because the mapper and the view each need them and neither
# should import the other. Both exist because extraction does not normalise:
# the same company's revenue arrives as "$57,090 thousand" for three periods
# and "$40,251,450" for a fourth, and its period labels as "2023", "TTM25",
# "FY23" and "2025B" in one series.
# ---------------------------------------------------------------------------

_PERIOD_YEAR4_RE = re.compile(r"(?:19|20)\d{2}")
# Not \b-delimited: "FY23" has no word boundary between "Y" and "2".
_PERIOD_YEAR2_RE = re.compile(r"(?<!\d)(\d{2})(?!\d)")

_MAGNITUDE_WORDS: tuple[tuple[str, float], ...] = (
    ("billion", 1_000_000_000.0),
    ("bn", 1_000_000_000.0),
    ("million", 1_000_000.0),
    ("mm", 1_000_000.0),
    ("thousand", 1_000.0),
    ("k", 1_000.0),
)
_NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def period_sort_key(period: Any) -> tuple[int, int]:
    """Order period labels chronologically across the shapes agents emit.

    Extraction labels are not uniform — one series carries "2020A", "FY23",
    "2025B", "TTM Aug-24", "2027PP". Sorted as plain strings, a trailing
    period lands between historical years, which is how a 2022 bar came to be
    drawn after TTM25. A label with no year sorts last: in practice that is a
    note rather than a dated period.
    """
    text = str(period or "")
    match = _PERIOD_YEAR4_RE.search(text)
    if match:
        return (0, int(match.group(0)))
    match = _PERIOD_YEAR2_RE.search(text)
    if match:
        return (0, 2000 + int(match.group(1)))
    return (1, 0)


def money_to_dollars(value: Any) -> float | None:
    """Absolute dollars from a money string, honouring a SPELLED-OUT magnitude.

    ``final_report_view.parse_money`` returns the figure in whatever unit the
    caller is already working in and knows only the ``k``/``bn`` suffixes.
    Extraction writes magnitude as a word at least as often, and comparing
    "$59,699 thousand" with "$10,917,799" as bare numbers is off by 1000x.
    A bare number is returned at face value; deciding whether an unqualified
    figure is safe to compare is the caller's job.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = _NUMBER_RE.search(text)
    if not match:
        return None
    try:
        number = float(match.group(0).replace(",", ""))
    except ValueError:
        return None
    low = text.lower()
    for word, factor in _MAGNITUDE_WORDS:
        if re.search(rf"\d\s*{re.escape(word)}\b", low):
            return number * factor
    return number


def has_explicit_magnitude(value: Any) -> bool:
    """True when the string states its own magnitude in words or a suffix."""
    if value is None:
        return False
    low = str(value).lower()
    return any(re.search(rf"\d\s*{re.escape(word)}\b", low) for word, _ in _MAGNITUDE_WORDS)


def format_dollars(value: float | None) -> str | None:
    """Compact money label with the magnitude the figure actually has.

    The label this replaces divided by 1,000 and appended "bn" unconditionally,
    so a P&L stated in thousands rendered $57.09M of revenue as "57.1bn" — the
    wrong magnitude and the wrong unit name, on every chart of every report.
    """
    if value is None:
        return None
    magnitude = abs(value)
    if magnitude >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if magnitude >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if magnitude >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.0f}"


# Several agents write a gap as one sentence that already contains its own
# rationale, separated by an em dash: "Top customer revenue % not stated —
# required for concentration threshold evaluation". The appendix has an
# "Item requested" column and a "Why it matters" column, and the whole string
# went into the first one, leaving the second blank on every row of every
# report — including the rows whose reason the agent had already written.
_GAP_SEPARATOR = re.compile(r"\s+[—–]\s+")
_GAP_MIN_ITEM = 8
_GAP_MIN_WHY = 12


def split_gap_rationale(text: str) -> tuple[str, str | None]:
    """Split a gap sentence into what is requested and why it matters.

    Only splits on a SINGLE separator. Two or more means the sentence is a
    chain of clauses rather than a request-and-reason pair — the legal agent's
    "t4c: no documents retrieved … — request Top Customer Contracts — 
    no_chunks_retrieved" is a trace, not a rationale, and cutting it at the
    first dash would present an internal pass name as the item and a retrieval
    code as the reason.
    """
    parts = _GAP_SEPARATOR.split(str(text or "").strip())
    if len(parts) != 2:
        return str(text or "").strip(), None
    item, why = parts[0].strip(), parts[1].strip()
    if len(item) < _GAP_MIN_ITEM or len(why) < _GAP_MIN_WHY:
        return str(text or "").strip(), None
    # A single token is a status code, not a reason. The legal agent ends
    # several gaps with "— corpus_absent" and "— no_chunks_retrieved", which
    # cleared the length floor and would have printed a retrieval code into a
    # column a deal team reads as analysis.
    if " " not in why:
        return str(text or "").strip(), None
    return item, why[0].upper() + why[1:]
