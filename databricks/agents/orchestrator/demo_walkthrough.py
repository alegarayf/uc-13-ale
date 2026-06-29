"""UC13 Orchestrator M1 demo walkthrough — cluster verification harness (D-M1-5)."""

from __future__ import annotations

import ast
import os
from typing import Any, Sequence

import yaml

from agents.orchestrator.paths import reports_volume_dir

CONFIDENCE_AREAS: tuple[str, ...] = (
    "business_model",
    "financial_trends",
    "customer_quality",
    "kpi",
    "legal",
    "quality_of_earnings",
    "forecast_support",
)

REQUIRED_ARTIFACTS: tuple[str, ...] = (
    "orchestrator_bundle.yaml",
    "full_report.md",
    "tldr_one_pager.md",
    "full_report.docx",
    "tldr_one_pager.docx",
)


def _get_dbutils() -> Any | None:
    try:
        from IPython import get_ipython

        ip = get_ipython()
        if ip is not None:
            return ip.user_ns.get("dbutils")
    except Exception:
        pass
    return None


def get_param(key: str, default: str | None = None) -> str:
    """Read notebook widget or os.environ (workstream pattern)."""
    dbutils = _get_dbutils()
    if dbutils is not None:
        try:
            value = dbutils.widgets.get(key)
            if value:
                return value
        except Exception:
            pass
    value = os.environ.get(key, default)
    if value is None:
        raise RuntimeError(
            f"Parameter '{key}' not found. "
            "On Databricks: add it as a widget or job parameter. "
            "Locally: export it as an environment variable."
        )
    return value


def _fail(reason: str) -> int:
    print(f"[orchestrator] DEMO FAIL: {reason}")
    return 1


def _ascii_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Render a bordered ASCII table for stakeholder walkthrough output."""
    if not rows:
        widths = [len(h) for h in headers]
    else:
        widths = [
            max(len(headers[i]), *(len(row[i]) for row in rows))
            for i in range(len(headers))
        ]

    def _row(cells: Sequence[str]) -> str:
        return "| " + " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells)) + " |"

    border = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    lines = [border, _row(headers), border]
    lines.extend(_row(row) for row in rows)
    lines.append(border)
    return "\n".join(lines)


def _print_section(title: str, table: str) -> None:
    print(f"\n=== {title} ===")
    print(table)


def _diligence_text_from_entry(entry: dict[str, Any]) -> str:
    """Build stakeholder-readable diligence text from a legal recommended_diligence row."""
    if question := entry.get("question"):
        return str(question)
    if item := entry.get("item"):
        return str(item)
    if doc_type := entry.get("doc_type"):
        return f"Request and review {doc_type}"
    if item_id := entry.get("item_id"):
        return f"Complete diligence item: {str(item_id).replace('_', ' ')}"
    return str(entry)


def _format_diligence_question(row: dict[str, Any]) -> str:
    """Normalize diligence question for display (handles dict rows and legacy str(entry) values)."""
    raw = row.get("question")
    if isinstance(raw, dict):
        return _diligence_text_from_entry(raw)
    if isinstance(raw, str):
        stripped = raw.strip()
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


def run(company_name: str | None = None, catalog: str | None = None) -> int:
    """Execute M1 demo gates; return 0 on pass, 1 on any gate failure."""
    company_name = company_name or get_param("sp_company_name", "Elder Care")
    catalog = catalog or get_param("catalog", "uc13_ale")

    vol_dir = reports_volume_dir(catalog, company_name)
    bundle_path = f"{vol_dir}/orchestrator_bundle.yaml"

    if not os.path.exists(bundle_path):
        return _fail(f"bundle not found: {bundle_path}")

    print(f"[orchestrator] loaded {bundle_path}")
    try:
        with open(bundle_path, encoding="utf-8") as fh:
            bundle = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        return _fail(f"bundle YAML parse error: {exc}")

    if not isinstance(bundle, dict):
        return _fail("bundle root is not a mapping")

    meta = bundle.get("meta")
    if not isinstance(meta, dict):
        return _fail("meta block missing or not a mapping")

    if meta.get("demo_mode"):
        disclaimer = meta.get("disclaimer_text")
        if not disclaimer:
            return _fail("demo_mode true but meta.disclaimer_text missing")
        print("\n--- Demo disclaimer ---")
        print(disclaimer)
        print("---")

    confidence = bundle.get("confidence_by_area")
    if not isinstance(confidence, dict):
        return _fail("confidence_by_area missing or not a mapping")

    conf_rows: list[list[str]] = []
    for area in CONFIDENCE_AREAS:
        value = confidence.get(area)
        if value is None:
            return _fail(f"confidence_by_area.{area} missing")
        conf_rows.append([area, str(value)])
    _print_section("Confidence by area", _ascii_table(["Area", "Confidence"], conf_rows))

    risks = bundle.get("risks")
    if not isinstance(risks, list):
        return _fail("risks missing or not a list")

    risk_rows: list[list[str]] = []
    for row in risks[:8]:
        if not isinstance(row, dict):
            return _fail("risks[] contains non-object row")
        risk = row.get("risk")
        severity = row.get("severity")
        if not risk or not severity:
            return _fail("risks[] row missing risk or severity")
        risk_rows.append([str(risk), str(severity)])
    _print_section("Top risks (up to 8)", _ascii_table(["Risk", "Severity"], risk_rows))

    questions = bundle.get("diligence_questions")
    if not isinstance(questions, list):
        return _fail("diligence_questions missing or not a list")

    question_rows: list[list[str]] = []
    for idx, row in enumerate(questions[:8], start=1):
        if not isinstance(row, dict):
            return _fail("diligence_questions[] contains non-object row")
        question = _format_diligence_question(row)
        if not question:
            return _fail("diligence_questions[] row missing question")
        category = str(row.get("category") or "")
        question_rows.append([str(idx), category, question])
    _print_section(
        "Top diligence questions (up to 8)",
        _ascii_table(["#", "Category", "Question"], question_rows),
    )

    provenance = bundle.get("provenance")
    if not isinstance(provenance, dict):
        return _fail("provenance missing or not a mapping")

    gaps = provenance.get("synthesis_gaps")
    if not isinstance(gaps, list):
        return _fail("provenance.synthesis_gaps missing or not a list")

    gap_rows: list[list[str]] = []
    for row in gaps:
        if not isinstance(row, dict):
            return _fail("provenance.synthesis_gaps[] contains non-object row")
        field_path = row.get("field_path")
        reason = row.get("reason")
        owner = row.get("owner")
        if not field_path or not reason or not owner:
            return _fail("synthesis_gaps[] row missing field_path, reason, or owner")
        gap_rows.append([str(field_path), str(reason), str(owner)])
    _print_section(
        "Synthesis gaps",
        _ascii_table(["field_path", "reason", "owner"], gap_rows),
    )

    for name in REQUIRED_ARTIFACTS:
        path = f"{vol_dir}/{name}"
        if not os.path.exists(path):
            return _fail(f"required artifact missing: {path}")

    print(f"\n[orchestrator] DEMO PASS — all artifacts present under {vol_dir}")
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
