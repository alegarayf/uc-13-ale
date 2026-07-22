"""Deterministic render-time TL;DR projection from canonical orchestrator bundle."""

from __future__ import annotations

import ast
import copy
import re
from typing import Any

from agents.orchestrator.formatters import (
    format_agent_flag,
    format_diligence_entry,
    format_kpi_value,
)

# Match populate.merge_risks_from_flags L117 — lower rank = more severe.
SEVERITY_RANK: dict[str, int] = {"critical": 0, "material": 1, "track": 2}

_ANNUAL_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_MONTHLY_YEAR_RE = re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}\b", re.IGNORECASE)
_YEAR_EXTRACT_RE = re.compile(r"(?:19|20)\d{2}")
_RELATED_SUFFIX_RE = re.compile(r" \(\+\d+ related\)$")

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_REVENUE_QUALITY_SCALAR_CAP = 4
_REVENUE_QUALITY_KPI_CAP = 2
_REVENUE_QUALITY_TOTAL_CAP = 6

_CONCERN_PRIORITY_KEYWORDS: tuple[str, ...] = (
    "founder",
    "key-person",
    "key person",
    "lease",
    "insurance",
    "change-of-control",
    "consent",
    "e&o",
    "cyber",
    "d&o",
    "workers' comp",
)

_SEVERITY_SCORE: dict[str, int] = {"critical": 3, "material": 2, "track": 1}

RISK_DISPLAY_TITLES: dict[str, str] = {
    "tier4_addback": "Undocumented Tier 4 addbacks",
    "open_legal_matter_other": "Open legal matters",
}

_PRELIMINARY_DIGEST_SECTION_TAGS: tuple[str, ...] = (
    "Business Snapshot",
    "Financial Strip",
    "Revenue Quality",
    "KPI Dashboard",
    "Legal Snapshot",
    "Quality of Earnings",
    "Top Risks",
    "Confidence by Area",
)

_SECTION_TAG_RE = re.compile(
    r"\[("
    + "|".join(re.escape(tag) for tag in _PRELIMINARY_DIGEST_SECTION_TAGS)
    + r")\]"
)


def _section_data_for_tag(tag: str, bundle: dict[str, Any]) -> Any:
    if tag == "Business Snapshot":
        return {
            "company_framing": bundle.get("company_framing"),
            "revenue_quality": bundle.get("revenue_quality"),
        }
    key_by_tag = {
        "Financial Strip": "financials",
        "Revenue Quality": "revenue_quality",
        "KPI Dashboard": "kpi_dashboard",
        "Legal Snapshot": "legal",
        "Quality of Earnings": "qoe",
        "Top Risks": "risks",
        "Confidence by Area": "confidence_by_area",
    }
    key = key_by_tag.get(tag)
    return bundle.get(key) if key else None


def _collect_nested_source_docs(obj: Any) -> list[str]:
    """Collect unique non-blank ``source_doc`` values from a section subtree."""
    refs: list[str] = []
    seen: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            doc = str(node.get("source_doc") or "").strip()
            if doc and doc not in seen:
                seen.add(doc)
                refs.append(doc)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(obj)
    return refs


def _source_docs_for_section_tag(tag: str, bundle: dict[str, Any]) -> list[str]:
    if tag not in _PRELIMINARY_DIGEST_SECTION_TAGS:
        return []
    section = _section_data_for_tag(tag, bundle)
    if section is None:
        return []
    return _collect_nested_source_docs(section)


def _resolve_section_tag_citations(preliminary_digest: str, bundle: dict[str, Any]) -> str:
    """Map fixed-vocabulary section tags to real ``source_doc`` refs from that section only."""

    def _replace_tag(match: re.Match[str]) -> str:
        tag = match.group(1)
        refs = _source_docs_for_section_tag(tag, bundle)
        if refs:
            return f"[{tag}: {', '.join(refs)}]"
        return match.group(0)

    return _SECTION_TAG_RE.sub(_replace_tag, preliminary_digest)


