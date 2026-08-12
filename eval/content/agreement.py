"""§8.7 agreement predicates (C4) — exact-decimal, hermetic pure functions."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

NUMERIC_SURFACES = frozenset({"fta_numeric"})
CLAIM_VERDICTS = frozenset({"supported", "contradicted", "unsupported"})

# §16 numeric unit scale table (authoritative in spec §16).
_UNIT_TO_BASE: dict[str, tuple[str, int]] = {
    "USD": ("USD", 0),
    "USD_k": ("USD", 3),
    "USD_m": ("USD", 6),
    "USD_bn": ("USD", 9),
    "percent": ("ratio", -2),
    "ratio": ("ratio", 0),
    "count": ("count", 0),
    "days": ("days", 0),
}


def _coerce_decimal(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    if isinstance(raw, float):
        return None
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, int) and not isinstance(raw, bool):
        return Decimal(raw)
    if isinstance(raw, str):
        try:
            return Decimal(raw)
        except Exception:
            return None
    return None


def normalize_locator_value(kind: str, value: Any) -> str | int | None:
    """§16 per-kind locator normalization."""
    if kind == "page":
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None
    if kind == "section":
        if value is None:
            return None
        text = str(value)
        return re.sub(r"\s+", " ", text.strip()).casefold()
    return None


def normalize_unit_magnitude(magnitude: Any, unit: str | None) -> tuple[Decimal, str] | None:
    """Return base-normalized (magnitude, base_unit) or None if unresolvable."""
    if unit is None or unit not in _UNIT_TO_BASE:
        return None
    mag = _coerce_decimal(magnitude)
    if mag is None:
        return None
    base_unit, exponent = _UNIT_TO_BASE[unit]
    if exponent == 0:
        return mag, base_unit
    shift = Decimal(10) ** exponent
    return mag * shift, base_unit


def values_agree(
    operator_value: dict[str, Any] | None,
    judge_value: dict[str, Any] | None,
) -> bool:
    """Value half of §8.7 agreement predicate."""
    op_null = operator_value is None
    ju_null = judge_value is None
    if op_null and ju_null:
        return True
    if op_null != ju_null:
        return False

    assert operator_value is not None and judge_value is not None
    op_norm = normalize_unit_magnitude(
        operator_value.get("magnitude"), operator_value.get("unit")
    )
    ju_norm = normalize_unit_magnitude(
        judge_value.get("magnitude"), judge_value.get("unit")
    )
    if op_norm is None or ju_norm is None:
        return False
    op_mag, op_base = op_norm
    ju_mag, ju_base = ju_norm
    if op_base != ju_base:
        return False
    return op_mag == ju_mag


def spans_agree(
    operator_span: dict[str, Any] | None,
    judge_span: dict[str, Any] | None,
) -> bool:
    """Span half of §8.7 agreement predicate."""
    op_null = operator_span is None
    ju_null = judge_span is None
    if op_null != ju_null:
        return False
    if op_null and ju_null:
        return True

    assert operator_span is not None and judge_span is not None
    if operator_span.get("chunk_id") != judge_span.get("chunk_id"):
        return False

    op_loc = operator_span.get("locator")
    if op_loc is None:
        return True

    ju_loc = judge_span.get("locator")
    if ju_loc is None:
        return False

    op_kind = op_loc.get("kind")
    ju_kind = ju_loc.get("kind")
    if op_kind != ju_kind:
        return False

    op_norm = normalize_locator_value(op_kind, op_loc.get("value"))
    ju_norm = normalize_locator_value(ju_kind, ju_loc.get("value"))
    return op_norm is not None and ju_norm is not None and op_norm == ju_norm


def verdicts_agree(operator_verdict: str | None, judge_verdict: str | None) -> bool:
    """Non-numeric surface agreement."""
    if operator_verdict not in CLAIM_VERDICTS or judge_verdict not in CLAIM_VERDICTS:
        return False
    return operator_verdict == judge_verdict


def _is_both_null_numeric_claim(claim: dict[str, Any]) -> bool:
    return claim.get("expected_span") is None and claim.get("expected_value") is None


def compute_metrics(
    sample: dict[str, Any],
    judge_outputs: list[dict[str, Any]],
    *,
    surface: str,
) -> dict[str, float]:
    """Return C6 class-conditional figure map for one surface."""
    claims = sample.get("claims") or []
    if len(judge_outputs) != len(claims):
        raise ValueError("judge_outputs length must match sample claims length")

    if surface in NUMERIC_SURFACES:
        return _compute_numeric_metrics(claims, judge_outputs)
    return _compute_non_numeric_metrics(claims, judge_outputs)


def _compute_non_numeric_metrics(
    claims: list[dict[str, Any]],
    judge_outputs: list[dict[str, Any]],
) -> dict[str, float]:
    if not claims:
        return {"verdict_agreement": 0.0}
    agreements = sum(
        1
        for claim, judge in zip(claims, judge_outputs, strict=True)
        if verdicts_agree(claim.get("verdict"), judge.get("verdict"))
    )
    return {"verdict_agreement": agreements / len(claims)}


def _compute_numeric_metrics(
    claims: list[dict[str, Any]],
    judge_outputs: list[dict[str, Any]],
) -> dict[str, float]:
    total = len(claims)
    if total == 0:
        return {
            "resolved_value_fraction": 0.0,
            "resolved_span_fraction": 0.0,
            "locator_labelled_fraction": 0.0,
        }

    resolved_value = [
        (claim, judge)
        for claim, judge in zip(claims, judge_outputs, strict=True)
        if not _is_both_null_numeric_claim(claim) and claim.get("expected_value") is not None
    ]
    resolved_span = [
        (claim, judge)
        for claim, judge in zip(claims, judge_outputs, strict=True)
        if not _is_both_null_numeric_claim(claim) and claim.get("expected_span") is not None
    ]
    span_claims = [c for c in claims if c.get("expected_span") is not None]
    locator_labelled = sum(
        1 for c in span_claims if (c.get("expected_span") or {}).get("locator") is not None
    )

    figures: dict[str, float] = {
        "resolved_value_fraction": len(resolved_value) / total,
        "resolved_span_fraction": len(resolved_span) / total,
        "locator_labelled_fraction": (
            locator_labelled / len(span_claims) if span_claims else 0.0
        ),
    }

    if resolved_value:
        val_agree = sum(
            1
            for claim, judge in resolved_value
            if values_agree(claim.get("expected_value"), judge.get("extracted_value"))
        )
        figures["value_agreement"] = val_agree / len(resolved_value)
    if resolved_span:
        span_agree = sum(
            1
            for claim, judge in resolved_span
            if spans_agree(claim.get("expected_span"), judge.get("cited_span"))
        )
        figures["span_agreement"] = span_agree / len(resolved_span)

    return figures


def evaluate_thresholds(
    surface: str,
    figures: dict[str, float],
    *,
    verdict_threshold: float = 0.80,
    value_threshold: float = 0.90,
    span_threshold: float = 0.80,
) -> tuple[bool, list[str]]:
    """Return (pass, failure_reasons) per C5."""
    reasons: list[str] = []
    if surface in NUMERIC_SURFACES:
        rvf = figures.get("resolved_value_fraction", 0.0)
        rsf = figures.get("resolved_span_fraction", 0.0)
        if rvf <= 0:
            reasons.append("value resolved population empty (HALT-11 floor)")
        elif figures.get("value_agreement", 0.0) < value_threshold:
            reasons.append(
                f"value_agreement {figures.get('value_agreement'):.4f} < {value_threshold}"
            )
        if rsf <= 0:
            reasons.append("span resolved population empty (HALT-11 floor)")
        elif figures.get("span_agreement", 0.0) < span_threshold:
            reasons.append(
                f"span_agreement {figures.get('span_agreement'):.4f} < {span_threshold}"
            )
        return len(reasons) == 0, reasons

    if figures.get("verdict_agreement", 0.0) < verdict_threshold:
        reasons.append(
            f"verdict_agreement {figures.get('verdict_agreement'):.4f} < {verdict_threshold}"
        )
    return len(reasons) == 0, reasons
