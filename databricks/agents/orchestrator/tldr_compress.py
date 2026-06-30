"""Deterministic render-time TL;DR projection from canonical orchestrator bundle."""

from __future__ import annotations

import copy
import re
from typing import Any

from agents.orchestrator.formatters import (
    format_agent_flag,
    format_diligence_entry,
    is_operator_gap,
    normalize_gap,
)

# Match populate.merge_risks_from_flags L117 — lower rank = more severe.
SEVERITY_RANK: dict[str, int] = {"critical": 0, "material": 1, "track": 2}

_HEADLINE_FIELD_LABELS: tuple[tuple[str, str], ...] = (
    ("ltm_revenue", "LTM Revenue"),
    ("ltm_ebitda", "LTM EBITDA"),
    ("ltm_ebitda_margin_pct", "EBITDA Margin"),
    ("revenue_cagr", "Revenue CAGR"),
)

_DOLLAR_RE = re.compile(r"\$[\d,]+(?:\.\d+)?[MBK]?", re.IGNORECASE)
_CAGR_RE = re.compile(r"(?:cagr|growth)[^\d%]*(\d+\.?\d*%)", re.IGNORECASE)
_GROWTH_PCT_RE = re.compile(r"\d+\.?\d*%\s*(?:cagr|growth|yoy)", re.IGNORECASE)
_GROSS_MARGIN_RE = re.compile(
    r"(?:gross\s+margin[^\d%]*(\d+\.?\d*%)|(\d+\.?\d*%)\s*gross\s+margin)",
    re.IGNORECASE,
)
_EBITDA_MARGIN_RE = re.compile(
    r"(?:ebitda\s+margin[^\d%]*(\d+\.?\d*%)|(\d+\.?\d*%)\s*ebitda\s+margin)",
    re.IGNORECASE,
)
_ANNUAL_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_MONTHLY_YEAR_RE = re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}\b", re.IGNORECASE)
_YEAR_EXTRACT_RE = re.compile(r"(?:19|20)\d{2}")
_RELATED_SUFFIX_RE = re.compile(r" \(\+\d+ related\)$")

_QOE_COLLAPSE_METRIC = "tier4_addback"
_QOE_COLLAPSE_BULLET = (
    "{n} Tier 4 addbacks with undocumented or zero amounts — "
    "unlikely to survive buyer QoE (see full report)."
)
_HEADLINE_FALLBACK_NOTE = (
    "Headline financial metrics incomplete in source extracts — "
    "see Preliminary View and full report."
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

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


def compress_for_tldr(bundle: dict[str, Any]) -> dict[str, Any]:
    """Build lossy ``tldr_view`` projection; never mutates ``bundle`` (K1)."""
    snapshot = copy.deepcopy(bundle)
    source = bundle
    executive = source.get("executive") or {}
    preliminary = executive.get("preliminary_view") or {}
    headline_metrics = source.get("headline_metrics") or {}
    financials = source.get("financials") or {}
    revenue_quality = source.get("revenue_quality") or {}
    company_framing = source.get("company_framing") or {}
    legal = source.get("legal") or {}
    qoe = source.get("qoe") or {}

    risks = source.get("risks") or []
    headline = _compress_headline(headline_metrics, preliminary)
    strengths = _rank_preliminary_items(preliminary.get("strengths") or [], risks)
    concerns = _rank_preliminary_items(preliminary.get("concerns") or [], risks)
    in_one_line, show_in_one_line = _compress_in_one_line(
        executive.get("in_one_line") or "", strengths
    )

    view = {
        "headline": headline,
        "in_one_line": in_one_line,
        "show_in_one_line": show_in_one_line,
        "strengths": strengths,
        "concerns": concerns,
        "business_snapshot": _compress_business_snapshot(company_framing, revenue_quality),
        "financial": _compress_financial(financials),
        "revenue_quality": _compress_revenue_quality(revenue_quality),
        "kpi": _compress_kpi(source.get("kpi_dashboard") or []),
        "legal": _compress_legal(legal),
        "qoe": _compress_qoe(qoe),
        "risks": _compress_risks(source.get("risks") or []),
        "questions": _compress_questions(source.get("diligence_questions") or []),
        "open_items": _compress_open_items(source.get("data_room_gaps") or []),
        "confidence_by_area": dict(source.get("confidence_by_area") or {}),
        "show_confidence_table": bool(source.get("confidence_by_area")),
    }
    if bundle != snapshot:
        raise RuntimeError("compress_for_tldr mutated input bundle")
    return view


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return not text or text == "—"


def _compress_headline(
    headline_metrics: dict[str, Any],
    preliminary: dict[str, Any],
) -> dict[str, Any]:
    metrics: list[dict[str, str]] = []
    for key, label in _HEADLINE_FIELD_LABELS:
        value = headline_metrics.get(key)
        if not _is_blank(value):
            metrics.append({"label": label, "value": str(value).strip()})
        if len(metrics) >= 4:
            break

    if not metrics:
        metrics = _headline_from_preliminary(preliminary)

    fallback_note: str | None = None
    if len(metrics) < 2:
        fallback_note = _HEADLINE_FALLBACK_NOTE

    return {"metrics": metrics[:4], "fallback_note": fallback_note}


def _parse_dollar_magnitude(amount: str) -> float:
    """Numeric magnitude for comparing dollar matches in the same sentence."""
    stripped = amount.lstrip("$").replace(",", "")
    multiplier = 1.0
    if stripped and stripped[-1].upper() in "KMB":
        suffix = stripped[-1].upper()
        stripped = stripped[:-1]
        multiplier = {"K": 1_000.0, "M": 1_000_000.0, "B": 1_000_000_000.0}[suffix]
    try:
        return float(stripped) * multiplier
    except ValueError:
        return 0.0


def _best_dollar_match(text: str) -> str | None:
    """Return the single best dollar amount per text block (F-004)."""
    matches = list(_DOLLAR_RE.finditer(text))
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0].group(0)

    ranked = sorted(
        matches,
        key=lambda m: (
            _parse_dollar_magnitude(m.group(0)),
            bool(re.search(r"[KMB]$", m.group(0), re.IGNORECASE)),
            len(m.group(0)),
        ),
        reverse=True,
    )
    return ranked[0].group(0)