def compress_for_tldr(bundle: dict[str, Any]) -> dict[str, Any]:
    """Build lossy ``tldr_view`` projection; never mutates ``bundle`` (K1)."""
    snapshot = copy.deepcopy(bundle)
    source = bundle
    executive = source.get("executive") or {}
    preliminary = executive.get("preliminary_view") or {}
    financials = source.get("financials") or {}
    revenue_quality = source.get("revenue_quality") or {}
    company_framing = source.get("company_framing") or {}

    risks = source.get("risks") or []
    strengths = _rank_preliminary_items(preliminary.get("strengths") or [], risks)
    concerns = _rank_preliminary_items(preliminary.get("concerns") or [], risks)
    in_one_line, show_in_one_line = _compress_in_one_line(
        executive.get("in_one_line") or "", strengths
    )

    view = {
        "in_one_line": in_one_line,
        "show_in_one_line": show_in_one_line,
        "strengths": strengths,
        "concerns": concerns,
        "business_snapshot": _compress_business_snapshot(company_framing, revenue_quality),
        "business_snapshot_narrative": _optional_executive_string(
            executive, "business_snapshot_narrative"
        ),
        "thesis_bullets": _optional_executive_string_list(executive, "thesis_bullets"),
        "key_watchouts": _optional_executive_string_list(executive, "key_watchouts"),
        "mitigants_digest": _optional_executive_string(executive, "mitigants_digest"),
        "confidence_rationale": _optional_executive_string(
            executive, "confidence_rationale"
        ),
        "preliminary_digest": _resolve_preliminary_digest_for_tldr(executive, source),
        "financial": _compress_financial(financials),
        "revenue_quality": _compress_revenue_quality(
            revenue_quality, source.get("kpi_dashboard") or []
        ),
        "risks": _compress_risks(source.get("risks") or []),
        "questions": _compress_questions(source.get("diligence_questions") or []),
    }
    if bundle != snapshot:
        raise RuntimeError("compress_for_tldr mutated input bundle")
    return view


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return not text or text == "—"


def _optional_executive_string(executive: dict[str, Any], key: str) -> str | None:
    """Project optional Stage 6 narrative from ``executive``; absent → ``None``."""
    value = executive.get(key)
    if _is_blank(value):
        return None
    return str(value).strip()


def _optional_executive_string_list(executive: dict[str, Any], key: str) -> list[str] | None:
    """Project optional Stage 6 string[] from ``executive``; absent/empty → ``None``."""
    value = executive.get(key)
    if not isinstance(value, list):
        return None
    bullets = [str(item).strip() for item in value if not _is_blank(item)]
    return bullets if bullets else None


def _resolve_preliminary_digest_for_tldr(
    executive: dict[str, Any], bundle: dict[str, Any]
) -> str | None:
    """Project ``preliminary_digest`` with deterministic section-tag citation resolution."""
    raw = _optional_executive_string(executive, "preliminary_digest")
    if raw is None:
        return None
    return _resolve_section_tag_citations(raw, bundle)


def _first_sentence(text: str, max_len: int = 200) -> str:
    """Return the first complete sentence, capped at a sentence boundary within max_len."""
    text = text.strip()
    if not text:
        return ""
    parts = _SENTENCE_SPLIT_RE.split(text, maxsplit=1)
    first = parts[0]
    if len(first) <= max_len:
        return first
    window = first[:max_len]
    best_end = max(window.rfind(ch) for ch in ".!?")
    if best_end >= 0:
        return first[: best_end + 1]
    return first


def _item_severity_score(item: str, risks: list[Any], keywords: tuple[str, ...]) -> int:
    """Rank score: max risk-severity crosswalk hit + keyword hits (T9 §4.8)."""
    text = item.casefold()
    score = 0
    for risk in risks:
        if not isinstance(risk, dict):
            continue
        risk_token = str(risk.get("risk") or "").casefold()
        if not risk_token or risk_token not in text:
            continue
        severity = str(risk.get("severity") or "track").casefold()
        score = max(score, _SEVERITY_SCORE.get(severity, 1))
    for keyword in keywords:
        if keyword.casefold() in text:
            score += 1
    return score


