"""§8.7 agreement predicates (C4) — exact-decimal, hermetic pure functions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

NUMERIC_SURFACES = frozenset({"fta_numeric"})
CLAIM_VERDICTS = frozenset({"supported", "contradicted", "unsupported"})

MIN_SAMPLE_COUNT = 25
MAX_MAJORITY_CLASS_FRACTION = 0.60
MIN_DISTINCT_EXPECTED_CHUNK_IDS = 8
DEGENERATE_FLOOR_MARGIN = 0.10

_PIN_IDS = ("P1", "P2", "P3", "P4")
_OMITTED_REASON = "omitted (sample_composition is None)"
_NUMERIC_INAPPLICABLE_REASON = "inapplicable (numeric surface)"


@dataclass(frozen=True)
class SampleComposition:
    retained_count: int
    verdict_counts: dict[str, int]
    distinct_expected_chunk_ids: int


@dataclass(frozen=True)
class ThresholdResult:
    passed: bool
    failure_reasons: list[str]
    unevaluated_pins: list[str]

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


def compute_sample_composition(sample: dict[str, Any]) -> SampleComposition:
    """Derive P1–P4 composition fields from sample claims."""
    claims = sample.get("claims") or []
    verdict_counts: dict[str, int] = {}
    chunk_ids: set[Any] = set()
    for claim in claims:
        verdict = claim.get("verdict")
        if verdict in CLAIM_VERDICTS:
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
        chunk_id = (claim.get("expected_span") or {}).get("chunk_id")
        if chunk_id is not None:
            chunk_ids.add(chunk_id)
    return SampleComposition(
        retained_count=len(claims),
        verdict_counts=verdict_counts,
        distinct_expected_chunk_ids=len(chunk_ids),
    )


def _majority_class_fraction(composition: SampleComposition) -> float:
    if composition.retained_count <= 0:
        return 1.0
    if not composition.verdict_counts:
        return 1.0
    return max(composition.verdict_counts.values()) / composition.retained_count


def _append_c5_reasons(
    surface: str,
    figures: dict[str, float],
    reasons: list[str],
    *,
    verdict_threshold: float,
    value_threshold: float,
    span_threshold: float,
) -> None:
    if surface in NUMERIC_SURFACES:
        rvf = figures.get("resolved_value_fraction", 0.0)
        rsf = figures.get("resolved_span_fraction", 0.0)
        if rvf <= 0:
            reasons.append(
                "value resolved population empty (HALT-29 / §8.7 non-empty floor)"
            )
        elif figures.get("value_agreement", 0.0) < value_threshold:
            reasons.append(
                f"value_agreement {figures.get('value_agreement'):.4f} < {value_threshold}"
            )
        if rsf <= 0:
            reasons.append(
                "span resolved population empty (HALT-29 / §8.7 non-empty floor)"
            )
        elif figures.get("span_agreement", 0.0) < span_threshold:
            reasons.append(
                f"span_agreement {figures.get('span_agreement'):.4f} < {span_threshold}"
            )
        return

    if figures.get("verdict_agreement", 0.0) < verdict_threshold:
        reasons.append(
            f"verdict_agreement {figures.get('verdict_agreement'):.4f} < {verdict_threshold}"
        )


def _append_composition_pin_reasons(
    surface: str,
    figures: dict[str, float],
    composition: SampleComposition,
    reasons: list[str],
    unevaluated: list[str],
) -> None:
    if composition.retained_count < MIN_SAMPLE_COUNT:
        reasons.append(
            f"P1: retained_count {composition.retained_count} < {MIN_SAMPLE_COUNT}"
        )

    numeric = surface in NUMERIC_SURFACES
    if numeric:
        unevaluated.append(f"P2: {_NUMERIC_INAPPLICABLE_REASON}")
    else:
        majority = _majority_class_fraction(composition)
        if majority > MAX_MAJORITY_CLASS_FRACTION:
            reasons.append(
                f"P2: majority class fraction {majority:.4f} > {MAX_MAJORITY_CLASS_FRACTION}"
            )

    if composition.distinct_expected_chunk_ids < MIN_DISTINCT_EXPECTED_CHUNK_IDS:
        reasons.append(
            f"P3: distinct_expected_chunk_ids {composition.distinct_expected_chunk_ids} "
            f"< {MIN_DISTINCT_EXPECTED_CHUNK_IDS}"
        )

    if numeric:
        unevaluated.append(f"P4: {_NUMERIC_INAPPLICABLE_REASON}")
        return

    majority = _majority_class_fraction(composition)
    verdict_agreement = figures.get("verdict_agreement", 0.0)
    floor = majority + DEGENERATE_FLOOR_MARGIN
    if verdict_agreement < floor:
        reasons.append(
            f"P4: verdict_agreement {verdict_agreement:.4f} < majority baseline "
            f"{majority:.4f} + {DEGENERATE_FLOOR_MARGIN}"
        )


def evaluate_thresholds(
    surface: str,
    figures: dict[str, float],
    *,
    verdict_threshold: float = 0.80,
    value_threshold: float = 0.90,
    span_threshold: float = 0.80,
    sample_composition: SampleComposition | None = None,
) -> ThresholdResult:
    """Return ThresholdResult per C5 plus composition pins P1–P4."""
    reasons: list[str] = []
    unevaluated: list[str] = []

    if sample_composition is None:
        unevaluated = [f"{pin}: {_OMITTED_REASON}" for pin in _PIN_IDS]
        _append_c5_reasons(
            surface,
            figures,
            reasons,
            verdict_threshold=verdict_threshold,
            value_threshold=value_threshold,
            span_threshold=span_threshold,
        )
        return ThresholdResult(
            passed=False,
            failure_reasons=list(reasons),
            unevaluated_pins=list(unevaluated),
        )

    _append_composition_pin_reasons(
        surface, figures, sample_composition, reasons, unevaluated
    )
    _append_c5_reasons(
        surface,
        figures,
        reasons,
        verdict_threshold=verdict_threshold,
        value_threshold=value_threshold,
        span_threshold=span_threshold,
    )
    return ThresholdResult(
        passed=len(reasons) == 0,
        failure_reasons=list(reasons),
        unevaluated_pins=list(unevaluated),
    )