def _margin_pct_from_match(match: re.Match[str]) -> str:
    return match.group(1) or match.group(2)


_BLENDED_MARGIN_KEYWORDS: tuple[str, ...] = (
    "pro forma",
    "adjusted",
    "ttm",
    "blended",
    "company-wide",
)
_SEGMENT_MARGIN_KEYWORDS: tuple[str, ...] = ("hha", "live-in", "live in")


def _margin_label_from_context(
    text: str,
    match: re.Match[str],
    *,
    is_only_margin: bool,
    margin_ordinal: int,
) -> str:
    """Disambiguate gross margin ribbon label from ±80 char context (T12)."""
    start = max(0, match.start() - 80)
    end = min(len(text), match.end() + 80)
    before = text[start:match.start()].casefold()
    local = text[max(0, match.start() - 40):min(len(text), match.end() + 20)].casefold()
    window = text[start:end].casefold()

    if any(kw in local for kw in _SEGMENT_MARGIN_KEYWORDS):
        return "Gross Margin (HHA/Live-In)"
    if any(kw in before for kw in _BLENDED_MARGIN_KEYWORDS):
        return "Gross Margin (Blended)"
    if any(kw in window for kw in _BLENDED_MARGIN_KEYWORDS):
        return "Gross Margin (Blended)"
    if is_only_margin:
        return "Gross Margin"
    if margin_ordinal > 0:
        return "Gross Margin (Segment)"
    return "Gross Margin"


def _headline_from_preliminary(preliminary: dict[str, Any]) -> list[dict[str, str]]:
    texts: list[str] = []
    for key in ("strengths", "concerns"):
        for item in preliminary.get(key) or []:
            if not _is_blank(item):
                texts.append(str(item))

    metrics: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()

    gross_margin_occurrences: list[tuple[int, str, re.Match[str]]] = []
    for text_idx, text in enumerate(texts):
        for match in _GROSS_MARGIN_RE.finditer(text):
            gross_margin_occurrences.append((text_idx, text, match))
    total_margins = len(gross_margin_occurrences)
    margin_ordinals = {
        (text_idx, match.start(), match.end()): idx
        for idx, (text_idx, _, match) in enumerate(gross_margin_occurrences)
    }

    def _add(label: str, value: str) -> None:
        key = (label, value)
        if key in seen_pairs or len(metrics) >= 4:
            return
        seen_pairs.add(key)
        metrics.append({"label": label, "value": value})

    for text_idx, text in enumerate(texts):
        dollar = _best_dollar_match(text)
        if dollar:
            _add("Revenue", dollar)
        for match in _CAGR_RE.finditer(text):
            _add("Revenue CAGR", match.group(1))
        for match in _GROWTH_PCT_RE.finditer(text):
            _add("Growth", match.group(0))
        for match in _GROSS_MARGIN_RE.finditer(text):
            label = _margin_label_from_context(
                text,
                match,
                is_only_margin=(total_margins == 1),
                margin_ordinal=margin_ordinals[(text_idx, match.start(), match.end())],
            )
            _add(label, _margin_pct_from_match(match))
        for match in _EBITDA_MARGIN_RE.finditer(text):
            _add("EBITDA Margin", _margin_pct_from_match(match))

    return metrics


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