def _rank_preliminary_items(
    items: list[Any],
    risks: list[Any],
    keywords: tuple[str, ...] = _CONCERN_PRIORITY_KEYWORDS,
) -> list[str]:
    indexed = [
        (idx, str(item).strip())
        for idx, item in enumerate(items)
        if not _is_blank(item)
    ]
    ranked = sorted(
        indexed,
        key=lambda pair: (-_item_severity_score(pair[1], risks, keywords), pair[0]),
    )
    return [text for _, text in ranked[:3]]


def _compress_in_one_line(in_one_line: str, strengths: list[str]) -> tuple[str, bool]:
    text = in_one_line.strip()
    if not text and strengths:
        text = _first_sentence(strengths[0])
    if not text:
        return "", False
    if strengths:
        strength_head = strengths[0].strip().casefold()
        candidate = text.strip().casefold()
        if strength_head.startswith(candidate) or candidate == strength_head:
            return "", False
    return text, True


def _compress_business_snapshot(
    company_framing: dict[str, Any],
    revenue_quality: dict[str, Any],
) -> str | None:
    overview = [
        str(b).strip()
        for b in (company_framing.get("overview_bullets") or [])
        if not _is_blank(b)
    ]
    rq_fields = (
        revenue_quality.get("scale_narrative"),
        revenue_quality.get("concentration"),
        revenue_quality.get("end_market_mix"),
        revenue_quality.get("retention_notes"),
    )
    if not overview and all(_is_blank(f) for f in rq_fields):
        return None

    sentences: list[str] = []
    if overview:
        sentences.append(overview[0].rstrip(".") + ".")
    for field in (revenue_quality.get("concentration"), revenue_quality.get("retention_notes")):
        if not _is_blank(field):
            sentences.append(str(field).strip().rstrip(".") + ".")
        if len(sentences) >= 2:
            break
    return " ".join(sentences[:2]) if sentences else None


def _financial_row_empty(row: dict[str, Any]) -> bool:
    return all(_is_blank(row.get(k)) for k in ("revenue", "gross_profit", "ebitda"))


def _parse_row_year(row: dict[str, Any]) -> int:
    year_text = str(row.get("year") or "")
    match = _YEAR_EXTRACT_RE.search(year_text)
    return int(match.group(0)) if match else 0


def _is_annual_row(row: dict[str, Any]) -> bool:
    year_text = str(row.get("year") or "")
    if _ANNUAL_YEAR_RE.fullmatch(year_text.strip()):
        return True
    if _MONTHLY_YEAR_RE.search(year_text):
        return False
    return bool(_ANNUAL_YEAR_RE.search(year_text))


def _compress_financial(financials: dict[str, Any]) -> dict[str, Any]:
    rows_in = [
        r for r in (financials.get("table_rows") or []) if isinstance(r, dict) and not _financial_row_empty(r)
    ]
    annual = sorted(
        [r for r in rows_in if _is_annual_row(r)],
        key=_parse_row_year,
        reverse=True,
    )
    monthly = sorted(
        [r for r in rows_in if not _is_annual_row(r)],
        key=_parse_row_year,
        reverse=True,
    )
    rows = (annual + monthly)[:4]

    observations = [
        str(o).strip()
        for o in (financials.get("observations") or [])
        if not _is_blank(o)
    ][:2]

    show = bool(rows or observations)
    return {"rows": rows, "observations": observations, "show": show}


def _kpi_lines_for_revenue_quality(kpi_dashboard: list[Any]) -> list[str]:
    """Fold KPI dashboard rows into Revenue Quality prose (Revision 2 Bucket A)."""
    lines: list[str] = []
    for raw in kpi_dashboard:
        if not isinstance(raw, dict):
            continue
        display_name = str(raw.get("display_name") or "").strip()
        stated_value = format_kpi_value(raw.get("stated_value")).strip()
        if _is_blank(display_name) and _is_blank(stated_value):
            continue
        if display_name and stated_value:
            lines.append(f"{display_name}: {stated_value}")
        elif display_name:
            lines.append(display_name)
        else:
            lines.append(stated_value)
        if len(lines) >= _REVENUE_QUALITY_KPI_CAP:
            break
    return lines


