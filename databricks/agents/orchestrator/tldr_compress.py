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

_REVENUE_RE = re.compile(r"\$[\d.]+[MBK]?", re.IGNORECASE)
_CAGR_RE = re.compile(r"(?:cagr|growth)[^\d%]*(\d+\.?\d*%)", re.IGNORECASE)
_GROWTH_PCT_RE = re.compile(r"\d+\.?\d*%\s*(?:cagr|growth|yoy)", re.IGNORECASE)
_MARGIN_RE = re.compile(r"(?:ebitda\s*)?margin[^\d%]*(\d+\.?\d*%)", re.IGNORECASE)
_ANNUAL_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_MONTHLY_YEAR_RE = re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}\b", re.IGNORECASE)
_YEAR_EXTRACT_RE = re.compile(r"(?:19|20)\d{2}")

_QOE_COLLAPSE_METRIC = "tier4_addback"
_QOE_COLLAPSE_BULLET = (
    "{n} Tier 4 addbacks with undocumented or zero amounts — "
    "unlikely to survive buyer QoE (see full report)."
)
_HEADLINE_FALLBACK_NOTE = (
    "Headline financial metrics incomplete in source extracts — "
    "see Preliminary View and full report."
)


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

    headline = _compress_headline(headline_metrics, preliminary)
    strengths, concerns = _compress_preliminary_lists(preliminary)
    in_one_line = _compress_in_one_line(executive.get("in_one_line") or "", strengths)

    view = {
        "headline": headline,
        "in_one_line": in_one_line,
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


def _headline_from_preliminary(preliminary: dict[str, Any]) -> list[dict[str, str]]:
    texts: list[str] = []
    for key in ("strengths", "concerns"):
        for item in preliminary.get(key) or []:
            if not _is_blank(item):
                texts.append(str(item))

    metrics: list[dict[str, str]] = []
    seen_values: set[str] = set()

    def _add(label: str, value: str) -> None:
        if value in seen_values or len(metrics) >= 4:
            return
        seen_values.add(value)
        metrics.append({"label": label, "value": value})

    for text in texts:
        for match in _REVENUE_RE.finditer(text):
            _add("Revenue", match.group(0))
        for match in _CAGR_RE.finditer(text):
            _add("Revenue CAGR", match.group(1))
        for match in _GROWTH_PCT_RE.finditer(text):
            _add("Growth", match.group(0))
        for match in _MARGIN_RE.finditer(text):
            _add("EBITDA Margin", match.group(1))

    return metrics


def _compress_preliminary_lists(preliminary: dict[str, Any]) -> tuple[list[str], list[str]]:
    strengths = [
        str(s).strip()
        for s in (preliminary.get("strengths") or [])
        if not _is_blank(s)
    ][:3]
    concerns = [
        str(c).strip()
        for c in (preliminary.get("concerns") or [])
        if not _is_blank(c)
    ][:3]
    return strengths, concerns


def _compress_in_one_line(in_one_line: str, strengths: list[str]) -> str:
    text = in_one_line.strip()
    if text:
        return text
    if strengths:
        return strengths[0][:160]
    return ""


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
        merged.append(
            {
                "risk": risk_key,
                "severity": str(best.get("severity") or "track"),
                "evidence": evidence,
                "mitigant": str(best.get("mitigant_or_question") or ""),
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