def _compress_revenue_quality(revenue_quality: dict[str, Any]) -> dict[str, Any]:
    lines = [
        str(v).strip()
        for v in (
            revenue_quality.get("scale_narrative"),
            revenue_quality.get("concentration"),
            revenue_quality.get("end_market_mix"),
            revenue_quality.get("retention_notes"),
        )
        if not _is_blank(v)
    ][:2]
    return {"lines": lines, "show": bool(lines)}


def _compress_kpi(kpi_dashboard: list[Any]) -> dict[str, Any]:
    rows = [
        r
        for r in kpi_dashboard
        if isinstance(r, dict)
        and (not _is_blank(r.get("stated_value")) or not _is_blank(r.get("display_name")))
    ][:5]
    return {"rows": rows, "show": bool(rows)}


def _compress_legal(legal: dict[str, Any]) -> dict[str, Any]:
    assessed = legal.get("assessed_count")
    total = legal.get("checklist_total") or 11
    assessed_label = f"{assessed} / {total}" if assessed is not None else f"— / {total}"
    bullets = [
        format_agent_flag(flag)
        for flag in (legal.get("top_flags") or [])
        if isinstance(flag, dict)
    ]
    bullets = [b for b in bullets if b][:6]
    show = bool(bullets) or assessed is not None
    return {
        "assessed_label": assessed_label,
        "section_confidence": str(legal.get("section_confidence") or ""),
        "bullets": bullets,
        "show": show,
    }


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


def _compress_qoe(qoe: dict[str, Any]) -> dict[str, Any]:
    flags = [f for f in (qoe.get("flags") or []) if isinstance(f, dict)]
    summary = _truncate(str(qoe.get("tier_summary") or "").strip(), 200)

    by_metric: dict[str, list[dict[str, Any]]] = {}
    for flag in flags:
        metric = str(flag.get("metric") or "")
        by_metric.setdefault(metric, []).append(flag)

    collapse_group: list[dict[str, Any]] | None = None
    for group in by_metric.values():
        if len(group) >= 3:
            if collapse_group is None or len(group) > len(collapse_group):
                collapse_group = group

    bullets: list[str] = []
    if collapse_group is not None:
        metric = str(collapse_group[0].get("metric") or "")
        if metric == _QOE_COLLAPSE_METRIC:
            bullets.append(_QOE_COLLAPSE_BULLET.format(n=len(collapse_group)))
        else:
            bullets.append(
                f"{len(collapse_group)} related {metric} flags — see full report."
            )
    else:
        bullets = [format_agent_flag(f) for f in flags[:2]]
        bullets = [b for b in bullets if b]

    show = bool(summary or bullets)
    return {"summary": summary, "bullets": bullets[:2], "show": show}


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
        evidence = str(best.get("evidence") or "").strip()
        if len(group) > 1:
            suffix = f" (+{len(group) - 1} related)"
            evidence = (evidence + suffix) if evidence else suffix.strip()
        mitigant = str(best.get("mitigant_or_question") or "").strip()
        merged.append(
            {
                "risk": risk_key,
                "display_title": _risk_display_title(risk_key),
                "severity": str(best.get("severity") or "track"),
                "evidence": _truncate_table_cell(evidence),
                "mitigant": _truncate_table_cell(mitigant),
            }
        )

    merged.sort(
        key=lambda r: (
            SEVERITY_RANK.get(str(r.get("severity") or "track"), 9),
            str(r.get("risk") or ""),
        )
    )
    return merged[:5]


def _gap_included(row: dict[str, Any]) -> bool:
    if is_operator_gap(str(row.get("item") or "")):
        return False
    priority = str(row.get("priority") or "").lower()
    if priority == "high":
        return True
    if row.get("source_agent") == "legal" and row.get("fill_state") == "gap_correct":
        return True
    return False


def _compress_open_items(gaps: list[Any]) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for row in gaps:
        if not isinstance(row, dict) or not _gap_included(row):
            continue
        text = str(row.get("item") or "").strip()
        if not text:
            continue
        norm = normalize_gap(text)
        if norm in seen:
            continue
        seen.add(norm)
        items.append(text)
        if len(items) >= 5:
            break
    return items


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