def _compress_revenue_quality(
    revenue_quality: dict[str, Any],
    kpi_dashboard: list[Any] | None = None,
) -> dict[str, Any]:
    scalar_lines = [
        str(v).strip()
        for v in (
            revenue_quality.get("scale_narrative"),
            revenue_quality.get("concentration"),
            revenue_quality.get("end_market_mix"),
            revenue_quality.get("retention_notes"),
        )
        if not _is_blank(v)
    ][: _REVENUE_QUALITY_SCALAR_CAP]
    kpi_lines = _kpi_lines_for_revenue_quality(kpi_dashboard or [])
    lines = (scalar_lines + kpi_lines)[: _REVENUE_QUALITY_TOTAL_CAP]
    return {"lines": lines, "show": bool(lines)}


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _truncate_table_cell(text: str, max_len: int = 120) -> str:
    """Trim table cell text at word boundary with ellipsis (T10)."""
    text = text.strip()
    if len(text) <= max_len:
        return text

    suffix_match = _RELATED_SUFFIX_RE.search(text)
    suffix = suffix_match.group(0) if suffix_match else ""
    base = text[: -len(suffix)] if suffix else text
    budget = max_len - len(suffix)

    if len(base) <= budget:
        return base + suffix

    cut = base[: budget - 3]
    last_space = cut.rfind(" ")
    if last_space > 0:
        cut = cut[:last_space]
    return cut + "..." + suffix


def _risk_display_title(key: str) -> str:
    if key in RISK_DISPLAY_TITLES:
        return RISK_DISPLAY_TITLES[key]
    return " ".join(word.capitalize() for word in key.split("_"))


def _clean_risk_evidence(evidence: str, risk_key: str) -> str:
    """Readable Evidence prose — no raw dict repr or bare metric keys."""
    text = evidence.strip()
    if not text:
        return ""

    if text.startswith("{"):
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            parsed = None
        if isinstance(parsed, dict):
            cleaned = format_agent_flag(parsed)
            if cleaned:
                return cleaned

    if text == risk_key or text in RISK_DISPLAY_TITLES:
        return _risk_display_title(text if text in RISK_DISPLAY_TITLES else risk_key)

    return text


def _compress_risks(risks: list[Any]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in risks:
        if not isinstance(row, dict):
            continue
        key = str(row.get("risk") or "")
        groups.setdefault(key, []).append(row)

    merged: list[dict[str, Any]] = []
    for risk_key, group in groups.items():
        best = min(
            group,
            key=lambda r: (
                SEVERITY_RANK.get(str(r.get("severity") or "track"), 9),
                str(r.get("evidence") or ""),
            ),
        )
        evidence = _clean_risk_evidence(str(best.get("evidence") or ""), risk_key)
        if len(group) > 1:
            suffix = f" (+{len(group) - 1} related)"
            evidence = (evidence + suffix) if evidence else suffix.strip()
        merged.append(
            {
                "risk": risk_key,
                "display_title": _risk_display_title(risk_key),
                "severity": str(best.get("severity") or "track"),
                "evidence": _truncate_table_cell(evidence),
            }
        )

    merged.sort(
        key=lambda r: (
            SEVERITY_RANK.get(str(r.get("severity") or "track"), 9),
            str(r.get("risk") or ""),
        )
    )
    return merged[:5]


def _compress_questions(questions: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in questions:
        if not isinstance(row, dict):
            continue
        question = format_diligence_entry(row.get("question") or "")
        if not question:
            continue
        result.append(
            {
                "category": str(row.get("category") or ""),
                "question": question,
                "priority": str(row.get("priority") or ""),
            }
        )
        if len(result) >= 5:
            break
    return result
